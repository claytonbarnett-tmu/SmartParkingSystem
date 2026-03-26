
            assert booked_status[results[0].event_id] is True
            assert booked_status[results[1].event_id] is False
"""Tests for the high-level service interface (service.py).

Each function in service.py acquires its own session via get_session(),
so these tests patch that to inject the test fixture session instead.
"""

from datetime import datetime
from unittest.mock import patch

from sqlalchemy import select

from pricing.bandit import PriceSelection
from pricing.models import BanditArm, LotPricingConfig, PricingEvent
from pricing.seed import seed_lot

from pricing.service import cancel_booking, confirm_booking, get_price, initialize_lot


def _seed(session, lot_id=1, base_price=4.00):
    """Helper: seed a lot and flush."""
    seed_lot(session, lot_id, base_price)
    session.flush()


class TestInitializeLot:
    def test_creates_arms(self, session):
        with patch("pricing.service.get_session", return_value=session):
            count = initialize_lot(lot_id=1, base_price=5.00)

        assert count == 144

    def test_creates_config(self, session):
        with patch("pricing.service.get_session", return_value=session):
            initialize_lot(lot_id=1, base_price=5.00)

        config = session.execute(
            select(LotPricingConfig).where(LotPricingConfig.lot_id == 1)
        ).scalar_one()
        assert float(config.base_price) == 5.00

    def test_idempotent(self, session):
        with patch("pricing.service.get_session", return_value=session):
            count1 = initialize_lot(lot_id=1)
            count2 = initialize_lot(lot_id=1)

        assert count1 == 144
        assert count2 == 0

    def test_does_not_accept_price_ceiling(self):
        """Regression: initialize_lot must not accept a price_ceiling argument."""
        import inspect
        sig = inspect.signature(initialize_lot)
        assert "price_ceiling" not in sig.parameters


class TestGetPrice:
    def test_returns_price_selection(self, session):
        _seed(session)
        with patch("pricing.service.get_session", return_value=session):
            result = get_price(
                lot_id=1,
                start_time=datetime(2026, 3, 4, 9, 0),
                end_time=datetime(2026, 3, 4, 11, 0),
                occupancy_rate=0.5,
            )
        assert isinstance(result, PriceSelection)

    def test_price_is_positive(self, session):
        _seed(session)
        with patch("pricing.service.get_session", return_value=session):
            result = get_price(
                lot_id=1,
                start_time=datetime(2026, 3, 4, 9, 0),
                end_time=datetime(2026, 3, 4, 11, 0),
                occupancy_rate=0.5,
            )
        assert result.final_price > 0

    def test_creates_event(self, session):
        _seed(session)
        with patch("pricing.service.get_session", return_value=session):
            result = get_price(
                lot_id=1,
                start_time=datetime(2026, 3, 4, 14, 0),
                end_time=datetime(2026, 3, 4, 16, 0),
                occupancy_rate=0.6,
            )

        event = session.execute(
            select(PricingEvent).where(PricingEvent.event_id == result.event_id)
        ).scalar_one()
        assert event.booked is False


class TestConfirmBooking:
    def test_marks_booked(self, session):
        _seed(session)
        with patch("pricing.service.get_session", return_value=session):
            result = get_price(
                lot_id=1,
                start_time=datetime(2026, 3, 4, 9, 0),
                end_time=datetime(2026, 3, 4, 11, 0),
                occupancy_rate=0.5,
            )
            confirm_booking(result.event_id)

        event = session.execute(
            select(PricingEvent).where(PricingEvent.event_id == result.event_id)
        ).scalar_one()
        assert event.booked is True
        assert event.reward > 0.0

        def test_updates_arm_alpha(self, session):
            _seed(session)
            with patch("pricing.service.get_session", return_value=session):
                result = get_price(
                    lot_id=1,
                    start_time=datetime(2026, 3, 4, 9, 0),
                    end_time=datetime(2026, 3, 4, 11, 0),
                    occupancy_rate=0.5,
                )
                event = session.execute(
                    select(PricingEvent).where(PricingEvent.event_id == result.event_id)
                ).scalar_one()
                arm_id = event.arm_id
                arm_before = session.execute(
                    select(BanditArm).where(BanditArm.arm_id == arm_id)
                ).scalar_one()
                alpha_before = arm_before.alpha

                confirm_booking(result.event_id)
                session.expire_all()

                arm_after = session.execute(
                    select(BanditArm).where(BanditArm.arm_id == arm_id)
                ).scalar_one()
                assert arm_after.alpha > alpha_before


class TestCancelBooking:
        def test_stays_unbooked(self, session):
            _seed(session)
            with patch("pricing.service.get_session", return_value=session):
                result = get_price(
                    lot_id=1,
                    start_time=datetime(2026, 3, 4, 9, 0),
                    end_time=datetime(2026, 3, 4, 11, 0),
                    occupancy_rate=0.5,
                )
                cancel_booking(result.event_id)

                event = session.execute(
                    select(PricingEvent).where(PricingEvent.event_id == result.event_id)
                ).scalar_one()
                assert event.booked is False
                assert event.reward == 0.0

        def test_increases_beta(self, session):
            _seed(session)
            with patch("pricing.service.get_session", return_value=session):
                result = get_price(
                    lot_id=1,
                    start_time=datetime(2026, 3, 4, 9, 0),
                    end_time=datetime(2026, 3, 4, 11, 0),
                    occupancy_rate=0.5,
                )
                event = session.execute(
                    select(PricingEvent).where(PricingEvent.event_id == result.event_id)
                ).scalar_one()
                arm_id = event.arm_id
                arm_before = session.execute(
                    select(BanditArm).where(BanditArm.arm_id == arm_id)
                ).scalar_one()
                beta_before = arm_before.beta_param

                cancel_booking(result.event_id)
                session.expire_all()

                arm_after = session.execute(
                    select(BanditArm).where(BanditArm.arm_id == arm_id)
                ).scalar_one()
                assert arm_after.beta_param == beta_before + 1.0
