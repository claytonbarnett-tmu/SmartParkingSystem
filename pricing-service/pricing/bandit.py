"""Contextual multi-armed bandit with Thompson sampling for dynamic pricing.

This module implements the reinforcement-learning core of the Pricing
Service.  The approach is a *contextual* multi-armed bandit where:

* **Arms** are price *multipliers* (e.g. ×0.70 … ×1.50) applied to a
  per-lot heuristic base price.
* **Context** is a discrete bucket built from three dimensions:
  time-of-day (4 buckets), day-type (weekday / weekend), and current
  lot occupancy (low / medium / high) — giving 24 unique contexts.
* **Reward** is normalised revenue: ``booked × (price_offered / price_ceiling)``.
  This keeps rewards in [0, 1] for clean Beta-distribution updates.

A separate ``Beta(α, β)`` distribution is maintained for every
``(lot, context, arm)`` triple.  At decision time the algorithm:

1. Draws one sample from each arm’s Beta distribution.
2. Selects the arm with the highest sample (Thompson sampling).
3. Logs the offered price as a :class:`~pricing.models.PricingEvent`.

When the booking outcome is known, the arm’s parameters are updated:

* **Booked:** ``α += reward``, ``β += (1 - reward)``.
* **Not booked:** ``β += 1`` (no change to α).

Public API
----------
- :func:`build_context_key` — encode a datetime + occupancy into a key.
- :func:`select_price` — run Thompson sampling and return the price.
- :func:`record_booking` — update the arm after a confirmed booking.
- :func:`record_no_booking` — update the arm after abandonment.
"""

from datetime import datetime
from typing import NamedTuple

import numpy as np
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from pricing.models import BanditArm, LotPricingConfig, PricingEvent

# ---------------------------------------------------------------------------
# Context helpers
# ---------------------------------------------------------------------------

TIME_BUCKETS = {
    range(6, 11): "morning",     # 06:00 – 10:59
    range(11, 16): "afternoon",  # 11:00 – 15:59
    range(16, 21): "evening",    # 16:00 – 20:59
}
_NIGHT_LABEL = "night"  # 21:00 – 05:59


def _time_bucket(hour: int) -> str:
    """Map an hour (0–23) to a time-of-day label."""
    for rng, label in TIME_BUCKETS.items():
        if hour in rng:
            return label
    return _NIGHT_LABEL


def _day_type(dt: datetime) -> str:
    """Return ``'weekday'`` or ``'weekend'`` for the given datetime."""
    return "weekend" if dt.weekday() >= 5 else "weekday"


def _occupancy_bucket(rate: float) -> str:
    """Discretise an occupancy rate (0.0–1.0) into low / medium / high.

    Thresholds:
        * ``rate < 0.30`` → ``'low'``
        * ``0.30 ≤ rate ≤ 0.70`` → ``'medium'``
        * ``rate > 0.70`` → ``'high'``
    """
    if rate < 0.30:
        return "low"
    elif rate <= 0.70:
        return "medium"
    else:
        return "high"


def build_context_key(dt: datetime, occupancy_rate: float) -> str:
    """Encode the current context into a colon-separated string key.

    Format: ``"<time_bucket>:<day_type>:<occupancy_bucket>"``

    Examples:
        >>> build_context_key(datetime(2026, 3, 4, 9, 0), 0.82)
        'morning:weekday:high'
        >>> build_context_key(datetime(2026, 3, 7, 22, 0), 0.15)
        'night:weekend:low'

    Args:
        dt: The datetime representing the current (or requested) time.
        occupancy_rate: Fraction of spots currently occupied (0.0–1.0).

    Returns:
        A context key string usable as a lookup key in ``bandit_arms``.
    """
    return f"{_time_bucket(dt.hour)}:{_day_type(dt)}:{_occupancy_bucket(occupancy_rate)}"


# All possible context keys (24 total)
ALL_CONTEXT_KEYS: list[str] = [
    f"{t}:{d}:{o}"
    for t in ("morning", "afternoon", "evening", "night")
    for d in ("weekday", "weekend")
    for o in ("low", "medium", "high")
]

# Default multiplier arms
DEFAULT_MULTIPLIERS: list[float] = [0.70, 0.85, 1.00, 1.15, 1.30, 1.50]


# ---------------------------------------------------------------------------
# Thompson sampling
# ---------------------------------------------------------------------------


class PriceSelection(NamedTuple):
    """Immutable result returned by :func:`select_price`.

    Attributes:
        arm_id:      Primary key of the chosen :class:`~pricing.models.BanditArm`.
        multiplier:  The price multiplier that was selected.
        base_price:  The lot's base price at decision time.
        final_price: ``base_price × multiplier`` — the price to show the user.
        context_key: The context string used for arm lookup.
        event_id:    Primary key of the logged :class:`~pricing.models.PricingEvent`.
                     Must be passed back in :func:`record_booking` or
                     :func:`record_no_booking` to close the feedback loop.
    """
    arm_id: int
    multiplier: float
    base_price: float
    final_price: float
    context_key: str
    event_id: int


