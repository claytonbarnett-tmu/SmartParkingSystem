# Smart Parking System — Architecture Document

## 1. System Overview

This document extends the original project proposal to incorporate two missing architectural elements:

1. **A database layer** — persistent storage for parking lots, spots, reservations, and pricing data.
2. **An RL-based dynamic pricing engine** — a contextual multi-armed bandit with Thompson sampling.

The system remains a microservice architecture. Each service communicates via gRPC (synchronous) or RabbitMQ (asynchronous events).

### Updated Component Map

```
┌────────────┐         ┌───────────┐
│ Mobile App │──REST──▶│  FastAPI   │
└────────────┘         └─────┬─────┘
                             │ gRPC
                    ┌────────┴────────┐
                    ▼                 ▼
            ┌──────────────┐  ┌──────────────┐
            │  Inventory   │  │   Pricing    │
            │   Service    │◀─│   Service    │
            └──────┬───────┘  └──────┬───────┘
                   │  gRPC           │
                   │                 │
            ┌──────▼───────┐  ┌──────▼───────┐
            │  PostgreSQL  │  │  PostgreSQL  │
            │ (inventory)  │  │  (pricing)   │
            └──────────────┘  └──────────────┘
                   ▲
                   │ consume
            ┌──────┴───────┐
            │  RabbitMQ    │◀── Simulated Sensors
            └──────────────┘
```

> **Note on DB topology:** The two PostgreSQL boxes above can be two schemas/databases inside a single Postgres container, or two separate containers. For a course project a single Postgres container with two schemas (`inventory`, `pricing`) is simplest while still keeping data ownership clear between services.

---

## 2. Database Design

### 2.1 Why a Database?

The original proposal has the Inventory Service "hold and organize the state" but doesn't specify how state persists across restarts. A database is needed to:

- Persist parking spot states and reservations beyond process lifetime.
- Support concurrency-safe reservation logic (double-booking prevention via row-level locks / unique constraints).
- Store historical pricing and reward data for the RL agent.

### 2.2 Schema — `inventory` (owned by Inventory Service)

Expanded from the teammate's schema to support **multiple parking lots**.

```sql
-- inventory schema

CREATE TABLE users (
    user_id     VARCHAR(64) PRIMARY KEY,   -- opaque ID (e.g. UUID or Firebase UID)
    display_name VARCHAR(128),
    email       VARCHAR(256),
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE parking_lots (
    lot_id        SERIAL PRIMARY KEY,
    name          VARCHAR(128) NOT NULL,
    address       TEXT,
    total_spots   INT NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE parking_spots (
    spot_id       SERIAL PRIMARY KEY,
    lot_id        INT NOT NULL REFERENCES parking_lots(lot_id),
    label         VARCHAR(32),                          -- e.g. "A-12"
    status        VARCHAR(16) NOT NULL DEFAULT 'available'
                      CHECK (status IN ('available', 'occupied', 'reserved')),
    last_updated  TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_spots_lot_status ON parking_spots(lot_id, status);

CREATE TABLE reservations (
    reservation_id  SERIAL PRIMARY KEY,
    spot_id         INT NOT NULL REFERENCES parking_spots(spot_id),
    lot_id          INT NOT NULL REFERENCES parking_lots(lot_id),
    user_id         VARCHAR(64) NOT NULL REFERENCES users(user_id),
    status          VARCHAR(16) NOT NULL DEFAULT 'confirmed'
                        CHECK (status IN ('confirmed', 'cancelled', 'expired', 'completed')),
    created_at      TIMESTAMPTZ DEFAULT now(),
    start_time      TIMESTAMPTZ NOT NULL,
    end_time        TIMESTAMPTZ NOT NULL,
    price_at_booking NUMERIC(8,2) NOT NULL
);
CREATE INDEX idx_reservations_lot ON reservations(lot_id, status);
CREATE INDEX idx_reservations_spot_time ON reservations(spot_id, start_time, end_time);
```

