from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

SPOT_STATUSES = ("available", "occupied", "reserved")
RESERVATION_STATUSES = ("confirmed", "cancelled", "expired", "completed")

class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "inventory"}

    user_id = Column(String(64), primary_key=True)
    display_name = Column(String(128), nullable=True)
    email = Column(String(256), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ParkingLot(Base):
    __tablename__ = "parking_lots"
    __table_args__ = {"schema": "inventory"}

    lot_id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    address = Column(Text, nullable=True)
    total_spots = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    spots = relationship("ParkingSpot", back_populates="lot")


class ParkingSpot(Base):
    __tablename__ = "parking_spots"
    __table_args__ = (
        UniqueConstraint("lot_id", "label", name="uq_spot_lot_label"),
        {"schema": "inventory"},
    )

    spot_id = Column(Integer, primary_key=True)
    lot_id = Column(Integer, ForeignKey("inventory.parking_lots.lot_id"), nullable=False)
    label = Column(String(32), nullable=True)
    status = Column(String(16), nullable=False, default="available")
    last_updated = Column(DateTime, nullable=True, default=datetime.utcnow)

    lot = relationship("ParkingLot", back_populates="spots")
    reservations = relationship("Reservation", back_populates="spot")


class Reservation(Base):
    __tablename__ = "reservations"
    __table_args__ = (
        UniqueConstraint("spot_id", "start_time", "end_time", name="uq_reservation_spot_time"),
        {"schema": "inventory"},
    )

    reservation_id = Column(Integer, primary_key=True)
    spot_id = Column(Integer, ForeignKey("inventory.parking_spots.spot_id"), nullable=False)
    lot_id = Column(Integer, ForeignKey("inventory.parking_lots.lot_id"), nullable=False)
    user_id = Column(String(64), ForeignKey("inventory.users.user_id"), nullable=False)
    status = Column(String(16), nullable=False, default="confirmed")
    created_at = Column(DateTime, default=datetime.utcnow)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    price_at_booking = Column(Numeric(8, 2), nullable=True)

    spot = relationship("ParkingSpot", back_populates="reservations")
