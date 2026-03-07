"""gRPC server for the Pricing Service.

Run with:  python -m pricing.server
"""

import logging
import os
import signal
import sys
from concurrent import futures
from datetime import datetime
from typing import Any

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

from pricing import service
from pricing.generated import pricing_pb2_grpc  # type: ignore[attr-defined]
from pricing.generated import pricing_pb2 as _pb2  # type: ignore[attr-defined]

# Alias so the type checker treats these as Any rather than flagging every usage.
pricing_pb2: Any = _pb2

_LOG = logging.getLogger(__name__)
_PORT = os.environ.get("GRPC_PORT", "50052")


def _parse_int_id(raw: str, field_name: str, context) -> int:
    """Convert a string ID from the proto to an int primary key.

    The proto uses string IDs for forward compatibility with UUIDs.
    The current ORM uses auto-increment integers, so this helper
    bridges the two.  Remove this when migrating to UUID PKs.
    """
    try:
        return int(raw)
    except ValueError:
        context.abort(
            grpc.StatusCode.INVALID_ARGUMENT,
            f"Invalid {field_name}: expected numeric string, got {raw!r}",
        )
        raise  # unreachable — satisfies type checker


class PricingServicer(pricing_pb2_grpc.PricingServiceServicer):
    """Implements the PricingService gRPC interface."""

    def GetPrice(self, request, context):
        lot_id = _parse_int_id(request.lot_id, "lot_id", context)

        try:
            start_time = datetime.fromisoformat(request.start_time)
        except ValueError:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid start_time format")
            raise  # unreachable — satisfies type checker

        try:
            result = service.get_price(
                lot_id=lot_id,
                start_time=start_time,
                occupancy_rate=0.5,  # TODO: call Inventory Service for real occupancy
            )
        except Exception as exc:
            _LOG.exception("GetPrice failed")
            context.abort(grpc.StatusCode.INTERNAL, str(exc))
            raise  # unreachable — satisfies type checker

        return pricing_pb2.GetPriceResponse(
            price_per_hour=result.final_price,
            event_id=str(result.event_id),
            context_key=result.context_key,
            base_price=result.base_price,
            multiplier=result.multiplier,
        )

    def RecordBookingOutcome(self, request, context):
        event_id = _parse_int_id(request.event_id, "event_id", context)

        try:
            if request.booked:
                service.confirm_booking(event_id)
            else:
                service.cancel_booking(event_id)
        except Exception as exc:
            _LOG.exception("RecordBookingOutcome failed")
            context.abort(grpc.StatusCode.INTERNAL, str(exc))
            raise  # unreachable — satisfies type checker

        return pricing_pb2.RecordBookingOutcomeResponse(success=True)


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    pricing_pb2_grpc.add_PricingServiceServicer_to_server(PricingServicer(), server)

    # gRPC health check
    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    health_servicer.set("parking.pricing.PricingService", health_pb2.HealthCheckResponse.SERVING)

    server.add_insecure_port(f"[::]:{_PORT}")
    server.start()
    _LOG.info("Pricing service listening on port %s", _PORT)

    # Graceful shutdown on SIGTERM
    def _stop(signum, frame):
        _LOG.info("Shutting down…")
        server.stop(grace=5)

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    server.wait_for_termination()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    serve()
