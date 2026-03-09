"""gRPC server for the Inventory Service.

Run with:
    python -m inventory.server
"""
import os
import signal
import sys
from concurrent import futures
from typing import Any

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

from inventory import service
from inventory.generated import inventory_pb2_grpc 
from inventory.generated import inventory_pb2 as _pb2

inventory_pb2: Any = _pb2

_PORT = os.environ.get("GRPC_PORT", "50051")


def _parse_int_id(raw: str, field_name: str, context) -> int:
    try:
        return int(raw)
    except ValueError:
        context.abort(
            grpc.StatusCode.INVALID_ARGUMENT,
            f"Invalid {field_name}: expected numeric string, got {raw!r}",
        )
        raise


class InventoryServicer(inventory_pb2_grpc.InventoryServiceServicer):
    def GetLotOccupancy(self, request, context):
        lot_id = _parse_int_id(request.lot_id, "lot_id", context)
        try:
            occupancy = service.get_lot_occupancy(lot_id)
        except Exception as exc:
            context.abort(grpc.StatusCode.INTERNAL, str(exc))
            raise

        return inventory_pb2.GetLotOccupancyResponse(
            lot_id=str(occupancy["lot_id"]),
            total_spots=occupancy["total_spots"],
            occupied_spots=occupancy["occupied_spots"],
            reserved_spots=occupancy["reserved_spots"],
            available_spots=occupancy["available_spots"],
        )

    def ListSpots(self, request, context):
        lot_id = _parse_int_id(request.lot_id, "lot_id", context)
        try:
            spots = service.list_spots(lot_id)
        except Exception as exc:
            context.abort(grpc.StatusCode.INTERNAL, str(exc))
            raise

        return inventory_pb2.ListSpotsResponse(
            spots=[
                inventory_pb2.SpotStatus(
                    spot_id=str(s.spot_id),
                    label=s.label or "",
                    status=s.status,
                    last_updated=s.last_updated.isoformat() if s.last_updated else "",
                )
                for s in spots
            ]
        )


def serve() -> None:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    inventory_pb2_grpc.add_InventoryServiceServicer_to_server(InventoryServicer(), server)

    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    health_servicer.set("parking.inventory.InventoryService", health_pb2.HealthCheckResponse.SERVING)

    server.add_insecure_port(f"[::]:{_PORT}")
    server.start()

    def _stop(signum, frame):
        server.stop(grace=5)

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
