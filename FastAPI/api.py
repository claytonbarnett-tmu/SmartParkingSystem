from fastapi import FastAPI
from schema import UserReservationsRequest
from schema import ParkingLotInfo
from schema import SearchRequest, LotSearchResult, SearchResponse
from schema import BookingRequest, CreateUserRequest, CreateUserResponse
from backend.inventory_client import InventoryClient
from backend.pricing_client import PricingClient
from typing import List

app = FastAPI(title="Smart Parking Backend API")

inventory_client = InventoryClient()
pricing_client = PricingClient()


@app.get("/parking-lots", response_model=List[ParkingLotInfo])
def list_parking_lots():
    # Call the inventory service via gRPC
    lots = inventory_client.list_parking_lots()
    # lots should be a list of dicts or ParkingLotInfo objects
    return lots

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


@app.post("/users", response_model=CreateUserResponse)
def create_user(request: CreateUserRequest) -> CreateUserResponse:
    grpc_response = inventory_client.create_user(request.username, request.email)
    return CreateUserResponse(
        success=grpc_response.success,
        user_id=grpc_response.user_id if grpc_response.user_id else None,
        message=grpc_response.message
    )

# Step 6 & 7: Booking endpoint
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
        return {
            "success": True,
            "status": "declined",
            "event_id": request.event_id,
            "lot_id": request.lot_id
        }

# Endpoint to view reservations for a user
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