**Key changes vs. teammate's original schema:**
- Added `parking_lots` table — supports multiple lots.
- Added `users` table — minimal, just enough to give `reservations.user_id` a FK target.
- `parking_spots` and `reservations` both carry a `lot_id` FK.
- Indexes support per-lot queries (occupancy counts, availability).

**Note on `users`:** This table is intentionally minimal. For a course project we don't need password hashing, OAuth flows, etc. The mobile app (Alaa's domain) can generate a UUID on first launch and register it via a simple `POST /users` endpoint on FastAPI. That UUID then travels with every reservation request. If the team later wants login/auth, the table is already there to attach to.

### 2.3 Schema — `pricing` (owned by Pricing Service)

These tables store the state of the RL agent and a log of every pricing decision and its outcome.

```sql
-- pricing schema

-- Each row is one "arm" in a specific context.
-- Context = (lot, time-of-day bucket, day-type, occupancy bucket).
-- Arms are price *multipliers* applied to a heuristic base price.
CREATE TABLE bandit_arms (
    arm_id        SERIAL PRIMARY KEY,
    lot_id        INT NOT NULL,
    context_key   VARCHAR(64) NOT NULL,   -- encoded context, e.g. "morning:weekday:high"
    multiplier    NUMERIC(4,2) NOT NULL,  -- e.g. 0.8, 1.0, 1.2, 1.5
    alpha         DOUBLE PRECISION NOT NULL DEFAULT 1.0,  -- Beta dist param
    beta          DOUBLE PRECISION NOT NULL DEFAULT 1.0,  -- Beta dist param
    total_pulls   INT NOT NULL DEFAULT 0,
    total_revenue DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    updated_at    TIMESTAMPTZ DEFAULT now(),
    UNIQUE (lot_id, context_key, multiplier)
);

-- Per-lot configuration: base price and ceiling for normalization.
CREATE TABLE lot_pricing_config (
    lot_id        INT PRIMARY KEY,
    base_price    NUMERIC(8,2) NOT NULL DEFAULT 4.00,  -- heuristic base $/hr
    updated_at    TIMESTAMPTZ DEFAULT now()
);

-- Append-only log of every price offered and whether it converted.
CREATE TABLE pricing_events (
    event_id        SERIAL PRIMARY KEY,
    lot_id          INT NOT NULL,
    arm_id          INT REFERENCES bandit_arms(arm_id),
    context_key     VARCHAR(64) NOT NULL,
    base_price      NUMERIC(8,2) NOT NULL,
    multiplier      NUMERIC(4,2) NOT NULL,
    price_offered   NUMERIC(8,2) NOT NULL,  -- base_price × multiplier
    booked          BOOLEAN NOT NULL DEFAULT FALSE,
    reward          DOUBLE PRECISION DEFAULT 0.0, -- normalized revenue: booked × (price / ceiling)
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_pricing_events_lot ON pricing_events(lot_id, created_at);
```

---

## 3. RL Dynamic Pricing — Multi-Armed Bandit with Thompson Sampling

### 3.1 Formulation

| Concept | Mapping |
|---|---|
| **Arms** | Price *multipliers* applied to a heuristic base price (e.g. ×0.7, ×0.85, ×1.0, ×1.15, ×1.3, ×1.5) |
| **Context** | `(lot_id, time_bucket, day_type, occupancy_bucket)` |
| **Reward** | Revenue-normalized: `booked × (price_offered / price_ceiling)` — continuous in [0, 1] |
| **Prior** | Beta(1, 1) — uniform prior per arm per context |

**Why multipliers, not absolute prices?** A heuristic base price (from `lot_pricing_config`) handles the coarse pricing. The bandit only learns a small *adjustment* around that base. This means:
- Arms stay in a tight range (×0.7 to ×1.5), so the worst-case exploration is still a reasonable price.
- Fewer arms needed (6 multipliers vs. many absolute dollar values).
- If the base price is later adjusted (e.g. a lot raises its base rate), the bandit's learned multipliers still apply.

