# Pricing Service — gRPC Integration Guide

> **Owner:** Pricing Service team  
> **Audience:** FastAPI / Mobile App, Inventory Service, Docker / RabbitMQ

This document describes how other services communicate with the Pricing Service over gRPC, and what each teammate needs to know to integrate correctly.

---

## 1. Overview

The Pricing Service is a gRPC server that provides **dynamic pricing** for parking reservations using a contextual multi-armed bandit (Thompson sampling). It exposes two RPCs:

| RPC | Caller | Purpose |
|-----|--------|---------|
| `GetPrice` | FastAPI | Get a dynamically computed hourly price for a lot |
| `RecordBookingOutcome` | FastAPI | Tell the service whether the user booked or abandoned |

The service also makes an **outbound gRPC call** to the Inventory Service to retrieve lot occupancy, which is one of the inputs to the pricing algorithm.

```
Mobile App ──REST──▶ FastAPI ──gRPC──▶ Pricing Service
                                           │
                                           ├──gRPC──▶ Inventory Service (GetLotOccupancy)
                                           │
                                           ▼
                                      PostgreSQL (pricing schema)
```

---

## 2. Protobuf Service Definition

The `.proto` file below is the **contract** between the FastAPI gateway and the Pricing Service.

```protobuf
syntax = "proto3";

package parking.pricing;

service PricingService {
  // Phase 1: Request a price quote.
  rpc GetPrice (GetPriceRequest) returns (GetPriceResponse);

  // Phase 2: Report whether the user booked or not.
  rpc RecordBookingOutcome (RecordBookingOutcomeRequest) returns (RecordBookingOutcomeResponse);
}

// ─── GetPrice ────────────────────────────────────────────────

message GetPriceRequest {
  string lot_id   = 1;  // UUID of the parking lot
  string user_id  = 2;  // UUID of the requesting user (for future personalization)
  string start_time = 3;  // ISO-8601 datetime, e.g. "2026-03-07T14:00:00"
  string end_time   = 4;  // ISO-8601 datetime
}

message GetPriceResponse {
  double price_per_hour = 1;  // Final offered price (base_price × multiplier)
  string event_id       = 2;  // UUID — must be sent back in RecordBookingOutcome
  string context_key    = 3;  // Human-readable context label (for debugging)
  double base_price     = 4;  // Lot's configured base price
  double multiplier     = 5;  // Multiplier chosen by the bandit (e.g. 1.15)
}

// ─── RecordBookingOutcome ────────────────────────────────────

message RecordBookingOutcomeRequest {
  string event_id = 1;  // The event_id returned by GetPrice
  bool   booked   = 2;  // true = user confirmed; false = user abandoned
}

message RecordBookingOutcomeResponse {
  bool success = 1;
}
```

### Key points

- **`event_id` is the link between the two RPCs.** Every `GetPrice` call creates a pricing event. That `event_id` must be forwarded back via `RecordBookingOutcome` once the user decides.
- `user_id` is accepted but not yet used in pricing decisions. It is stored for future personalization.
- Timestamps are ISO-8601 strings (not protobuf `Timestamp`), to keep the proto simple. The service parses `start_time` to derive the pricing context.

---

## 3. Call Flow

### 3a. Happy path — user books

```
FastAPI                          Pricing Service            Inventory Service
  │                                    │                           │
  │── GetPrice(lot_id, user_id, ──────▶│                           │
  │   start_time, end_time)            │── GetLotOccupancy(lot_id)▶│
  │                                    │◀── occupancy_rate ────────│
  │                                    │                           │
  │                                    │ (Thompson sampling runs)  │
  │◀── price_per_hour, event_id ───────│                           │
  │                                    │                           │
  │  (user sees price, taps "Book")    │                           │
  │                                    │                           │
  │── RecordBookingOutcome ───────────▶│                           │
  │   (event_id, booked=true)          │ (updates α, β)           │
  │◀── success=true ──────────────────│                           │
```

### 3b. User abandons

Same as above, except:
- `booked = false` is sent in `RecordBookingOutcome`
- The bandit increments `β += 1` (penalizes the chosen price)

### 3c. What if `RecordBookingOutcome` is never called?

The pricing event stays in the database with `booked = NULL`. The bandit parameters are **not** updated. This is safe but means the algorithm does not learn from that interaction — so the FastAPI layer should always call `RecordBookingOutcome`, even on timeouts or errors.

---

## 4. What the Pricing Algorithm Needs From Inventory Service

The Pricing Service needs to call the Inventory Service to get the current occupancy rate for a lot before it can price it.

### Required RPC

```protobuf
service InventoryService {
  rpc GetLotOccupancy (GetLotOccupancyRequest) returns (GetLotOccupancyResponse);
}

message GetLotOccupancyRequest {
  string lot_id = 1;
}

message GetLotOccupancyResponse {
  double occupancy_rate = 0;  // 0.0 to 1.0 (fraction of spots occupied)
}
```

The occupancy rate is bucketed into three levels to form the pricing context:

| Bucket | Range |
|--------|-------|
| `low` | < 30% occupied |
| `medium` | 30–70% occupied |
| `high` | > 70% occupied |

If the Inventory Service is unreachable, the Pricing Service will fall back to `medium` occupancy (50%) so it can still return a price.

