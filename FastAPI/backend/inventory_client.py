# gRPC client for Inventory Service


import os
from typing import Optional
import grpc
from schema import LotOccupancyResult
from inventory_service.inventory.generated import inventory_pb2, inventory_pb2_grpc

class InventoryClient:
    def __init__(self, grpc_host: Optional[str] = None, grpc_port: Optional[int] = None):
        grpc_host = grpc_host or os.getenv("INVENTORY_GRPC_HOST", "localhost")
        grpc_port = grpc_port or int(os.getenv("INVENTORY_GRPC_PORT", 50051))
        self.channel = grpc.insecure_channel(f"{grpc_host}:{grpc_port}")
        self.stub = inventory_pb2_grpc.InventoryServiceStub(self.channel)

    def get_lot_occupancy(self, lot_id: int) -> LotOccupancyResult:
        request = inventory_pb2.GetLotOccupancyRequest(lot_id=str(lot_id))
        response = self.stub.GetLotOccupancy(request)
        return LotOccupancyResult(
            lot_id=str(response.lot_id),
            total_spots=response.total_spots,
            occupied_spots=response.occupied_spots,
            reserved_spots=response.reserved_spots,
            available_spots=response.available_spots,
        )
    def cancel_reservation(self, user_id: str, reservation_id: str):
            request = inventory_pb2.CancelReservationRequest(user_id=user_id, reservation_id=reservation_id)
            response = self.stub.CancelReservation(request)
            return response
    
    def reserve_spot(self, user_id: str, lot_id: int, event_id: str, start_time: str, end_time: str, price: float):
        request = inventory_pb2.ReserveSpotRequest(
            user_id=str(user_id),
            lot_id=str(lot_id),
            event_id=event_id,
            start_time=start_time,
            end_time=end_time,
            price_at_booking=price
        )
        response = self.stub.ReserveSpot(request)
        return response
    
    def list_reservations(self, user_id: str):
        request = inventory_pb2.ListReservationsRequest(user_id=user_id)
        response = self.stub.ListReservations(request)
        return response

    def list_parking_lots(self):
        request = inventory_pb2.ListParkingLotsRequest()
        response = self.stub.ListParkingLots(request)
        lots = []
        for lot in response.parking_lots:
            lots.append({
                "lot_id": lot.lot_id,
                "lot_name": lot.lot_name,
                "address": lot.address
            })
        return lots

    def create_user(self, username: str, email: str):
        request = inventory_pb2.CreateUserRequest(username=username, email=email)
        response = self.stub.CreateUser(request)
        return response
    
    def verify_user(self, username: str, email: str):
        request = inventory_pb2.VerifyUserRequest(username=username, email=email)
        response = self.stub.VerifyUser(request)
        return response