def select_price(
    session: Session,
    lot_id: int,
    current_time: datetime,
    occupancy_rate: float,
) -> PriceSelection:
    """Run Thompson sampling to select a price for the given lot.

    Steps:

    1. Build the context key from ``current_time`` and ``occupancy_rate``.
    2. Load all :class:`~pricing.models.BanditArm` rows matching
       ``(lot_id, context_key)``.
    3. Draw one sample from each arm's ``Beta(α, β)`` distribution.
    4. Select the arm with the highest sample (exploration is
       implicit in the variance of the Beta draws).
    5. Compute ``final_price = base_price × multiplier``.
    6. Insert a :class:`~pricing.models.PricingEvent` with
       ``booked=False`` so the outcome can be recorded later.

    Args:
        session:        An active SQLAlchemy session (caller manages
                        commit / rollback).
        lot_id:         The parking lot to price.
        current_time:   The time of the pricing request.
        occupancy_rate: Current occupancy fraction (0.0–1.0), typically
                        obtained from the Inventory Service via gRPC.

    Returns:
        A :class:`PriceSelection` named tuple with the chosen price
        and the ``event_id`` for later feedback.

    Raises:
        ValueError: If no bandit arms exist for the computed context
            (call :func:`~pricing.seed.seed_lot` first).
        sqlalchemy.exc.NoResultFound: If the lot has no
            :class:`~pricing.models.LotPricingConfig` entry.
    """
    context_key = build_context_key(current_time, occupancy_rate)

    # Fetch lot pricing config
    config = session.execute(
        select(LotPricingConfig).where(LotPricingConfig.lot_id == lot_id)
    ).scalar_one()

    # Fetch all arms for this (lot, context)
    arms: list[BanditArm] = list(
        session.execute(
            select(BanditArm).where(
                BanditArm.lot_id == lot_id,
                BanditArm.context_key == context_key,
            )
        ).scalars()
    )

    if not arms:
        raise ValueError(
            f"No bandit arms found for lot_id={lot_id}, context_key={context_key}. "
            "Run seed_lot() first."
        )

    # Thompson sample: draw from Beta(alpha, beta) for each arm
    samples = [
        np.random.beta(arm.alpha, arm.beta_param) for arm in arms
    ]
    best_idx = int(np.argmax(samples))
    chosen_arm = arms[best_idx]

    base_price = float(config.base_price)
    multiplier = float(chosen_arm.multiplier)
    final_price = round(base_price * multiplier, 2)

    # Log the pricing event
    event = PricingEvent(
        lot_id=lot_id,
        arm_id=chosen_arm.arm_id,
        context_key=context_key,
        base_price=base_price,
        multiplier=multiplier,
        price_offered=final_price,
        booked=False,
        reward=0.0,
    )
    session.add(event)
    session.flush()  # populates event.event_id

    return PriceSelection(
        arm_id=chosen_arm.arm_id,
        multiplier=multiplier,
        base_price=base_price,
        final_price=final_price,
        context_key=context_key,
        event_id=event.event_id,
    )


# ---------------------------------------------------------------------------
# Reward updates
# ---------------------------------------------------------------------------


def record_booking(session: Session, event_id: int) -> None:
    """Update the bandit arm after the user confirms a booking.

    Computes the normalised revenue reward:

        ``reward = price_offered / price_ceiling``

    where ``price_ceiling = base_price × max(multipliers)`` (derived,
    not stored).

    Then updates the arm's Beta parameters:

        ``α += reward``
        ``β += (1 - reward)``

    This means a booking at a *high* price contributes more to α
    (shifting the distribution right → arm favoured more) than a
    booking at a low price, incentivising revenue over pure
    conversion.

    Args:
        session:  An active SQLAlchemy session.
        event_id: Primary key of the :class:`~pricing.models.PricingEvent`
                  created by :func:`select_price`.
    """
    event = session.execute(
        select(PricingEvent).where(PricingEvent.event_id == event_id)
    ).scalar_one()

    # Derive ceiling for normalization
    config = session.execute(
        select(LotPricingConfig).where(LotPricingConfig.lot_id == event.lot_id)
    ).scalar_one()

    ceiling = float(config.base_price) * max(DEFAULT_MULTIPLIERS)
    reward = float(event.price_offered) / ceiling

    # Update the pricing event
    event.booked = True
    event.reward = reward

    # Update the bandit arm's Beta params
    session.execute(
        update(BanditArm)
        .where(BanditArm.arm_id == event.arm_id)
        .values(
            alpha=BanditArm.alpha + reward,
            beta_param=BanditArm.beta_param + (1.0 - reward),
            total_pulls=BanditArm.total_pulls + 1,
            total_revenue=BanditArm.total_revenue + float(event.price_offered),
        )
    )

    session.flush()


def record_no_booking(session: Session, event_id: int) -> None:
    """Update the bandit arm when the user does not book.

    Sets ``reward = 0`` and increments only the arm's β parameter:

        ``β += 1``

    This penalises the arm (its Beta mean shifts left) without
    any offsetting α increase, making it less likely to be
    selected in future draws for this context.

    Args:
        session:  An active SQLAlchemy session.
        event_id: Primary key of the :class:`~pricing.models.PricingEvent`.
    """
    event = session.execute(
        select(PricingEvent).where(PricingEvent.event_id == event_id)
    ).scalar_one()

    # reward = 0 → alpha unchanged, beta += 1
    event.booked = False
    event.reward = 0.0

    session.execute(
        update(BanditArm)
        .where(BanditArm.arm_id == event.arm_id)
        .values(
            beta_param=BanditArm.beta_param + 1.0,
            total_pulls=BanditArm.total_pulls + 1,
        )
    )

    session.flush()