---

## 5. Initializing a New Lot

Before the Pricing Service can price a lot, that lot must be initialized. This seeds 144 bandit arms (6 multipliers × 24 context combinations) with uniform priors.

**This must happen once per lot**, either:
- At system startup via a seed script, or
- Via an internal admin RPC / CLI command

```python
# Example: initialize lot with $4.00 base price
from pricing.service import initialize_lot
initialize_lot(lot_id="lot-uuid-here", base_price=4.00)
```

The operation is **idempotent** — calling it again for the same lot will not duplicate arms.

### Default multipliers

| Multiplier | Meaning |
|------------|---------|
| 0.70 | 30% discount |
| 0.85 | 15% discount |
| 1.00 | Base price |
| 1.15 | 15% surge |
| 1.30 | 30% surge |
| 1.50 | 50% surge |

With a base price of $4.00, the service can offer prices from **$2.80/hr** to **$6.00/hr**.

---

## 6. Database Requirements

The Pricing Service requires a PostgreSQL database with a `pricing` schema. The schema is created automatically on startup.

### Connection

| Variable | Default |
|----------|---------|
| `DATABASE_URL` | `postgresql://parking:parking@localhost:5432/parking` |

The service expects the same PostgreSQL instance as the Inventory Service (different schema). Docker Compose should expose a single `postgres` service that both microservices connect to.

### Tables created automatically

| Table | Purpose |
|-------|---------|
| `pricing.bandit_arms` | Beta(α, β) parameters per (lot, context, multiplier) |
| `pricing.lot_pricing_config` | Base price per lot |
| `pricing.pricing_events` | Audit log of every pricing decision |

### Storage estimate

Per lot: ~144 arm rows + 1 config row. Event rows grow with traffic but are append-only.

---

## 7. Docker / Deployment Notes

### Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `GRPC_PORT` | No | Port for the gRPC server (default: `50052`) |
| `INVENTORY_SERVICE_HOST` | Yes | Hostname of the Inventory Service gRPC server |
| `INVENTORY_SERVICE_PORT` | No | Port of the Inventory Service gRPC server (default: `50051`) |

### Python dependencies

```
sqlalchemy>=2.0,<3.0
psycopg2-binary>=2.9,<3.0
numpy>=1.24,<3.0
grpcio>=1.60
grpcio-tools>=1.60
```

`grpcio` and `grpcio-tools` will be added to `requirements.txt` once the gRPC layer is implemented.

### Docker Compose service sketch

```yaml
pricing-service:
  build: ./pricing-service
  environment:
    DATABASE_URL: postgresql://parking:parking@postgres:5432/parking
    INVENTORY_SERVICE_HOST: inventory-service
  ports:
    - "50052:50052"
  depends_on:
    - postgres
    - inventory-service
```

### Health / readiness

The service is ready to accept RPCs once it can connect to PostgreSQL and the `pricing` schema exists. A gRPC health check will be added.

---

## 8. Error Handling

| Scenario | gRPC Status | Notes |
|----------|-------------|-------|
| Lot not initialized | `NOT_FOUND` | Call `initialize_lot` first |
| Invalid `event_id` in `RecordBookingOutcome` | `NOT_FOUND` | Event UUID doesn't exist |
| Inventory Service unreachable | (transparent) | Falls back to medium occupancy; still returns a price |
| Database unreachable | `UNAVAILABLE` | Retry with backoff |

---

## 9. Quick Reference for FastAPI Integration

### Calling `GetPrice`

```python
import grpc
from parking.pricing import pricing_pb2, pricing_pb2_grpc

channel = grpc.insecure_channel("pricing-service:50052")
stub = pricing_pb2_grpc.PricingServiceStub(channel)

response = stub.GetPrice(pricing_pb2.GetPriceRequest(
    lot_id="lot-uuid",
    user_id="user-uuid",
    start_time="2026-03-07T14:00:00",
    end_time="2026-03-07T16:00:00",
))

price = response.price_per_hour   # e.g. 4.60
event_id = response.event_id      # save this!
```

### Reporting the outcome

```python
# After user confirms or abandons:
stub.RecordBookingOutcome(pricing_pb2.RecordBookingOutcomeRequest(
    event_id=event_id,
    booked=True,  # or False
))
```

### REST endpoint shape (suggestion)

```
GET /lots/{lot_id}/price?start=2026-03-07T14:00:00&end=2026-03-07T16:00:00
→ { "price_per_hour": 4.60, "event_id": "uuid", "base_price": 4.00, "multiplier": 1.15 }

POST /bookings/{event_id}/confirm
POST /bookings/{event_id}/cancel
```

---

## 10. Summary of Responsibilities

| Team / Role | Action items |
|-------------|-------------|
| **FastAPI / Mobile App** | Call `GetPrice` from FastAPI on price-check; call `RecordBookingOutcome` on book/abandon; surface price in the mobile app |
| **Inventory Service** | Expose `GetLotOccupancy` RPC returning a 0–1 float; ensure lot UUIDs are consistent across services |
| **Docker / Infra** | Add `pricing-service` to Docker Compose; share a single Postgres instance; set environment variables |
| **Pricing Service** | Implement the gRPC server wrapper, generate proto stubs, add health check |
