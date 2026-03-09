# Inventory Service Design

This document describes the high-level design of the Inventory Service for the
Smart Parking System.

## Responsibilities

- **Track parking spot availability** via incoming sensor events.
- **Persist state** in a relational database.
- **Expose a FastAPI HTTP API** for the front-end to query lot/spot state and make reservations.
- **Expose a gRPC API** so pricing service can query current occupancy.

## Data Model

The service stores:

- **Parking lots**
- **Parking spots** with status `available | occupied | reserved`
- **Reservations** with time ranges and a link to the user who made them
- **Users**

## Sensor Integration

Sensor events (from RabbitMQ) are consumed by `inventory.consumer`. Each
message should contain:

```json
{
  "lot_id": 1,
  "spot_id": 42,
  "status": "occupied"  // or "available"
}
```

The consumer updates the corresponding spot status in the database.

## Reservation Logic

Reservations are enforced by:

- Only allowing reservations on spots currently marked `available`.
- Rejecting overlaps by checking for confirmed reservations on the same spot with
  intersecting time ranges.
- Transitioning the spot to `reserved` when a reservation is confirmed.

## gRPC Contract

The gRPC interface is defined in `proto/inventory.proto`. It provides:

- `GetLotOccupancy` — occupancy counts for a lot
- `ListSpots` — current status for all spots in a lot

This lets the Pricing Service request the current occupancy to compute a pricing context.