**Why revenue-normalized reward?** A binary reward (booked/not) treats a $3 booking and a $8 booking equally. With `reward = booked × (price / ceiling)`, the agent prefers arms that produce higher revenue, not just higher conversion. Normalizing by ceiling keeps reward in [0, 1] for compatibility with Beta distribution updates.

A separate Beta distribution is maintained **per (context, arm)** pair. This makes the bandit *contextual* without requiring a full contextual-bandit model — we simply partition the state space into discrete buckets and run independent bandits per partition.

### 3.2 Context Dimensions

| Dimension | Buckets | Rationale |
|---|---|---|
| **Time of day** | `morning` (6–11), `afternoon` (11–16), `evening` (16–21), `night` (21–6) | Demand varies by time |
| **Day type** | `weekday`, `weekend` | Different usage patterns |
| **Occupancy level** | `low` (<30%), `medium` (30–70%), `high` (>70%) | Core demand signal |

Context key example: `"morning:weekday:high"` → high-demand weekday morning.

Total contexts per lot: 4 × 2 × 3 = **24**. With 6 multiplier arms, that's 144 arm entries per lot — very manageable.

### 3.3 Algorithm (per pricing request)

```
1. Receive request: lot_id, current_time
2. Build context_key:
      a. time_bucket  ← bucket(current_time.hour)
      b. day_type     ← weekday/weekend(current_time)
      c. Query InventoryService for lot occupancy → occupancy_bucket
3. Look up base_price, price_ceiling from lot_pricing_config
4. For each arm in bandit_arms WHERE lot_id AND context_key:
      sample θ_arm ~ Beta(alpha, beta)
5. Select arm* = argmax(θ_arm)
6. final_price = base_price × arm*.multiplier
7. Log row into pricing_events (booked = FALSE, reward = 0.0 initially)
8. Return final_price
```

### 3.4 Reward Update (on booking confirmation)

When FastAPI confirms a reservation at a given price:

```
1. Look up the pricing_event for this reservation
2. reward = price_offered / price_ceiling        (continuous, in [0, 1])
3. Set booked = TRUE, reward = reward on the pricing_event row
4. Update bandit_arms:
      alpha += reward
      beta  += (1 - reward)
      total_pulls += 1
      total_revenue += price_offered
```

When a price is offered but the user does **not** book (e.g. they abandon or the pricing_event ages beyond a TTL):

```
1. reward = 0
2. Update bandit_arms:
      alpha += 0       (no change)
      beta  += 1
      total_pulls += 1
```

**Intuition:** A booking at a high price pushes alpha up significantly (e.g. +0.8), making that multiplier more likely to be sampled again. A booking at a low price pushes alpha less (e.g. +0.3), so the agent still prefers it over no booking, but not as much as a high-revenue booking. No booking always pushes beta up by 1, penalizing that arm.

### 3.5 Initialization / Seeding

On first deployment (or when a new lot is added), the Pricing Service:

1. Inserts a row into `lot_pricing_config` with a sensible base price and ceiling for the lot.
2. Seeds `bandit_arms` with all (context_key, multiplier) combinations for that lot.
   - Multipliers: 0.7, 0.85, 1.0, 1.15, 1.3, 1.5
   - Contexts: 24 per lot
   - Total: 144 rows per lot, each initialized to Beta(1, 1).

Because the base price already encodes a reasonable starting rate, the ×1.0 arm is "correct" from day one. The bandit explores modest adjustments around it.

---

## 4. gRPC Interface Definitions

### 4.1 Pricing Service gRPC (pricing_service.proto)

The Pricing Service exposes a gRPC server consumed by FastAPI. It is also a gRPC client to the Inventory Service (to get occupancy data).

