# Pricing Service — Design and Implementation

This document provides a structured reference for the **design** and
**implementation** of the Pricing Service within the Smart Parking System.
It is written to feed directly into the project report's *Design* and
*Implementation* sections.

---

## Part A — Design

### A.1  High-Level Design

The Pricing Service is responsible for a single concern: **deciding how much
to charge a driver for a parking reservation, and learning from the outcome
of that decision.**

At the highest level the service operates as a closed feedback loop:

```
           ┌──────────────────────────────────────────────────┐
           │          Pricing Service (feedback loop)         │
           │                                                  │
  request  │   ┌───────────┐    price    ┌───────────┐       │  outcome
  ────────►│   │  Observe  │────────────►│  Decide   │───────│──────────►
           │   │  Context  │             │   Price   │       │
           │   └───────────┘             └─────┬─────┘       │
           │                                   │             │
           │         ┌─────────────┐           │             │
  outcome  │         │   Update    │◄──────────┘             │
  ────────►│         │   Beliefs   │                         │
           │         └─────────────┘                         │
           └──────────────────────────────────────────────────┘
```

1. **Observe Context** — When a user views a parking lot, the service
   gathers contextual information: the time of day, the day of the week,
   and how full the lot currently is.

2. **Decide Price** — Using its current beliefs about which price works
   best for this context, the service selects a price and presents it to
   the user.

3. **Update Beliefs** — When the user either books or walks away, the
   service treats the outcome as a learning signal and adjusts its beliefs
   so that future decisions in similar contexts are better informed.

The service is **stateful**: it must remember its beliefs across restarts
and keep a historical record of every price it has offered and the
corresponding outcome.  This requires a persistent storage layer.

The service is also **context-aware**: a price that works well on a
weekday morning in a nearly-full lot may perform poorly on a weekend
night in a half-empty lot.  The service therefore maintains independent
beliefs for each distinct context.


### A.2  Detailed Design

This section breaks the high-level loop into its constituent design
elements.  No specific technologies or code are referenced here — those
appear in Part B.

#### A.2.1  Context Model

The service discretises the continuous environment into a finite set of
**context buckets**.  Three dimensions are used:

| Dimension        | Buckets                                    | Count |
|------------------|--------------------------------------------|-------|
| Time of day      | morning, afternoon, evening, night         | 4     |
| Day type         | weekday, weekend                           | 2     |
| Occupancy level  | low (< 30 %), medium (30–70 %), high (> 70 %) | 3  |

The Cartesian product yields **4 × 2 × 3 = 24 unique contexts**.  Each
context is encoded as a human-readable key, e.g. `morning:weekday:high`.

> **Design rationale — why discrete buckets?**  A fully continuous context
> representation would require a parametric model (e.g. a neural network)
> and far more data to converge.  Discrete buckets let us run a simple,
> well-understood algorithm with fast convergence, which is appropriate for
> a system that may see only tens of bookings per day per lot.

#### A.2.2  Action Space (Price Multipliers)

Rather than choosing from a set of absolute dollar amounts, the service
defines its actions as **multipliers** applied to a per-lot **base price**.

Default multipliers: **×0.70,  ×0.85,  ×1.00,  ×1.15,  ×1.30,  ×1.50**.

This means the service can offer prices ranging from 70 % to 150 % of the
base rate.

> **Design rationale — why multipliers?**
>
> - The base price already encodes a reasonable starting rate, so even the
>   worst-case exploratory price (×0.70 or ×1.50) is still sensible.
> - If a lot operator later changes the base rate, previously learned
>   multipliers remain valid.
> - The action space stays small (6 arms) regardless of absolute price range.

#### A.2.3  Decision Algorithm

The service uses a **contextual multi-armed bandit** with **Thompson
sampling**.

##### The Beta distribution

Each (context, multiplier) pair — called an *arm* — is associated with a
**Beta distribution**, a continuous probability distribution defined on
the interval [0, 1] and parameterised by two positive shape parameters,
**α** (alpha) and **β** (beta).

- The **mean** of a Beta(α, β) distribution is $\frac{\alpha}{\alpha + \beta}$.
  This represents the system's current best estimate of how "good" the
  arm is — specifically, how much normalised revenue it tends to produce.
