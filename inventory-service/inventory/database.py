import os
import time
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://inventory:inventory@db:5432/inventory",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

_initialized = False

_MAX_RETRIES = 5
_RETRY_DELAY = 2

def _initialize() -> None:
    global _initialized
    if _initialized:
        return

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("CREATE SCHEMA IF NOT EXISTS inventory"))
                conn.commit()
            Base.metadata.create_all(engine)
            _initialized = True
            return
        except Exception:
            if attempt == _MAX_RETRIES:
                raise
            time.sleep(_RETRY_DELAY)


def get_session() -> Session:
    _initialize()
    session = SessionLocal()
    session.execute(text("SET search_path TO inventory, public"))
    return session