```protobuf
syntax = "proto3";
package pricing;

service PricingService {
    // Called by FastAPI when a user views a lot — returns the current dynamic price.
    rpc GetPrice (GetPriceRequest) returns (GetPriceResponse);

    // Called by FastAPI after a reservation is confirmed — updates the bandit reward.
    rpc RecordBookingOutcome (BookingOutcomeRequest) returns (BookingOutcomeResponse);
}

message GetPriceRequest {
    int32  lot_id = 1;
    string user_id = 2;          // for logging; not used in pricing logic
    string start_time = 3;       // ISO 8601
    string end_time = 4;         // ISO 8601
}

message GetPriceResponse {
    double price_per_hour = 1;    // final price (base × multiplier)
    int32  pricing_event_id = 2;  // opaque ID, passed back in RecordBookingOutcome
    string context_key = 3;       // informational
    double base_price = 4;        // the base price before multiplier
    double multiplier = 5;        // the selected multiplier
}

message BookingOutcomeRequest {
    int32  pricing_event_id = 1;
    bool   booked = 2;           // true = user confirmed, false = abandoned
}

message BookingOutcomeResponse {
    bool   success = 1;
}
```

### 4.2 Inventory Service gRPC (inventory_service.proto)

The Pricing Service needs occupancy data. These RPCs should be part of the Inventory Service's gRPC server (Nafia's responsibility), but are listed here so you can coordinate.

```protobuf
syntax = "proto3";
package inventory;

service InventoryService {
    // Returns current availability/occupancy for a lot.
    rpc GetLotOccupancy (LotOccupancyRequest) returns (LotOccupancyResponse);

    // Returns a list of all lots (for initialization / iteration).
    rpc ListLots (ListLotsRequest) returns (ListLotsResponse);
}

message LotOccupancyRequest {
    int32 lot_id = 1;
}

message LotOccupancyResponse {
    int32 lot_id = 1;
    int32 total_spots = 2;
    int32 available_spots = 3;
    int32 occupied_spots = 4;
    int32 reserved_spots = 5;
    double occupancy_rate = 6;    // (occupied + reserved) / total
}

message ListLotsRequest {}

message ListLotsResponse {
    repeated LotSummary lots = 1;
}

message LotSummary {
    int32  lot_id = 1;
    string name = 2;
    int32  total_spots = 3;
}
```

---

## 5. Data Flow — End-to-End Pricing Scenario

```
User opens app → views Lot #3
       │
       ▼
   FastAPI ──GetPrice(lot_id=3, start, end)──▶ PricingService
                                                     │
                                           GetLotOccupancy(3)
                                                     │
                                                     ▼
                                              InventoryService
                                              (returns: 70% occupied)
                                                     │
                                                     ▼
                                              PricingService:
                                              context = "afternoon:weekday:high"
                                              Thompson sample → $6/hr
                                              Log pricing_event (booked=FALSE)
                                                     │
       ◀──price=$6/hr, event_id=4821──────────────────┘
       │
   User confirms reservation
       │
       ▼
   FastAPI ──(create reservation in InventoryService)──▶ InventoryService
       │
   FastAPI ──RecordBookingOutcome(event_id=4821, booked=TRUE)──▶ PricingService
                                                                      │
                                                                update arm alpha += 1
                                                                update pricing_event booked=TRUE
```

If the user **doesn't** book, a background process (or TTL-based sweep) marks stale pricing_events and increments the arm's beta.

---

## 6. Deployment Notes (Docker Compose additions)

