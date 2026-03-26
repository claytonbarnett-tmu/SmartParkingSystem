"""Tests for the Thompson sampling engine and reward updates (bandit.py)."""

from datetime import datetime

import numpy as np
from sqlalchemy import select

from pricing.bandit import (
    PriceSelection,
    record_booking,
    record_no_booking,
    select_price,
)
from pricing.models import BanditArm, PricingEvent
from pricing.seed import seed_lot


def _seed(session, lot_id=1, base_price=4.00):
    """Helper: seed a lot and flush."""
    seed_lot(session, lot_id, base_price)
    session.flush()


# ── select_price ──────────────────────────────────────────────────────────


class TestSelectPrice:
    def test_returns_price_selection(self, session):
        _seed(session)
        result = select_price(session, lot_id=1,
                              start_time=datetime(2026, 3, 4, 9, 0),
                              end_time=datetime(2026, 3, 4, 11, 0),
                              occupancy_rate=0.5)
        assert isinstance(result, PriceSelection)

    # Removed: test_final_price_is_base_times_multiplier (multiplier/base_price not returned)

    # Removed: test_base_price_matches_config (base_price not returned)

    # Removed: test_multiplier_in_default_set (multiplier not returned)

    def test_creates_pricing_event(self, session):
        _seed(session)
        result = select_price(session, lot_id=1,
                              start_time=datetime(2026, 3, 4, 9, 0),
                              end_time=datetime(2026, 3, 4, 11, 0),
                              occupancy_rate=0.5)
        session.flush()

        event = session.execute(
            select(PricingEvent).where(
                PricingEvent.event_id == result.event_id
            )
        ).scalar_one()

        assert event.booked is False
        assert event.reward == 0.0
        assert float(event.price_offered) == result.final_price

    # Removed: test_context_key_matches (context_key not returned)

    def test_raises_on_unseeded_lot(self, session):
        """Trying to price a lot with no arms should raise ValueError."""
        # Seed lot 1 but query lot 99
        _seed(session, lot_id=1)
        import pytest
        with pytest.raises(Exception):
            select_price(session, lot_id=99,
                         start_time=datetime(2026, 3, 4, 9, 0),
                         end_time=datetime(2026, 3, 4, 11, 0),
                         occupancy_rate=0.5)


# ── record_booking ────────────────────────────────────────────────────────


class TestRecordBooking:
    def test_marks_event_booked(self, session):
        _seed(session, base_price=4.00)
        result = select_price(session, lot_id=1,
                              start_time=datetime(2026, 3, 4, 9, 0),
                              end_time=datetime(2026, 3, 4, 11, 0),
                              occupancy_rate=0.5)
        session.flush()

        record_booking(session, result.event_id)
        session.flush()

        event = session.execute(
            select(PricingEvent).where(
                PricingEvent.event_id == result.event_id
            )
        ).scalar_one()

        assert event.booked is True
        assert event.reward > 0.0

    def test_reward_is_normalized(self, session):
        _seed(session, base_price=4.00)
        result = select_price(session, lot_id=1,
                              start_time=datetime(2026, 3, 4, 9, 0),
                              end_time=datetime(2026, 3, 4, 11, 0),
                              occupancy_rate=0.5)
        session.flush()

        record_booking(session, result.event_id)
        session.flush()

        event = session.execute(
            select(PricingEvent).where(
                PricingEvent.event_id == result.event_id
            )
        ).scalar_one()

        # Ceiling is derived: base_price * max(DEFAULT_MULTIPLIERS) = 4.00 * 1.50 = 6.00
        expected_reward = float(event.price_offered) / 6.00
        assert abs(event.reward - expected_reward) < 1e-9

    def test_alpha_increases(self, session):
        _seed(session)
        result = select_price(session, lot_id=1,
                              start_time=datetime(2026, 3, 4, 9, 0),
                              end_time=datetime(2026, 3, 4, 11, 0),
                              occupancy_rate=0.5)
        session.flush()

        event = session.execute(
            select(PricingEvent).where(PricingEvent.event_id == result.event_id)
        ).scalar_one()
        arm_id = event.arm_id
        arm_before = session.execute(
            select(BanditArm).where(BanditArm.arm_id == arm_id)
        ).scalar_one()
        alpha_before = arm_before.alpha

        record_booking(session, result.event_id)
        session.flush()
        session.expire_all()

        arm_after = session.execute(
            select(BanditArm).where(BanditArm.arm_id == arm_id)
        ).scalar_one()

        assert arm_after.alpha > alpha_before

    def test_total_pulls_increments(self, session):
        _seed(session)
        result = select_price(session, lot_id=1,
                              start_time=datetime(2026, 3, 4, 9, 0),
                              end_time=datetime(2026, 3, 4, 11, 0),
                              occupancy_rate=0.5)
        session.flush()

        record_booking(session, result.event_id)
        session.flush()
        session.expire_all()

        event = session.execute(
            select(PricingEvent).where(PricingEvent.event_id == result.event_id)
        ).scalar_one()
        arm_id = event.arm_id
        arm = session.execute(
            select(BanditArm).where(BanditArm.arm_id == arm_id)
        ).scalar_one()

        assert arm.total_pulls == 1

    def test_total_revenue_increases(self, session):
        _seed(session)
        result = select_price(session, lot_id=1,
                              start_time=datetime(2026, 3, 4, 9, 0),
                              end_time=datetime(2026, 3, 4, 11, 0),
                              occupancy_rate=0.5)
        session.flush()

        record_booking(session, result.event_id)
        session.flush()
        session.expire_all()

        event = session.execute(
            select(PricingEvent).where(PricingEvent.event_id == result.event_id)
        ).scalar_one()
        arm_id = event.arm_id
        arm = session.execute(
            select(BanditArm).where(BanditArm.arm_id == arm_id)
        ).scalar_one()

        assert arm.total_revenue == result.final_price


