from typing import Optional, Tuple
import grpc
from datetime import datetime
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Sequence
from sqlalchemy import and_, func, select
from typing import List
from inventory.generated_pricing import pricing_pb2, pricing_pb2_grpc
from inventory.database import get_session
from inventory.models import (
    ParkingLot,
    ParkingSpot,
    Reservation,
    RESERVATION_STATUSES,
    SPOT_STATUSES,
    User,
)


def list_lots() -> List[ParkingLot]:
    session = get_session()
    try:
        result: Sequence[ParkingLot] = session.execute(select(ParkingLot)).scalars().all()
        return list(result)
    finally:
        session.close()


def get_lot(lot_id: int) -> Optional[ParkingLot]:
    session = get_session()
    try:
        return session.get(ParkingLot, lot_id)
    finally:
        session.close()


def list_spots(lot_id: int, status: Optional[str] = None) -> List[ParkingSpot]:
    session = get_session()
    try:
        stmt = select(ParkingSpot).where(ParkingSpot.lot_id == lot_id)
        if status is not None:
            stmt = stmt.where(ParkingSpot.status == status)
        result: Sequence[ParkingSpot] = session.execute(stmt).scalars().all()
        return list(result)
    finally:
        session.close()


def get_lot_occupancy(lot_id: int) -> Dict[str, int]:
    session = get_session()
    try:
        total = session.execute(
            select(func.count()).select_from(ParkingSpot).where(ParkingSpot.lot_id == lot_id)
        ).scalar_one()
        counts = {
            row[0]: row[1]
            for row in session.execute(
                select(ParkingSpot.status, func.count())
                .where(ParkingSpot.lot_id == lot_id)
                .group_by(ParkingSpot.status)
            )
        }

        return {
            "lot_id": lot_id,
            "total_spots": total,
            "occupied_spots": counts.get("occupied", 0),
            "reserved_spots": counts.get("reserved", 0),
            "available_spots": counts.get("available", 0),
        }
    finally:
        session.close()


def update_spot_status(lot_id: int, spot_id: int, new_status: str) -> ParkingSpot:
    session = get_session()
    try:
        spot = session.get(ParkingSpot, spot_id)
        if spot is None or getattr(spot, "lot_id", None) != lot_id:
            raise ValueError(f"Spot {spot_id} in lot {lot_id} not found")
        setattr(spot, "status", new_status)
        setattr(spot, "last_updated", datetime.utcnow())
        session.add(spot)
        session.commit()
        session.refresh(spot)
        return spot
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reserve_spot(user_id: str, lot_id: int, spot_id: int, start_time: datetime, end_time: datetime, price_at_booking: Optional[float] = None) -> Reservation:
    if start_time >= end_time:
        raise ValueError("end_time must be after start_time")

    session = get_session()
    try:
        spot = session.get(ParkingSpot, spot_id)
        if spot is None or getattr(spot, "lot_id", None) != lot_id:
            raise ValueError(f"Spot {spot_id} in lot {lot_id} not found")

        if getattr(spot, "status", None) != "available":
            raise ValueError("Spot is not available")

        # Ensure user exists (create if missing)
        user = session.get(User, user_id)
        if user is None:
            user = User(user_id=user_id)
            session.add(user)

        # Prevent double-booking by rejecting overlapping confirmed reservations.
        overlap = session.execute(
            select(Reservation)
            .where(
                Reservation.spot_id == spot_id,
                Reservation.status == "confirmed",
                Reservation.end_time > start_time,
                Reservation.start_time < end_time,
            )
        ).scalars().first()

        if overlap is not None:
            raise ValueError("Spot is already reserved for this time window")

        setattr(spot, "status", "reserved")
        setattr(spot, "last_updated", datetime.utcnow())
        session.add(spot)

        reservation = Reservation(
            spot_id=spot_id,
            lot_id=lot_id,
            user_id=user_id,
            status="confirmed",
            start_time=start_time,
            end_time=end_time,
            price_at_booking=price_at_booking,
        )
        session.add(reservation)
        session.commit()
        session.refresh(reservation)
        return reservation
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def cancel_reservation(reservation_id: int) -> Reservation:
    session = get_session()
    try:
        reservation = session.get(Reservation, reservation_id)
        if reservation is None:
            raise ValueError(f"Reservation {reservation_id} not found")

        setattr(reservation, "status", "cancelled")
        session.add(reservation)
        session.commit()
        session.refresh(reservation)
        return reservation
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def reserve_spot_grpc(user_id: str, lot_id: int, spot_id: int, start_time: str, end_time: str, price_at_booking: Optional[float] = None, event_id: Optional[str] = None):
    # event_id must be passed for pricing validation
    if event_id is None:
        raise ValueError("event_id is required for pricing validation")

    # Call PricingService.RecordBookingOutcome before proceeding
    channel = grpc.insecure_channel("pricing-service:50052")
    stub = pricing_pb2_grpc.PricingServiceStub(channel)
    outcome_req = pricing_pb2.RecordBookingOutcomeRequest(
        event_id=event_id,
        user_id=user_id,
        price_offered=price_at_booking if price_at_booking is not None else 0.0,
        booked=True,
    )
    outcome_resp = stub.RecordBookingOutcome(outcome_req)
    if not outcome_resp.success:
        raise ValueError(f"Pricing validation failed: {outcome_resp.failure_reason}")
    # Parse ISO 8601 strings
    start_dt = datetime.fromisoformat(start_time)
    end_dt = datetime.fromisoformat(end_time)
    return reserve_spot(
        user_id=user_id,
        lot_id=lot_id,
        spot_id=spot_id,
        start_time=start_dt,
        end_time=end_dt,
        price_at_booking=price_at_booking,
    )

def list_reservations(user_id: str) -> List[Reservation]:
    session = get_session()
    try:
        result: Sequence[Reservation] = session.execute(
            select(Reservation).where(Reservation.user_id == user_id)
        ).scalars().all()
        return list(result)
    finally:
        session.close()

def create_user(username: str, email: str) -> tuple[bool, Optional[str], str]:
    """
    Attempts to create a new user. Returns (success, user_id, message).
    """
    session = get_session()
    try:
        # Check for existing username or email
        existing = session.execute(
            select(User).where((User.display_name == username) | (User.email == email))
        ).scalars().first()
        if existing:
            return False, None, "Username or email already exists."
        # Create new user
        import uuid
        user_id = str(uuid.uuid4())
        user = User(user_id=user_id, display_name=username, email=email)
        session.add(user)
        session.commit()
        return True, user_id, "User created successfully."
    except Exception as exc:
        session.rollback()
        return False, None, f"Error: {exc}"
    finally:
        session.close()