
# Smart Parking System

Distributed microservice system for real-time parking availability, dynamic pricing, and reservations. Built for COE892 (Distributed Cloud Computing).

## Architecture
- **FastAPI**: REST API gateway for frontend/mobile clients. Aggregates inventory and pricing.
- **Inventory Service**: Tracks parking lots, spots, reservations. Consumes sensor events via RabbitMQ. Exposes gRPC API.
- **Pricing Service**: RL-based dynamic pricing (multi-armed bandit). Exposes gRPC API.
- **PostgreSQL**: Persistent storage (two schemas: inventory, pricing).
- **RabbitMQ**: Event bus for simulated sensor events.
- **Mobile App**: Android client (not in this repo).

See [documentation/architecture.md](documentation/architecture.md) for diagrams and schema.

## Quickstart (Docker Compose)
1. Clone this repo.
2. Build and start all services:
	```sh
	docker compose up --build
	```
3. Seed demo data (if needed):
	```sh
	docker compose exec inventory-service python seed_demo_data.py
	docker compose exec pricing-service python seed_pricing.py
	```
4. Access FastAPI at [http://localhost:8000/docs](http://localhost:8000/docs)

## Services
- `FastAPI/` – API gateway, REST endpoints, gRPC clients
- `inventory-service/` – Inventory microservice (lots, spots, reservations)
- `pricing-service/` – Pricing microservice (RL bandit, dynamic pricing)
- `documentation/` – Architecture, use-cases, integration guides

## Documentation
- [architecture.md](documentation/architecture.md): System design, DB schema, gRPC interfaces
- [USE-CASES.md](documentation/USE-CASES.md): End-to-end flows
- [integration.md](documentation/integration.md): How services connect

## Running Tests
Run all tests with tox (requires Python 3.12):
```sh
tox
```
Or run individual tests with pytest:
```sh
pytest tests/
```

## Authors
Group 14: Alaa Yafaoui, Nafia Rahman, Andy Nguyen, Clayton Barnett