- The **variance** decreases as α + β grows.  A freshly initialised arm
  with Beta(1, 1) — a uniform distribution — has maximum uncertainty.
  After many observations the distribution becomes tightly concentrated
  around the true reward rate.
- When α > β the distribution is skewed right (the arm is believed to be
  good).  When β > α it is skewed left (the arm is believed to be poor).

All arms are initialised to **Beta(1, 1)**, which is a uniform
distribution over [0, 1] — expressing total prior ignorance about the
arm's quality.

##### Thompson sampling

At decision time the algorithm proceeds as follows:

1. For every arm in the current context, **draw one random sample** from
   its Beta(α, β) distribution.  This sample is a number between 0 and 1.
2. **Select the arm whose sample is highest.**

A "high" sample from an arm means that, on this particular draw, the arm
looked very promising.  Because the sample is *random*, an arm with high
uncertainty (low α + β) will occasionally produce very high samples even
if its mean is mediocre — this is how the algorithm **explores** arms it
hasn't tried much.  Conversely, an arm with strong positive evidence
(high α, low β) will consistently produce high samples — this is how the
algorithm **exploits** what it has already learned.

Thompson sampling therefore achieves an automatic, principled balance
between exploration and exploitation without requiring a tuning parameter
(unlike ε-greedy or UCB approaches).

#### A.2.4  Reward Signal

The reward must capture both *whether* the user booked and *how much
revenue* that booking generated.  A binary reward (booked / not booked)
would treat a $3 booking and a $10 booking identically, so the service
uses a **normalised revenue reward**:

$$
r = \text{booked} \times \frac{\text{price\_offered}}{\text{price\_ceiling}}
$$

The **price ceiling** is not a separate configuration value — it is
derived automatically as `base_price × max(multipliers)`.  With the
default multipliers this is `base_price × 1.50`.  This ensures the
ceiling always matches the highest price the system can actually offer.

- If the user books at $6 and the ceiling is $6 (= $4 × 1.50): $r = 6/6 = 1.0$.
- If the user books at $2.80 (= $4 × 0.70) and the ceiling is $6:
  $r = 2.80/6 ≈ 0.47$.
- If the user does not book: $r = 0$.

This keeps $r \in [0, 1]$, which is required for valid Beta-distribution
updates.

#### A.2.5  Belief Update Rules

After every pricing event:

| Outcome    | α update         | β update             |
|------------|------------------|----------------------|
| **Booked** | α ← α + r        | β ← β + (1 − r)     |
| **Abandoned** | (no change)   | β ← β + 1           |

> **Why this rule?**  The Beta distribution is the conjugate prior for
> Bernoulli-like observations.  In the standard binary case (success /
> failure) the update is simply α += 1 on success, β += 1 on failure.
> Our reward is *continuous* in [0, 1] rather than binary, so we use a
> fractional update: a booking contributes `r` to α and `(1 − r)` to β,
> where `r` is the normalised revenue (A.2.4).  This preserves the
> property that every observation adds exactly 1 to (α + β) — keeping
> the distribution's concentration growing at a steady rate — while
> encoding *how much* revenue the booking generated, not just *whether*
> it occurred.
>
> The effect: a high-revenue booking (e.g. r = 0.8) shifts the
> distribution strongly to the right (α grows a lot, β grows a little),
> making the arm much more likely to be selected again.  A low-revenue
> booking (e.g. r = 0.25) still shifts it right, but only modestly.
> An abandonment (r = 0) shifts it left (only β grows), penalising the
> arm.

#### A.2.6  Lot Initialisation

When a new parking lot is added to the system the service must
pre-populate the belief store with all (context, multiplier) combinations
for that lot: **24 contexts × 6 multipliers = 144 entries**, each set to
Beta(1, 1).  A per-lot configuration record stores the base price; the
price ceiling is derived automatically as `base_price × max(multipliers)`
(see A.2.4).  Initialisation is idempotent — running it again for an
existing lot updates the configuration but does not duplicate entries.

#### A.2.7  Persistent State

Two categories of data must survive restarts:

1. **Belief state** — the (α, β) parameters for every arm, plus
   pull counts and cumulative revenue.
2. **Event log** — an append-only history of every pricing decision:
   the arm that was chosen, the price offered, whether the user booked,
   and the computed reward.  A new event row is created at offer time
   (with ``booked=False``); it is updated in-place when the outcome
   is known.

