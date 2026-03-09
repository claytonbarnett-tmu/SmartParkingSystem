from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import and_, func, select

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
        return session.execute(select(ParkingLot)).scalars().all()
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
        return session.execute(stmt).scalars().all()
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
        if spot is None or spot.lot_id != lot_id:
            raise ValueError(f"Spot {spot_id} in lot {lot_id} not found")
        spot.status = new_status
        spot.last_updated = datetime.utcnow()
        session.add(spot)
        session.commit()
        session.refresh(spot)
        return spot
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reserve_spot(user_id: str, lot_id: int, spot_id: int, start_time: datetime, end_time: datetime, price_at_booking: Optional[float] = None,) -> Reservation:
    if start_time >= end_time:
        raise ValueError("end_time must be after start_time")

    session = get_session()
    try:
        spot = session.get(ParkingSpot, spot_id)
        if spot is None or spot.lot_id != lot_id:
            raise ValueError(f"Spot {spot_id} in lot {lot_id} not found")

        if spot.status != "available":
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

        spot.status = "reserved"
        spot.last_updated = datetime.utcnow()
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

        reservation.status = "cancelled"
        session.add(reservation)
        session.commit()
        session.refresh(reservation)
        return reservation
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
