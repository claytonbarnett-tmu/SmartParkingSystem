"""Database engine and session factory for the Pricing Service.

This module creates the SQLAlchemy ``Engine`` and ``Session`` factory
used by all other modules in the pricing package.  On first use it:

1. Reads ``DATABASE_URL`` from the environment (falling back to a
   local development default).
2. Creates a connection-pool-enabled engine with ``pool_pre_ping``
   for automatic stale-connection recovery.
3. Ensures the ``pricing`` schema and all ORM tables exist in the
   target Postgres database (idempotent — safe to run repeatedly).

Initialization is **lazy**: the database is not contacted until the
first call to :func:`get_session`, which makes imports safe in test
and CLI contexts where no database is available.  A retry loop
handles the common Docker scenario where the application container
starts before PostgreSQL is fully ready.

The public helper :func:`get_session` returns a new ``Session``
whose ``search_path`` is set to ``pricing, public`` so that
ORM table references resolve correctly without needing fully
qualified names everywhere.

Environment variables:
    DATABASE_URL: Full SQLAlchemy-compatible connection string,
        e.g. ``postgresql://parking:secret@postgres:5432/parking``.
        Defaults to ``postgresql://parking:parking@localhost:5432/parking``.
"""

import logging
import os
import time

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from pricing.models import Base

_LOG = logging.getLogger(__name__)

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://parking:parking@db:5432/parking",
)
print(f"[DEBUG] DATABASE_URL in pricing/database.py: {DATABASE_URL}")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

_initialized = False

_MAX_RETRIES = 5
_RETRY_DELAY = 2  # seconds


def _initialize() -> None:
    """Ensure the pricing schema and tables exist.

    Retries up to ``_MAX_RETRIES`` times with a ``_RETRY_DELAY``-second
    pause between attempts, covering the common case where PostgreSQL
    is still starting up in Docker Compose.
    """
    global _initialized
    if _initialized:
        return

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("CREATE SCHEMA IF NOT EXISTS pricing"))
                conn.commit()
            Base.metadata.create_all(engine)
            _initialized = True
            _LOG.info("Database initialized (attempt %d)", attempt)
            return
        except Exception:
            if attempt == _MAX_RETRIES:
                _LOG.error("Database unreachable after %d attempts", _MAX_RETRIES)
                raise
            _LOG.warning(
                "Database not ready (attempt %d/%d), retrying in %ds…",
                attempt, _MAX_RETRIES, _RETRY_DELAY,
            )
            time.sleep(_RETRY_DELAY)


def get_session() -> Session:
    """Create and return a new SQLAlchemy session.

    On the first call, ensures the ``pricing`` schema and all tables
    exist (with retries if the database is not yet available).

    The session's ``search_path`` is set to ``pricing, public`` so
    that all ORM models in :mod:`pricing.models` resolve correctly.

    The caller is responsible for committing or rolling back the
    session and closing it when finished.  The recommended pattern
    is a ``try / except / finally`` block (see :mod:`pricing.service`
    for examples).

    Returns:
        A configured :class:`sqlalchemy.orm.Session` instance.
    """
    _initialize()
    session = SessionLocal()
    # Set search path so unqualified table references resolve to pricing schema
    session.execute(text("SET search_path TO pricing, public"))
    return session