A third piece of configuration — the per-lot base price — is also stored
persistently.  The price ceiling is derived from the base price and
multipliers, not stored separately.

#### A.2.8  Service Interface

The service exposes four operations to the rest of the system:

| Operation            | Input                              | Output                              | Side effects                          |
|----------------------|------------------------------------|-------------------------------------|---------------------------------------|
| **Get Price**        | lot ID, start time, occupancy rate | offered price, event ID, context key | Inserts a ``PricingEvent`` row       |
| **Confirm Booking**  | event ID                           | (none)                              | Updates arm α/β, marks event booked   |
| **Cancel Booking**   | event ID                           | (none)                              | Increments arm β, event stays unbooked|
| **Initialise Lot**   | lot ID, base price                 | number of arms created              | Seeds belief store and config         |

*Get Price* runs Thompson sampling and logs a ``PricingEvent`` with
``booked=False``.  The caller receives an ``event_id`` that must be
passed back to either *Confirm Booking* or *Cancel Booking* to close
the feedback loop.

This event-ID approach provides a clean separation between the
pricing decision and the outcome recording, and produces an audit
trail of every price ever offered — even for abandoned sessions.

---

## Part B — Implementation

### B.1  High-Level Implementation

The design in Part A is realised as a Python package (`pricing/`) with
the following technology choices:

| Design element          | Technology / library           | Why                                                              |
|-------------------------|--------------------------------|------------------------------------------------------------------|
| Persistent state (A.2.7)| **PostgreSQL** + **SQLAlchemy 2.0** ORM | Relational storage with schema isolation; ORM gives type-safe, Pythonic access |
| Decision algorithm (A.2.3) | **NumPy** (`numpy.random.beta`) | Fast Beta-distribution sampling                                  |
| Service interface (A.2.8) | Plain Python functions (will be wrapped by **gRPC** handlers) | Clean separation of business logic from transport               |
| Inter-service comms     | **gRPC** (planned)             | To query the Inventory Service for occupancy data                |

The package is structured into five modules, each handling a distinct
design responsibility:

| Module        | Primary design elements covered       | Role                                       |
|---------------|---------------------------------------|--------------------------------------------|
| `models.py`   | A.2.7 (persistent state)              | ORM table definitions                      |
| `database.py` | A.2.7 (persistent state)              | Engine creation, session factory            |
| `bandit.py`   | A.2.1–A.2.5 (context, actions, algorithm, reward, updates) | RL logic     |
| `seed.py`     | A.2.6 (lot initialisation)            | Populates arms for new lots                |
| `service.py`  | A.2.8 (service interface)             | Transaction-safe public API                |


### B.2  Detailed Implementation

Each subsection below maps back to the corresponding design element and
identifies the exact module, class, or function that implements it.

#### B.2.1  Context Model → `bandit.py`

*Implements design element A.2.1.*

Three private helpers discretise the environment:

| Function              | Input            | Output                          |
|-----------------------|------------------|---------------------------------|
| `_time_bucket(hour)`  | integer 0–23     | `"morning"` / `"afternoon"` / `"evening"` / `"night"` |
| `_day_type(dt)`       | `datetime`       | `"weekday"` / `"weekend"`       |
| `_occupancy_bucket(rate)` | float 0.0–1.0 | `"low"` / `"medium"` / `"high"`|

The public function `build_context_key(dt, occupancy_rate)` composes the
three outputs into a colon-separated key (e.g. `"morning:weekday:high"`).

The module-level constant `ALL_CONTEXT_KEYS` pre-computes all 24 possible
keys for use by the seeding logic.

#### B.2.2  Action Space → `bandit.py`, `models.py`

*Implements design element A.2.2.*

The module-level constant `DEFAULT_MULTIPLIERS` in `bandit.py` lists the
six default arms: `[0.70, 0.85, 1.00, 1.15, 1.30, 1.50]`.

Each multiplier is stored per-context in the `BanditArm` ORM model
(column `multiplier`, type `NUMERIC(4,2)`).  The lot's base price lives
in `LotPricingConfig.base_price`.

#### B.2.3  Decision Algorithm → `bandit.select_price()`

*Implements design element A.2.3.*

`select_price(session, lot_id, current_time, occupancy_rate)` executes
the Thompson sampling procedure:

