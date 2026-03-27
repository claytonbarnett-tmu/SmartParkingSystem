from pydantic import BaseModel
from typing import List

# Request model for viewing reservations by user
class UserReservationsRequest(BaseModel):
    user_id: str  # or int, depending on your user id type

class SearchRequest(BaseModel):
    user_id: str
    lot_ids: List[int]
    start_time: str  # ISO 8601
    end_time: str    # ISO 8601

class LotOccupancyResult(BaseModel):
    lot_id: int
    total_spots: int
    occupied_spots: int
    reserved_spots: int
    available_spots: int

class LotSearchResult(BaseModel):
    lot_id: int
    available_spots: int
    price_per_hour: float
    event_id: str


class SearchResponse(BaseModel):
    results: list[LotSearchResult]


# --- Use Case 4: List Parking Lots ---
class ParkingLotInfo(BaseModel):
    lot_id: str
    lot_name: str
    address: str


# Booking request model for /book endpoint
class BookingRequest(BaseModel):
    event_id: str
    lot_id: int
    user_id: str  # or int, depending on your user id type
    start_time: str  # ISO 8601
    end_time: str    # ISO 8601
    price: float
    is_booking: bool  # True if booking, False if decline


# --- Use Case 5: Create User ---
class CreateUserRequest(BaseModel):
    username: str
    email: str


class CreateUserResponse(BaseModel):
    success: bool
    user_id: str | None = None
    message: str | None = None

# --- Use Case 6: User Login ---
class LoginRequest(BaseModel):
    username: str
    email: str

class LoginResponse(BaseModel):
    success: bool
    user_id: str | None = None
    message: str | None = None

class CancelReservationRequest(BaseModel):
    user_id: str
    reservation_id: str

class CancelReservationResponse(BaseModel):
    success: bool
    message: str | None = None
