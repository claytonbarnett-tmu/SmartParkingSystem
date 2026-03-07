"""Tests for lot seeding logic (seed.py)."""

from pricing.bandit import ALL_CONTEXT_KEYS, DEFAULT_MULTIPLIERS
from pricing.models import BanditArm, LotPricingConfig
from pricing.seed import seed_lot

from sqlalchemy import select


class TestSeedLot:
    def test_creates_config(self, session):
        seed_lot(session, lot_id=1, base_price=5.00)
        session.flush()

        config = session.execute(
            select(LotPricingConfig).where(LotPricingConfig.lot_id == 1)
        ).scalar_one()

        assert float(config.base_price) == 5.00

    def test_creates_144_arms(self, session):
        count = seed_lot(session, lot_id=1)
        session.flush()

        assert count == 144  # 24 contexts × 6 multipliers

        arms = session.execute(
            select(BanditArm).where(BanditArm.lot_id == 1)
        ).scalars().all()

        assert len(arms) == 144

    def test_arms_initialised_to_uniform_prior(self, session):
        seed_lot(session, lot_id=1)
        session.flush()

        arms = session.execute(
            select(BanditArm).where(BanditArm.lot_id == 1)
        ).scalars().all()

        for arm in arms:
            assert arm.alpha == 1.0
            assert arm.beta_param == 1.0
            assert arm.total_pulls == 0
            assert arm.total_revenue == 0.0

    def test_all_context_multiplier_combinations_present(self, session):
        seed_lot(session, lot_id=1)
        session.flush()

        arms = session.execute(
            select(BanditArm).where(BanditArm.lot_id == 1)
        ).scalars().all()

        pairs = {(a.context_key, float(a.multiplier)) for a in arms}
        expected = {
            (ctx, mult)
            for ctx in ALL_CONTEXT_KEYS
            for mult in DEFAULT_MULTIPLIERS
        }
        assert pairs == expected

    def test_idempotent_no_duplicates(self, session):
        count1 = seed_lot(session, lot_id=1, base_price=4.00)
        session.flush()
        count2 = seed_lot(session, lot_id=1, base_price=6.00)
        session.flush()

        assert count1 == 144
        assert count2 == 0  # all arms already existed

        arms = session.execute(
            select(BanditArm).where(BanditArm.lot_id == 1)
        ).scalars().all()
        assert len(arms) == 144

    def test_idempotent_updates_config(self, session):
        seed_lot(session, lot_id=1, base_price=4.00)
        session.flush()
        seed_lot(session, lot_id=1, base_price=6.00)
        session.flush()

        config = session.execute(
            select(LotPricingConfig).where(LotPricingConfig.lot_id == 1)
        ).scalar_one()

        assert float(config.base_price) == 6.00

    def test_custom_multipliers(self, session):
        custom = [0.90, 1.00, 1.10]
        count = seed_lot(session, lot_id=1, multipliers=custom)
        session.flush()

        assert count == 24 * 3  # 24 contexts × 3 multipliers

    def test_separate_lots_independent(self, session):
        seed_lot(session, lot_id=1)
        seed_lot(session, lot_id=2)
        session.flush()

        arms_1 = session.execute(
            select(BanditArm).where(BanditArm.lot_id == 1)
        ).scalars().all()
        arms_2 = session.execute(
            select(BanditArm).where(BanditArm.lot_id == 2)
        ).scalars().all()

        assert len(arms_1) == 144
        assert len(arms_2) == 144
