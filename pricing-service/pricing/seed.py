"""Seed and initialisation utilities for bandit arms and lot configs.

When a new parking lot is added to the system the Pricing Service
needs to:

1. Create a :class:`~pricing.models.LotPricingConfig` row with a
   sensible base price.
2. Populate :class:`~pricing.models.BanditArm` rows for every
   ``(context_key, multiplier)`` combination — 24 contexts × 6
   multipliers = **144 rows per lot** — each initialised to
   ``Beta(1, 1)`` (uniform prior).

The price ceiling is derived at runtime as
``base_price × max(multipliers)`` and is not stored.

:func:`seed_lot` is the public entry point.  It is idempotent:
calling it again for an existing lot will update the config but
skip arms that already exist.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from pricing.models import BanditArm, LotPricingConfig
from pricing.bandit import ALL_CONTEXT_KEYS, DEFAULT_MULTIPLIERS


def seed_lot(
    session: Session,
    lot_id: int,
    base_price: float = 4.00,
    multipliers: Optional[list[float]] = None,
) -> int:
    """Seed bandit arms and pricing config for a parking lot.

    This function is **idempotent**: it will create a
    :class:`~pricing.models.LotPricingConfig` if none exists (or
    update it), and insert only the
    :class:`~pricing.models.BanditArm` rows that are missing.

    Args:
        session:       An active SQLAlchemy session (caller manages
                       commit / rollback).
        lot_id:        The parking lot identifier.
        base_price:    Heuristic base price per hour.
        multipliers:   Optional list of multiplier values.  Defaults
                       to ``DEFAULT_MULTIPLIERS`` (0.70 – 1.50).

    Returns:
        The number of new :class:`~pricing.models.BanditArm` rows
        that were created (0 if all already existed).
    """
    if multipliers is None:
        multipliers = DEFAULT_MULTIPLIERS

    # Upsert lot config
    existing = session.execute(
        select(LotPricingConfig).where(LotPricingConfig.lot_id == lot_id)
    ).scalar_one_or_none()

    if existing is None:
        session.add(
            LotPricingConfig(
                lot_id=lot_id,
                base_price=base_price,
            )
        )
    else:
        existing.base_price = base_price

    # Seed arms — skip any that already exist
    existing_arms = {
        (row[0], float(row[1]))
        for row in session.execute(
            select(BanditArm.context_key, BanditArm.multiplier).where(
                BanditArm.lot_id == lot_id
            )
        ).all()
    }

    count = 0
    for ctx in ALL_CONTEXT_KEYS:
        for mult in multipliers:
            if (ctx, mult) not in existing_arms:
                session.add(
                    BanditArm(
                        lot_id=lot_id,
                        context_key=ctx,
                        multiplier=mult,
                        alpha=1.0,
                        beta_param=1.0,
                        total_pulls=0,
                        total_revenue=0.0,
                    )
                )
                count += 1

    session.flush()
    return count
