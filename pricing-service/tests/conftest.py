"""Shared test fixtures for the pricing service test suite.

Uses an in-memory SQLite database with SQLAlchemy's schema_translate_map
to redirect the ``pricing`` schema to the default (None) schema, since
SQLite does not support named schemas.
"""


import os
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from pricing.models import Base


@pytest.fixture(scope="session")
def engine():
    """Create a test engine: use Postgres if DATABASE_URL is set, else SQLite."""
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        eng = create_engine(db_url)
        Base.metadata.create_all(eng)
        return eng
    else:
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
    """Yield a transactional session that rolls back after each test.
    For Postgres, drop and recreate all tables before each test for a clean state."""
    db_url = str(engine.url)
    if db_url.startswith("postgresql"):
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
    connection = engine.connect()
    transaction = connection.begin()
    sess = Session(bind=connection)

    yield sess

    sess.close()
    transaction.rollback()
    connection.close()
