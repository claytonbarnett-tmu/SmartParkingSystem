# Smart Parking Pricing Service

This repository contains the pricing microservice for the Smart Parking System (COE892 project).

## Structure
- `architecture.md` — overall system architecture
- `COE892 - Project Proposal.*` — project proposal docs
- `pricing-service/` — pricing microservice
	 - `DESIGN.md` — service design
	 - `INTEGRATION.md` — gRPC integration guide
	 - `Dockerfile`, `docker-compose.yml` — containerization
	 - `proto/pricing.proto` — gRPC contract
	 - `scripts/run_deploy_tests.sh` — container smoke/integration test runner
	 - `tests/deploy_test.py` — container smoke/integration test client

## Quickstart
1. Create a Python venv and install requirements:
	```bash
	python -m venv .venv
	source .venv/bin/activate
	pip install -r pricing-service/requirements.txt
	pip install -r pricing-service/requirements-dev.txt
	```
2. Build and test the container:
	```bash
	cd pricing-service
	./scripts/run_deploy_tests.sh
	```

## Docs
- See `pricing-service/DESIGN.md` and `pricing-service/INTEGRATION.md` for details.