The existing Docker Compose (Andy's domain) will need these additions:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: parking
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: parking
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./db/init.sql:/docker-entrypoint-initdb.d/init.sql  # creates schemas + tables
    ports:
      - "5432:5432"

  pricing-service:
    build: ./pricing-service
    depends_on:
      - postgres
      - inventory-service
    environment:
      DATABASE_URL: postgresql://parking:${POSTGRES_PASSWORD}@postgres:5432/parking?options=-csearch_path=pricing
      INVENTORY_GRPC_HOST: inventory-service:50051

volumes:
  pgdata:
```

> The `init.sql` script would `CREATE SCHEMA inventory; CREATE SCHEMA pricing;` and then run the table DDL from sections 2.2 and 2.3.

---

## 7. Database Integration — What's Actually Needed

Beyond the Docker Compose YAML and the SQL schema, there are a few concrete pieces of work to wire the database into the services.

### 7.1 Init Script (`db/init.sql`)

A single SQL file mounted into the Postgres container at `/docker-entrypoint-initdb.d/`. It runs automatically on first container start. Contents:

```sql
CREATE SCHEMA IF NOT EXISTS inventory;
CREATE SCHEMA IF NOT EXISTS pricing;

SET search_path TO inventory;
-- (paste inventory DDL from §2.2)

SET search_path TO pricing;
-- (paste pricing DDL from §2.3)
```

No separate migration tool is needed for a project of this scope. If the schema changes during development, just `docker compose down -v` (destroys the volume) and re-up.

### 7.2 ORM / Database Access Layer

Yes, each Python service that talks to the DB needs a database library. Recommended stack:

| Component | Library | Why |
|---|---|---|
| Connection + query execution | **SQLAlchemy Core** (not the ORM layer) | Lightweight, gives connection pooling and parameterized queries without the complexity of full ORM models. Already a standard in the Python/FastAPI ecosystem. |
| Async support (if needed) | **asyncpg** as the SQLAlchemy driver | FastAPI is async; asyncpg is the fastest Postgres driver for async Python. |
| Schema-as-code (optional) | SQLAlchemy `Table` objects | Define tables once in Python, use them for queries. Auto-generates the same DDL as the init script if you ever want programmatic migrations. |

**Why not full ORM (SQLAlchemy ORM with mapped classes)?** For a course project with a small schema, mapped model classes add boilerplate without much benefit. Raw SQLAlchemy Core expressions (`select()`, `insert()`, `update()`) are more transparent and easier to debug.

Each service would have a small `db.py` module:

```python
# pricing-service/db.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker
import os

DATABASE_URL = os.environ["DATABASE_URL"]  # from Docker Compose env

# Replace 'postgresql://' with 'postgresql+asyncpg://' for async
engine = create_async_engine(
    DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
    pool_size=5,
)
async_session = async_sessionmaker(engine, class_=AsyncSession)
```

Then in gRPC handlers:

```python
async with async_session() as session:
    result = await session.execute(
        select(bandit_arms).where(
            bandit_arms.c.lot_id == lot_id,
            bandit_arms.c.context_key == context_key,
        )
    )
    arms = result.fetchall()
```

### 7.3 Hosting / Infrastructure

No extra hosting work beyond what Andy is already setting up with Docker Compose:

- **Local dev / demo:** `docker compose up` starts Postgres, RabbitMQ, and all services together. The Postgres data persists in the `pgdata` Docker volume.
- **Cloud deployment (if applicable):** If the team deploys to a cloud VM or Kubernetes, the same Compose file works. For a managed DB, swap the Postgres container for a connection string to a cloud Postgres instance (e.g. Supabase free tier, Railway, or GCP Cloud SQL) — just change `DATABASE_URL`.
- **No separate DB server to provision.** The containerized Postgres is self-contained.

### 7.4 Dependency Summary

New Python packages to add to `requirements.txt` for services that access the DB:

```
sqlalchemy>=2.0
asyncpg
```

That's it. No Alembic, no Django, no extra infrastructure.

---

## 8. Summary of Changes vs. Original Proposal

| Area | Original Proposal | This Document |
|---|---|---|
| **Database** | Not mentioned | PostgreSQL with `inventory` and `pricing` schemas |
| **Parking lots** | Single lot assumed | `parking_lots` table; all queries scoped by `lot_id` |
| **Pricing logic** | "Dynamic pricing" (unspecified) | Contextual multi-armed bandit, Thompson sampling, 7 price arms, 24 context partitions per lot |
| **Pricing data** | None | `bandit_arms` + `pricing_events` tables |
| **gRPC — Pricing** | Mentioned but undefined | `GetPrice`, `RecordBookingOutcome` RPCs defined |
| **gRPC — Inventory** | Mentioned but undefined | `GetLotOccupancy`, `ListLots` RPCs proposed for coordination |
| **Reward loop** | N/A | FastAPI → `RecordBookingOutcome` → arm update |
