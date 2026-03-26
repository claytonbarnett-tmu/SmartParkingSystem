# Integration Guide

This document outlines the requirements for each component in the Smart Parking System to connect to the other components it depends on. It also answers key questions about what information is needed for integration, and who is responsible for providing it. Any open questions are listed at the end.

## 1. Frontend Mobile App
- **Connections:** Connects to FastAPI via REST.
- **Needs to Know:**
  - The HTTPS (or HTTP for local/dev) URL of the FastAPI server (e.g., `https://api.smartparking.com` or `http://localhost:8000`).
  - Any authentication tokens or credentials required by the API (if applicable).
- **Who Provides:**
  - The FastAPI team is responsible for providing the API endpoint URL and documentation for authentication (if any).

## 2. Pricing Service
- **Connections:**
  - Connects to Inventory Service via gRPC
  - Connects to FastAPI via gRPC
  - Connects to PostgreSQL database
- **Needs to Know:**
  - **gRPC Connections:**
    - The host (IP or DNS name) and port where the other service's gRPC server is running (e.g., `inventory-service:50051`).
    - The `.proto` file definitions for the service interface (shared between both services).
    - Any authentication or TLS configuration (if using secure gRPC).
  - **Database Connection:**
    - Host, port, database name, username, and password for the PostgreSQL instance.
    - If running in the same container: typically `localhost` and the exposed port.
    - If running in a different container: the service name or network alias (e.g., `postgres:5432`).
- **Who Provides:**
  - The service being connected to (e.g., Inventory Service, FastAPI, or the DB admin) provides the host, port, and credentials.
  - The DevOps or deployment team is responsible for configuring environment variables or service discovery.

## 3. Inventory Service
- **Connections:**
  - Connects to Pricing Service via gRPC
  - Connects to FastAPI via gRPC
  - Subscribes to RabbitMQ (channel: `parking_events`)
  - Connects to PostgreSQL database
- **Needs to Know:**
  - **gRPC:** Same as above (host, port, proto definitions, auth/TLS if used).
  - **RabbitMQ:**
    - The RabbitMQ server URL (e.g., `amqp://rabbitmq:5672`)
    - The queue or exchange name (`parking_events`)
    - Expected message format/schema (should be documented/shared)
    - Any credentials if RabbitMQ is secured
  - **Database:** Same as above (host, port, db name, user, password)
- **Who Provides:**
  - The RabbitMQ admin provides the server URL, credentials, and channel names.
  - The service being connected to provides gRPC details.
  - The DB admin provides database connection info.

## 4. FastAPI
- **Connections:**
  - Serves REST API to Frontend
  - Connects to Inventory and Pricing Service via gRPC
- **Needs to Know:**
  - **REST:**
    - The public URL where FastAPI is accessible (provided to the mobile app team)
    - Any authentication requirements
  - **gRPC:**
    - Host and port for Inventory and Pricing Service gRPC servers
    - Proto definitions
    - Auth/TLS config if used
- **Who Provides:**
  - FastAPI team provides REST API details to frontend.
  - Inventory and Pricing Service teams provide gRPC details.

## 5. RabbitMQ
- **Connections:**
  - Receives messages from sensor simulation program (publishers)
  - Sends messages to Inventory Service (subscriber)
- **Needs to Know / Provide:**
  - **For Publishers/Subscribers:**
    - The RabbitMQ server URL and port
    - Credentials (if any)
    - The queue/exchange name(s) to publish/subscribe to
    - Message format/schema
- **Who Provides:**
  - RabbitMQ admin provides connection details and credentials to all clients (publishers/subscribers).
  - Message format should be agreed upon and documented by all parties.

---


## Central Connection Variables

All connection variables and proto definitions are documented here. The shared proto files are located in the `/proto` folder at the top level of the repository.

### FastAPI
- **REST API Host:** `http://localhost:8000/` (local dev; replace with public IP/DNS in production)
- **How to set:**
  - In Docker Compose: expose port 8000 (`ports: ["8000:8000"]`)
  - In Uvicorn: `uvicorn inventory.api:app --host 0.0.0.0 --port 8000`
- **Who provides:** FastAPI maintainer

### Pricing Service
- **gRPC Host:** `pricing-service:50051` (Docker Compose service name and port)
- **How to set:**
  - In server code: `server.add_insecure_port('[::]:50051')`
  - In Docker Compose: expose port 50051 (`ports: ["50051:50051"]`)
- **Proto file:** `/proto/pricing.proto`
- **Who provides:** Pricing service maintainer

### Inventory Service
- **gRPC Host:** `inventory-service:50052` (example; check actual port in compose/server)
- **How to set:**
  - In server code: `server.add_insecure_port('[::]:50052')` (or as configured)
  - In Docker Compose: expose port 50052 (`ports: ["50052:50052"]`)
- **Proto file:** `/proto/inventory.proto`
- **Who provides:** Inventory service maintainer

### Shared Proto Files
- All .proto files are stored in `/proto` at the project root.
- All services should reference these files for gRPC interface definitions.

### Example Docker Compose Service Definitions

```yaml
services:
  fastapi:
    build: ./FastAPI
    ports:
      - "8000:8000"
  pricing-service:
    build: ./pricing-service
    ports:
      - "50051:50051"
    volumes:
      - ./proto:/proto
  inventory-service:
    build: ./inventory-service
    ports:
      - "50052:50052"
    volumes:
      - ./proto:/proto
```

Update this section as connection details change.