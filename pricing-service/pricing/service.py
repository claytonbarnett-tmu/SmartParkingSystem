"""High-level pricing service interface.

This module is the primary entry point for the Pricing Service's
business logic.  The gRPC server handlers (to be implemented in a
separate module) should call the functions here rather than
interacting with the ORM or bandit engine directly.

Each public function acquires its own SQLAlchemy session, executes
the operation inside a transaction, and guarantees cleanup via a
``try / except / finally`` block:

* On success the transaction is committed.
* On failure it is rolled back and the exception re-raised.
* The session is always closed in the ``finally`` clause.

Public API
----------
- :func:`get_price` — compute a dynamic price for a lot.
- :func:`confirm_booking` — record a successful booking (reward > 0).
- :func:`cancel_booking` — record an abandoned price offer (reward = 0).
- :func:`initialize_lot` — seed the bandit arms for a new lot.
"""

from datetime import datetime

from pricing.bandit import PriceSelection, record_booking, record_no_booking, select_price
from pricing.database import get_session
from pricing.seed import seed_lot


def get_price(
    lot_id: int,
    start_time: datetime,
    occupancy_rate: float,
) -> PriceSelection:
    """Compute a dynamic price for a parking lot.

    Delegates to :func:`~pricing.bandit.select_price`, which runs
    Thompson sampling and logs a :class:`~pricing.models.PricingEvent`.

    Args:
        lot_id:         Identifier of the parking lot.
        start_time:     The requested reservation start time (used
                        to determine the time-of-day context bucket).
        occupancy_rate: Current fraction of occupied spots (0.0–1.0).

    Returns:
        A :class:`~pricing.bandit.PriceSelection` containing the
        offered price and the ``event_id`` needed for feedback.
    """
    session = get_session()
    try:
        result = select_price(session, lot_id, start_time, occupancy_rate)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def confirm_booking(event_id: int) -> None:
    """Record that the user confirmed a booking at the offered price.

    Updates the corresponding :class:`~pricing.models.PricingEvent`
    and increments the :class:`~pricing.models.BanditArm`’s α
    parameter by the normalised revenue reward.

    Args:
        event_id: The ``pricing_event_id`` returned by :func:`get_price`.
    """
    session = get_session()
    try:
        record_booking(session, event_id)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def cancel_booking(event_id: int) -> None:
    """Record that the user abandoned the offered price without booking.

    Increments the arm’s β parameter by 1 (penalising the arm)
    and leaves the pricing event marked as ``booked=False``.

    Args:
        event_id: The ``pricing_event_id`` returned by :func:`get_price`.
    """
    session = get_session()
    try:
        record_no_booking(session, event_id)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def initialize_lot(
    lot_id: int,
    base_price: float = 4.00,
) -> int:
    """Seed bandit arms for a new parking lot.

    Creates a :class:`~pricing.models.LotPricingConfig` row and
    populates 144 :class:`~pricing.models.BanditArm` rows (24
    contexts × 6 multipliers), all initialised to ``Beta(1, 1)``.

    The price ceiling is derived at runtime as
    ``base_price × max(multipliers)`` and is not stored.

    This is idempotent: calling it again for the same ``lot_id``
    will update the config and skip arms that already exist.

    Args:
        lot_id:        Identifier of the parking lot.
        base_price:    Heuristic base price per hour.

    Returns:
        The number of new :class:`~pricing.models.BanditArm` rows
        that were created.
    """
    session = get_session()
    try:
        count = seed_lot(session, lot_id, base_price)
        session.commit()
        return count
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
