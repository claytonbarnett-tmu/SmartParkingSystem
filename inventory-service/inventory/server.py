import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
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
from inventory.service import list_spots

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

    def CancelReservation(self, request, context):
        user_id = request.user_id
        reservation_id = request.reservation_id
        success, message = service.cancel_reservation(user_id, reservation_id)
        return inventory_pb2.CancelReservationResponse(
            success=success,
            message=message or ""
        )

    def CreateUser(self, request, context):
        username = request.username
        email = request.email
        success, user_id, message = service.create_user(username, email)
        return inventory_pb2.CreateUserResponse(
            success=success,
            user_id=user_id or "",
            message=message or ""
        )

    def ListParkingLots(self, request, context):
        try:
            lots = service.list_lots()
        except Exception as exc:
            context.abort(grpc.StatusCode.INTERNAL, str(exc))
            raise

        return inventory_pb2.ListParkingLotsResponse(
            parking_lots=[
                inventory_pb2.ParkingLotInfo(
                    lot_id=str(lot.lot_id),
                    lot_name=getattr(lot, "name", ""),
                    address=getattr(lot, "address", "") or ""
                )
                for lot in lots
            ]
        )
    def ListReservations(self, request, context):
        user_id = request.user_id
        try:
            reservations = service.list_reservations(user_id)
        except Exception as exc:
            context.abort(grpc.StatusCode.INTERNAL, str(exc))
            raise

        return inventory_pb2.ListReservationsResponse(
            reservations=[
                inventory_pb2.ReservationInfo(
                    reservation_id=str(r.reservation_id),
                    spot_id=str(r.spot_id),
                    lot_id=str(r.lot_id),
                    status=getattr(r, "status", None),
                    start_time=(r.start_time.isoformat() if getattr(r, "start_time", None) is not None else ""),
                    end_time=(r.end_time.isoformat() if getattr(r, "end_time", None) is not None else ""),
                    price_at_booking=float(getattr(r, "price_at_booking", 0.0) or 0.0),
                )
                for r in reservations
            ]
        )
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
                    label=getattr(s, "label", "") or "",
                    status=getattr(s, "status", None),
                    last_updated=(s.last_updated.isoformat() if getattr(s, "last_updated", None) is not None else ""),
                )
                for s in spots
            ]
        )

    def VerifyUser(self, request, context):
        username = request.username
        email = request.email
        success, user_id, message = service.verify_user(username, email)
        return inventory_pb2.VerifyUserResponse(
            success=success,
            user_id=user_id or "",
            message=message or ""
        )

    def ReserveSpot(self, request, context):
        lot_id = _parse_int_id(request.lot_id, "lot_id", context)
        spot_id = None
        failure_reason = ""
        try:
            # Auto-assign an available spot if spot_id is missing/empty
            if spot_id is None:
                available_spots = list_spots(lot_id, status="available")
                if not available_spots:
                    logger.error(f"No available spots in lot {lot_id}")
                    failure_reason = "No available spots in lot"
                    return inventory_pb2.ReserveSpotResponse(success=False, failure_reason=failure_reason)
                raw_spot_id = getattr(available_spots[0], "spot_id", None)
                if raw_spot_id is None:
                    logger.error(f"Auto-assigned spot has no spot_id for lot {lot_id}")
                    failure_reason = "Auto-assigned spot has no spot_id"
                    return inventory_pb2.ReserveSpotResponse(success=False, failure_reason=failure_reason)
                spot_id = int(raw_spot_id)

            # Require event_id for pricing validation
            if not hasattr(request, "event_id") or not request.event_id:
                logger.error("event_id is required for pricing validation but missing in request")
                failure_reason = "event_id is required for pricing validation"
                return inventory_pb2.ReserveSpotResponse(success=False, failure_reason=failure_reason)

            price = request.price_at_booking if request.HasField("price_at_booking") else None
            reservation = service.reserve_spot_grpc(
                user_id=request.user_id,
                lot_id=lot_id,
                spot_id=spot_id,
                start_time=request.start_time,
                end_time=request.end_time,
                price_at_booking=price,
                event_id=request.event_id,
            )
            return inventory_pb2.ReserveSpotResponse(
                success=True,
                reservation_id=str(reservation.reservation_id),
                spot_id=str(reservation.spot_id),
                lot_id=str(reservation.lot_id),
                user_id=getattr(reservation, "user_id", None),
                status=getattr(reservation, "status", None),
                start_time=(reservation.start_time.isoformat() if getattr(reservation, "start_time", None) is not None else ""),
                end_time=(reservation.end_time.isoformat() if getattr(reservation, "end_time", None) is not None else ""),
                price_at_booking=float(getattr(reservation, "price_at_booking", 0.0) or 0.0),
                failure_reason=""
            )
        except ValueError as exc:
            logger.error(f"ReserveSpot ValueError: {exc}")
            failure_reason = str(exc)
            return inventory_pb2.ReserveSpotResponse(success=False, failure_reason=failure_reason)
        except Exception as exc:
            logger.exception(f"ReserveSpot Exception: {exc}")
            failure_reason = str(exc)
            return inventory_pb2.ReserveSpotResponse(success=False, failure_reason=failure_reason)


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
