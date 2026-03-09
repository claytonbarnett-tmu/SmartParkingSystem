import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from inventory.models import Base


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(
        "sqlite://",
        execution_options={"schema_translate_map": {"inventory": None}},
    )

    @event.listens_for(eng, "connect")
    def _set_sqlite_pragma(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def session(engine):
    connection = engine.connect()
    transaction = connection.begin()
    sess = Session(bind=connection)

    yield sess

    sess.close()
    transaction.rollback()
    connection.close()