# ── record_no_booking ─────────────────────────────────────────────────────


class TestRecordNoBooking:
    def test_event_stays_unbooked(self, session):
        _seed(session)
        result = select_price(session, lot_id=1,
                      start_time=datetime(2026, 3, 4, 9, 0),
                      end_time=datetime(2026, 3, 4, 11, 0),
                      occupancy_rate=0.5)
        session.flush()

        record_no_booking(session, result.event_id)
        session.flush()

        event = session.execute(
            select(PricingEvent).where(
                PricingEvent.event_id == result.event_id
            )
        ).scalar_one()

        assert event.booked is False
        assert event.reward == 0.0

    def test_beta_increases(self, session):
        _seed(session)
        result = select_price(session, lot_id=1,
                      start_time=datetime(2026, 3, 4, 9, 0),
                      end_time=datetime(2026, 3, 4, 11, 0),
                      occupancy_rate=0.5)
        session.flush()

        event = session.execute(
            select(PricingEvent).where(PricingEvent.event_id == result.event_id)
        ).scalar_one()
        arm_id = event.arm_id
        arm_before = session.execute(
            select(BanditArm).where(BanditArm.arm_id == arm_id)
        ).scalar_one()
        beta_before = arm_before.beta_param

        record_no_booking(session, result.event_id)
        session.flush()
        session.expire_all()

        arm_after = session.execute(
            select(BanditArm).where(BanditArm.arm_id == arm_id)
        ).scalar_one()

        assert arm_after.beta_param == beta_before + 1.0

    def test_alpha_unchanged(self, session):
        _seed(session)
        result = select_price(session, lot_id=1,
                      start_time=datetime(2026, 3, 4, 9, 0),
                      end_time=datetime(2026, 3, 4, 11, 0),
                      occupancy_rate=0.5)
        session.flush()

        event = session.execute(
            select(PricingEvent).where(PricingEvent.event_id == result.event_id)
        ).scalar_one()
        arm_id = event.arm_id
        arm_before = session.execute(
            select(BanditArm).where(BanditArm.arm_id == arm_id)
        ).scalar_one()
        alpha_before = arm_before.alpha

        record_no_booking(session, result.event_id)
        session.flush()
        session.expire_all()

        arm_after = session.execute(
            select(BanditArm).where(BanditArm.arm_id == arm_id)
        ).scalar_one()

        assert arm_after.alpha == alpha_before

    def test_total_pulls_increments(self, session):
        _seed(session)
        result = select_price(session, lot_id=1,
                              start_time=datetime(2026, 3, 4, 9, 0),
                              end_time=datetime(2026, 3, 4, 11, 0),
                              occupancy_rate=0.5)
        session.flush()

        record_no_booking(session, result.event_id)
        session.flush()
        session.expire_all()

        event = session.execute(
            select(PricingEvent).where(PricingEvent.event_id == result.event_id)
        ).scalar_one()
        arm_id = event.arm_id
        arm = session.execute(
            select(BanditArm).where(BanditArm.arm_id == arm_id)
        ).scalar_one()

        assert arm.total_pulls == 1


# ── Thompson sampling behaviour ──────────────────────────────────────────


class TestThompsonSamplingBehaviour:
    """Statistical tests that verify the bandit learns over time."""

    def test_favours_arm_with_high_alpha(self, session):
        """After many bookings on ×1.0, that arm should be selected most often."""
        _seed(session, base_price=4.00)
        context_key = "morning:weekday:medium"

        # Artificially boost the ×1.0 arm
        target_arm = session.execute(
            select(BanditArm).where(
                BanditArm.lot_id == 1,
                BanditArm.context_key == context_key,
                BanditArm.multiplier == 1.00,
            )
        ).scalar_one()
        target_arm.alpha = 50.0  # strong prior
        target_arm.beta_param = 2.0
        session.flush()

        # Run many selections and count how often ×1.0 is chosen
        np.random.seed(42)
        selections = []
        for _ in range(100):
            result = select_price(
                session, lot_id=1,
                start_time=datetime(2026, 3, 4, 9, 0),  # morning weekday
                end_time=datetime(2026, 3, 4, 11, 0),
                occupancy_rate=0.50,  # medium
            )
            session.flush()
            event = session.execute(
                select(PricingEvent).where(PricingEvent.event_id == result.event_id)
            ).scalar_one()
            arm = session.execute(
                select(BanditArm).where(BanditArm.arm_id == event.arm_id)
            ).scalar_one()
            selections.append(arm.multiplier)

        count_1_0 = sum(1 for m in selections if m == 1.00)
        # With Beta(50,2) vs Beta(1,1) for other arms, ×1.0 should
        # dominate (>70% of selections).
        assert count_1_0 > 70, (
            f"Expected ×1.0 to be selected >70 times but got {count_1_0}"
        )
