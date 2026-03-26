
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

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_price(
    lot_id: int,
    user_id: str,
    start_time: datetime,
    end_time: datetime,
    occupancy_rate: float,
) -> PriceSelection:
    """Compute a dynamic price for a parking lot, optionally as part of a batch."""
    session = get_session()
    try:
        result = select_price(session, lot_id, user_id, start_time, end_time, occupancy_rate)
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
        # Record booking for the selected event
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

def validate_and_record_booking_outcome(event_id: int, user_id: str, price_offered: float, booked: bool) -> tuple[bool, str]:
    """Validate event and securely record booking outcome. Returns (success, failure_reason)."""
    session = get_session()
    try:
        from pricing.models import PricingEvent
        event = session.query(PricingEvent).filter_by(event_id=event_id).one_or_none()
        if event is None:
            logger.info(f"Event not found: event_id={event_id}")
            return False, "Event not found."
        if event.booked:
            logger.info(f"Event already updated: event_id={event_id}")
            return False, "Event already updated."
        if event.user_id != user_id:
            logger.info(f"User ID mismatch: event_id={event_id}, event.user_id={event.user_id}, request.user_id={user_id}")
            return False, "User ID does not match event."
        if float(event.price_offered) != float(price_offered):
            logger.info(f"Price mismatch: event_id={event_id}, event.price_offered={event.price_offered}, request.price_offered={price_offered}")
            return False, "Price offered does not match event."
        # Passed all checks, record outcome
        if booked:
            from pricing.bandit import record_booking
            record_booking(session, event_id)
        else:
            from pricing.bandit import record_no_booking
            record_no_booking(session, event_id)
        session.commit()
        return True, ""
    except Exception as exc:
        logger.exception(f"Exception in validate_and_record_booking_outcome: {exc}")
        session.rollback()
        return False, str(exc)
    finally:
        session.close()
