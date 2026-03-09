# Smart Parking Inventory Service

This repository contains the **Inventory Service** for the Smart Parking System. It is responsible for tracking parking spot availability (via sensor events), holding reservation state, and exposing an API for the frontend and gRPC server for the pricing server.

## Goals

- Consume sensor events (RabbitMQ) to keep spot state up to date
- Persist state in a relational database (PostgreSQL)
- Expose a **FastAPI** HTTP API for querying lots/spots and making reservations
- Expose a **gRPC** interface so pricing service can query lot occupancy

## Development

### To test the current progress, run using Docker

This is the easiest way to get the service running with Postgres.

1) Install Docker Desktop if you don’t already have it:
   - https://www.docker.com/get-started

2) Start the stack:

```bash
cd inventory-service
docker compose up --build
```

This starts:
- Postgres (named `inventory-service-postgres-1`)
- The Inventory FastAPI service (on `http://localhost:8000`)

3) Seed the database (example data):

```bash
# Connect to the running Postgres container
docker exec -it inventory-service-postgres-1 psql -U inventory -d inventory
```

Then run these SQL commands:

```sql
INSERT INTO inventory.parking_lots (lot_id, name, address, total_spots)
VALUES (1, 'Test Lot', '123 Main', 5);

INSERT INTO inventory.parking_spots (lot_id, label, status)
VALUES
  (1, 'A-1', 'available'),
  (1, 'A-2', 'available'),
  (1, 'A-3', 'available');

-- If you see a time/invalid timestamp error, update the timestamps:
UPDATE inventory.parking_spots SET last_updated = NOW();
```

Use the API (docs + endpoints):
- Open: http://localhost:8000/docs
- GET lots:  `GET /lots`
- GET occupancy:  `GET /lots/1/occupancy`
- GET spots:  `GET /lots/1/spots`

To add a reservation, use the **Try it out** button on the docs page (`POST /reservations`).