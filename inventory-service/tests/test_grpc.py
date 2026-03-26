import pytest

# NOTE: Run pytest from the inventory-service root directory (not from inside tests/) to ensure imports work:
#   cd /Volumes/Logic and Other/COE892/Project/inventory-service && pytest
import pytest
import grpc
import threading
import time
from concurrent import futures
from datetime import datetime, timedelta

from inventory.generated import inventory_pb2, inventory_pb2_grpc
from inventory.server import InventoryServicer
from inventory.models import ParkingLot, ParkingSpot, Reservation
from inventory import service

# Helper to start a gRPC server in a thread for testing
def start_grpc_server(servicer, port=50055):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    inventory_pb2_grpc.add_InventoryServiceServicer_to_server(servicer, server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    return server

@pytest.fixture(scope="module")
def grpc_server():
    # Use a custom port to avoid conflicts
    port = 50055
    servicer = InventoryServicer()
    server = start_grpc_server(servicer, port)
    time.sleep(0.5)  # Give server time to start
    yield port
    server.stop(0)

@pytest.fixture()
def grpc_channel(grpc_server):
    channel = grpc.insecure_channel(f"localhost:{grpc_server}")
    yield channel
    channel.close()

def _seed_lot(session, lot_id=1, spot_count=2):
    lot = ParkingLot(lot_id=lot_id, name="Test Lot", total_spots=spot_count)
    session.add(lot)
    session.flush()
    for i in range(spot_count):
        session.add(ParkingSpot(lot_id=lot_id, label=f"A-{i+1}", status="available"))
    session.flush()

# Integration test for ReserveSpot and ListReservations
def test_reserve_and_list_reservations(grpc_channel, session):
    _seed_lot(session)
    user_id = "user-grpc"
    lot_id = 1
    spot_id = 1
    start = datetime.utcnow()
    end = start + timedelta(hours=2)
    price = 7.5

    stub = inventory_pb2_grpc.InventoryServiceStub(grpc_channel)

    # Reserve a spot
    reserve_req = inventory_pb2.ReserveSpotRequest(
        user_id=user_id,
        lot_id=str(lot_id),
        spot_id=str(spot_id),
        start_time=start.isoformat(),
        end_time=end.isoformat(),
        price_at_booking=price,
    )
    reserve_resp = stub.ReserveSpot(reserve_req)
    assert reserve_resp.reservation_id
    assert reserve_resp.status == "confirmed"
    assert float(reserve_resp.price_at_booking) == price

    # List reservations for the user
    list_req = inventory_pb2.ListReservationsRequest(user_id=user_id)
    list_resp = stub.ListReservations(list_req)
    assert len(list_resp.reservations) == 1
    res = list_resp.reservations[0]
    assert res.user_id == user_id or not hasattr(res, 'user_id')  # user_id may not be present in proto
    assert res.spot_id == str(spot_id)
    assert res.lot_id == str(lot_id)
    assert float(res.price_at_booking) == price
    assert res.status == "confirmed"
    assert res.start_time and res.end_time
