"""Shared test fixtures for the pricing service test suite.

Uses an in-memory SQLite database with SQLAlchemy's schema_translate_map
to redirect the ``pricing`` schema to the default (None) schema, since
SQLite does not support named schemas.
"""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from pricing.models import Base


@pytest.fixture(scope="session")
def engine():
    """Create an in-memory SQLite engine with schema translation.

    The ``schema_translate_map`` rewrites every reference to the
    ``pricing`` schema to ``None``, allowing the ORM models to work
    unchanged against SQLite.
    """
    eng = create_engine(
        "sqlite://",
        execution_options={"schema_translate_map": {"pricing": None}},
    )
    # Enable foreign key enforcement in SQLite
    @event.listens_for(eng, "connect")
    def _set_sqlite_pragma(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def session(engine):
    """Yield a transactional session that rolls back after each test."""
    connection = engine.connect()
    transaction = connection.begin()
    sess = Session(bind=connection)

    yield sess

    sess.close()
    transaction.rollback()
    connection.close()
