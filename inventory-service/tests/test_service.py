from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import select

from inventory import service
from inventory.models import ParkingLot, ParkingSpot, Reservation


def _seed_lot(session, lot_id=1, spot_count=5):
    lot = ParkingLot(lot_id=lot_id, name="Test Lot", total_spots=spot_count)
    session.add(lot)
    session.flush()

    for i in range(spot_count):
        session.add(
            ParkingSpot(
                lot_id=lot_id,
                label=f"A-{i+1}",
                status="available",
            )
        )
    session.flush()


class TestReserveSpot:
    def test_can_reserve_available_spot(self, session):
        _seed_lot(session)
        with patch("inventory.service.get_session", return_value=session):
            start = datetime.utcnow()
            end = start + timedelta(hours=1)
            reservation = service.reserve_spot(
                user_id="user-1",
                lot_id=1,
                spot_id=1,
                start_time=start,
                end_time=end,
                price_at_booking=3.5,
            )

        assert reservation.spot_id == 1
        assert reservation.lot_id == 1
        assert reservation.user_id == "user-1"
        assert reservation.status == "confirmed"

    def test_prevents_overlapping_reservations(self, session):
        _seed_lot(session)
        with patch("inventory.service.get_session", return_value=session):
            start = datetime.utcnow()
            end = start + timedelta(hours=1)
            service.reserve_spot(
                user_id="user-1",
                lot_id=1,
                spot_id=1,
                start_time=start,
                end_time=end,
            )

            try:
                service.reserve_spot(
                    user_id="user-2",
                    lot_id=1,
                    spot_id=1,
                    start_time=start + timedelta(minutes=30),
                    end_time=end + timedelta(minutes=30),
                )
            except ValueError as exc:
                assert "already reserved" in str(exc) or "not available" in str(exc)
            else:
                raise AssertionError("Expected ValueError for overlapping reservation")

    def test_reservation_marks_spot_reserved(self, session):
        _seed_lot(session)
        with patch("inventory.service.get_session", return_value=session):
            start = datetime.utcnow()
            end = start + timedelta(hours=1)
            service.reserve_spot(
                user_id="user-1",
                lot_id=1,
                spot_id=1,
                start_time=start,
                end_time=end,
            )

        spot = session.execute(select(ParkingSpot).where(ParkingSpot.spot_id == 1)).scalar_one()
        assert spot.status == "reserved"


class TestGetLotOccupancy:
    def test_returns_zero_for_empty_lot(self, session):
        _seed_lot(session, spot_count=0)
        with patch("inventory.service.get_session", return_value=session):
            occupancy = service.get_lot_occupancy(lot_id=1)

        assert occupancy["total_spots"] == 0
        assert occupancy["available_spots"] == 0


class TestCancelReservation:
    def test_cancel_sets_status(self, session):
        _seed_lot(session)
        with patch("inventory.service.get_session", return_value=session):
            start = datetime.utcnow()
            end = start + timedelta(hours=1)
            reservation = service.reserve_spot(
                user_id="user-1",
                lot_id=1,
                spot_id=1,
                start_time=start,
                end_time=end,
            )
            service.cancel_reservation(reservation.reservation_id)

        res = session.execute(
            select(Reservation).where(Reservation.reservation_id == reservation.reservation_id)
        ).scalar_one()
        assert res.status == "cancelled"