1. Calls `build_context_key()` to encode the context (A.2.1).
2. Queries `LotPricingConfig` for the lot's base price and derives the
   ceiling as `base_price × max(multipliers)` (A.2.2).
3. Queries all `BanditArm` rows matching `(lot_id, context_key)`.
4. Draws `Beta(α, β)` samples via `numpy.random.beta()` for each arm.
5. Selects the arm with `argmax` over the samples.
6. Computes `final_price = base_price × multiplier`.
7. Returns a `PriceSelection` named tuple containing the price,
   `arm_id`, and `context_key`.

This function performs **no writes** — it is a pure query.  Event
logging is handled by the outcome recording step (B.2.4).

#### B.2.4  Reward Signal & Belief Updates → `bandit.record_outcome()`

*Implements design elements A.2.4 and A.2.5.*

`record_outcome(session, arm_id, lot_id, context_key, price_offered, booked)`:
- Loads the `BanditArm` by `arm_id`.
- Derives the price ceiling from the lot's `base_price` × `max(multipliers)`.
- Computes `reward = price_offered / ceiling` if booked, else `reward = 0`.
- Inserts a `PricingEvent` row recording the outcome.
- Updates the arm's Beta parameters:
  - If booked: `α += reward`, `β += (1 − reward)`, `total_revenue += price_offered`.
  - If not booked: `β += 1`.
  - Always: `total_pulls += 1`.

This single function handles both booking and abandonment outcomes,
keeping the interface simple.  It operates within the caller's
transaction (no internal commit).

#### B.2.5  Lot Initialisation → `seed.seed_lot()`

*Implements design element A.2.6.*

`seed_lot(session, lot_id, base_price, multipliers)`:
- Creates or updates a `LotPricingConfig` row (base price only;
  ceiling is derived at runtime).
- Queries existing arms for the lot to avoid duplicates.
- Inserts missing `BanditArm` rows (up to 144) with `α = β = 1`.
- Returns the number of newly created arms.

#### B.2.6  Persistent State → `models.py`, `database.py`

*Implements design element A.2.7.*

**ORM Models** (all in `models.py`, targeting the `pricing` Postgres schema):

| Class              | Table                | Purpose                                        |
|--------------------|----------------------|------------------------------------------------|
| `BanditArm`        | `bandit_arms`        | Belief state: α, β, pull count, revenue        |
| `LotPricingConfig` | `lot_pricing_config` | Per-lot base price (ceiling derived at runtime) |
| `PricingEvent`     | `pricing_events`     | Append-only event log (created at offer time)  |

Key implementation details:
- The Python attribute for the β column is named `beta_param` to avoid
  shadowing Python built-ins; the database column is still `beta`.
- A `UNIQUE(lot_id, context_key, multiplier)` constraint on `bandit_arms`
  prevents duplicate arm entries.
- `pricing_events` has an index on `(lot_id, created_at)` for efficient
  per-lot history queries.

**Database connectivity** (`database.py`):
- Reads `DATABASE_URL` from the environment (defaults to a local dev string).
- Creates the `pricing` schema on startup (`CREATE SCHEMA IF NOT EXISTS`).
- Provides `get_session()` which returns a `Session` with `search_path`
  set to `pricing, public`.

#### B.2.7  Service Interface → `service.py`

*Implements design element A.2.8.*

Four public functions map directly to the four operations in the design:

| Design operation    | Function              | Delegates to                    |
|---------------------|-----------------------|---------------------------------|
| Get Price           | `get_price()`         | `bandit.select_price()`         |
| Confirm Booking     | `confirm_booking()`   | `bandit.record_booking()`       |
| Cancel Booking      | `cancel_booking()`    | `bandit.record_no_booking()`    |
| Initialise Lot      | `initialize_lot()`    | `seed.seed_lot()`               |

Each function follows the same transaction pattern:
1. Acquire a session via `get_session()`.
2. Execute the operation.
3. Commit on success, rollback on exception.
4. Close the session in a `finally` block.

This pattern keeps transaction management out of the lower-level modules,
which only call `session.flush()` (not `commit`) and therefore remain
composable.

---

## Appendix — Module Dependency Graph

```
service.py
   ├── bandit.py
   │      └── models.py
   ├── seed.py
   │      ├── models.py
   │      └── bandit.py  (constants only)
   └── database.py
```

All external dependencies: `sqlalchemy`, `psycopg2-binary`, `numpy`.
