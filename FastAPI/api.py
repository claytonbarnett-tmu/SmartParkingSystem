from fastapi import FastAPI
from schema import UserReservationsRequest
from schema import ParkingLotInfo
from schema import SearchRequest, LotSearchResult, SearchResponse
from schema import BookingRequest, CreateUserRequest, CreateUserResponse, LoginRequest, LoginResponse
from schema import CancelReservationRequest, CancelReservationResponse
from backend.inventory_client import InventoryClient
from backend.pricing_client import PricingClient
from typing import List

app = FastAPI(title="Smart Parking Backend API")

inventory_client = InventoryClient()
pricing_client = PricingClient()

# This endpoint is to create a new user 
# Takes in a username and email, returns success status and user_id if successful
# Make sure to keep the user_id for future requests
# You could choose to have a user 'logged in' automatically after creation, 
# or require a separate login
@app.post("/users", response_model=CreateUserResponse)
def create_user(request: CreateUserRequest) -> CreateUserResponse:
    grpc_response = inventory_client.create_user(request.username, request.email)
    return CreateUserResponse(
        success=grpc_response.success,
        user_id=grpc_response.user_id if grpc_response.user_id else None,
        message=grpc_response.message
    )

# User login endpoint (Use Case 6)
# Takes in the same things as creating a user
# Checks in the backend if the user exists and returns success status and user_id if successful
# Make sure to keep the user_id for future requests
@app.post("/login", response_model=LoginResponse)
def login(request: LoginRequest) -> LoginResponse:
    grpc_response = inventory_client.verify_user(request.username, request.email)
    return LoginResponse(
        success=grpc_response.success,
        user_id=grpc_response.user_id if grpc_response.user_id else None,
        message=grpc_response.message if hasattr(grpc_response, 'message') else None
    )

# This is to get a list of parking lots
# My thought was that, before searching for availability, the user would see the list of parking lots with their addresses
# Then they would choose which lot to search for availability in
# Make sure to keep the lot ids for the search request later
# see the inventory_client for the exact structure of the response
@app.get("/parking-lots", response_model=List[ParkingLotInfo])
def list_parking_lots():
    # Call the inventory service via gRPC
    lots = inventory_client.list_parking_lots()
    # lots should be a list of dicts or ParkingLotInfo objects
    return lots

# This is where a user searches for available spots 
# It's set up to take a list of lot ids but it might be easier to just search one lot at a time
# See the schema for the exact structure of the request and response
# Make sure to hold onto the event id and price to use that in the booking request later
@app.post("/search", response_model=SearchResponse)
def search_lots(request: SearchRequest) -> SearchResponse:
    results = []
    for lot_id in request.lot_ids:
        occ = inventory_client.get_lot_occupancy(lot_id)
        if occ.available_spots > 0:
            price, event_id = pricing_client.get_price(lot_id, request.user_id, request.start_time, request.end_time)
            results.append(LotSearchResult(
                lot_id=lot_id,
                available_spots=occ.available_spots,
                price_per_hour=price,
                event_id=event_id,
            ))
    return SearchResponse(results=results)

# Booking endpoint
# My thought was that this would come immediately after search
# A user would search, see the results, and decide immediately to book or decline
# See the schema for the expected request format (note that the event id and price should come from the search result)
@app.post("/book")
def book_lot(request: BookingRequest):
    if request.is_booking:
        response = inventory_client.reserve_spot(
            user_id=request.user_id,
            lot_id=request.lot_id,
            event_id=request.event_id,
            start_time=request.start_time,
            end_time=request.end_time,
            price=request.price
        )
        if getattr(response, "success", False):
            return {
                "success": True,
                "spot_id": getattr(response, "spot_id", None),
                "reservation_id": getattr(response, "reservation_id", None)
            }
        else:
            return {
                "success": False,
                "failure_reason": getattr(response, "failure_reason", "Unknown error")
            }
    else:
        # Call PricingService.RecordBookingOutcome for declined booking
        pricing_response = pricing_client.record_booking_outcome(
            event_id=request.event_id,
            user_id=request.user_id,
            price_offered=request.price,
            booked=False
        )
        return {
            "success": pricing_response.success,
            "status": "declined",
            "event_id": request.event_id,
            "lot_id": request.lot_id,
            "message": getattr(pricing_response, "failure_reason", None) if not pricing_response.success else "Outcome recorded"
        }

# Endpoint to view reservations for a user
# Note the reservation_id is needed to cancel
# This should be pretty straightforward
@app.post("/reservations")
def get_user_reservations(request: UserReservationsRequest):
    response = inventory_client.list_reservations(request.user_id)
    # Parse and return the reservations as a list of dicts
    reservations = []
    for r in getattr(response, "reservations", []):
        reservations.append({
            "reservation_id": getattr(r, "reservation_id", None),
            "spot_id": getattr(r, "spot_id", None),
            "lot_id": getattr(r, "lot_id", None),
            "status": getattr(r, "status", None),
            "start_time": getattr(r, "start_time", None),
            "end_time": getattr(r, "end_time", None),
            "price_at_booking": getattr(r, "price_at_booking", None),
        })
    return {"reservations": reservations}

# Cancel reservation endpoint (Use Case 7)
# See the schema for the expected request and response format
# Note that, the backend is set up to only allow cancellations that are at least 1 hour before the reservation start time
@app.post("/cancel-reservation", response_model=CancelReservationResponse)
def cancel_reservation(request: CancelReservationRequest) -> CancelReservationResponse:
    grpc_response = inventory_client.cancel_reservation(request.user_id, request.reservation_id)
    return CancelReservationResponse(
        success=grpc_response.success,
        message=getattr(grpc_response, "message", None)
    )