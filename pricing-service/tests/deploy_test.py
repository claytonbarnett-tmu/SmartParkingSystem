"""Smoke tests for the containerised Pricing gRPC service.

Run against a live container (see scripts/run_smoke_tests.sh).
Expects:
  - gRPC server at localhost:50052
  - Lot 1 already seeded via the seed step in the runner script
"""

import sys

import grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc

# The generated stubs live inside the pricing package on disk.
# Add the repo root so "pricing.generated" is importable.
sys.path.insert(0, ".")

from pricing.generated import pricing_pb2_grpc          # type: ignore[attr-defined]
from pricing.generated import pricing_pb2 as pricing_pb2  # type: ignore[attr-defined]

GRPC_TARGET = "localhost:50052"
PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"


def _channel():
    return grpc.insecure_channel(GRPC_TARGET)


# ── individual checks ────────────────────────────────────────


def check_health(channel) -> bool:
    stub = health_pb2_grpc.HealthStub(channel)
    resp = stub.Check(health_pb2.HealthCheckRequest(
        service="parking.pricing.PricingService",
    ))
    ok = resp.status == health_pb2.HealthCheckResponse.SERVING
    print(f"  Health check: {PASS if ok else FAIL}")
    return ok


def check_get_price(channel) -> dict:
    stub = pricing_pb2_grpc.PricingServiceStub(channel)
    resp = stub.GetPrice(pricing_pb2.GetPriceRequest(
        lot_id="1",
        user_id="42",
        start_time="2026-03-04T09:00:00",
        end_time="2026-03-04T10:00:00",
        occupancy_rate=0.5,
    ))
    ok = (
        resp.price_per_hour > 0
        and resp.event_id != ""
        and resp.context_key != ""
        and resp.base_price > 0
        and resp.multiplier > 0
    )
    print(f"  GetPrice:     {PASS if ok else FAIL}  "
          f"(price={resp.price_per_hour:.2f}, ctx={resp.context_key})")
    return {"ok": ok, "event_id": resp.event_id, "price": resp.price_per_hour}


def check_record_booked(channel, event_id: str) -> bool:
    stub = pricing_pb2_grpc.PricingServiceStub(channel)
    resp = stub.RecordBookingOutcome(
        pricing_pb2.RecordBookingOutcomeRequest(event_id=event_id, booked=True)
    )
    ok = resp.success is True
    print(f"  RecordBooked: {PASS if ok else FAIL}")
    return ok


def check_record_not_booked(channel) -> bool:
    """Get a fresh price, then cancel it."""
    stub = pricing_pb2_grpc.PricingServiceStub(channel)

    price_resp = stub.GetPrice(pricing_pb2.GetPriceRequest(
        lot_id="1",
        user_id="42",
        start_time="2026-03-04T14:00:00",
        end_time="2026-03-04T15:00:00",
    ))
    resp = stub.RecordBookingOutcome(
        pricing_pb2.RecordBookingOutcomeRequest(
            event_id=price_resp.event_id, booked=False,
        )
    )
    ok = resp.success is True
    print(f"  RecordCancel: {PASS if ok else FAIL}")
    return ok


def check_invalid_lot(channel) -> bool:
    """GetPrice for an unseeded lot should return an INTERNAL error."""
    stub = pricing_pb2_grpc.PricingServiceStub(channel)
    try:
        stub.GetPrice(pricing_pb2.GetPriceRequest(
            lot_id="9999",
            user_id="1",
            start_time="2026-03-04T09:00:00",
            end_time="2026-03-04T10:00:00",
        ))
        print(f"  InvalidLot:   {FAIL}  (expected error, got success)")
        return False
    except grpc.RpcError as e:
        ok = e.code() in (grpc.StatusCode.INTERNAL, grpc.StatusCode.NOT_FOUND)
        print(f"  InvalidLot:   {PASS if ok else FAIL}  (code={e.code().name})")
        return ok


def check_bad_id(channel) -> bool:
    """Non-numeric lot_id should return INVALID_ARGUMENT."""
    stub = pricing_pb2_grpc.PricingServiceStub(channel)
    try:
        stub.GetPrice(pricing_pb2.GetPriceRequest(
            lot_id="not-a-number",
            user_id="1",
            start_time="2026-03-04T09:00:00",
            end_time="2026-03-04T10:00:00",
        ))
        print(f"  BadId:        {FAIL}  (expected error, got success)")
        return False
    except grpc.RpcError as e:
        ok = e.code() == grpc.StatusCode.INVALID_ARGUMENT
        print(f"  BadId:        {PASS if ok else FAIL}  (code={e.code().name})")
        return ok


# ── runner ────────────────────────────────────────────────────


def main():
    print(f"\nSmoke tests against {GRPC_TARGET}\n")

    with _channel() as ch:
        results = [
            check_health(ch),
            check_bad_id(ch),
            check_invalid_lot(ch),
        ]

        gp = check_get_price(ch)
        results.append(gp["ok"])

        results.append(check_record_booked(ch, gp["event_id"]))
        results.append(check_record_not_booked(ch))

    passed = sum(results)
    total = len(results)
    print(f"\n{passed}/{total} checks passed.\n")

    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
