from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class SpotStatus(str, Enum):
    available = "available"
    occupied = "occupied"
    reserved = "reserved"


class Spot(BaseModel):
    spot_id: int
    lot_id: int
    label: Optional[str]
    status: SpotStatus
    last_updated: datetime

    class Config:
        orm_mode = True


class Lot(BaseModel):
    lot_id: int
    name: str
    address: Optional[str]
    total_spots: int

    class Config:
        orm_mode = True


class Occupancy(BaseModel):
    lot_id: int
    total_spots: int
    occupied_spots: int
    reserved_spots: int
    available_spots: int


class ReservationRequest(BaseModel):
    user_id: str
    lot_id: int
    spot_id: int
    start_time: datetime
    end_time: datetime
    price_at_booking: Optional[float] = None


class ReservationResponse(BaseModel):
    reservation_id: int
    spot_id: int
    lot_id: int
    user_id: str
    status: str
    start_time: datetime
    end_time: datetime
    price_at_booking: Optional[float]
