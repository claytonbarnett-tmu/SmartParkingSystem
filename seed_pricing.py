"""
Seed demo data for pricing-service: lot pricing configs and bandit arms.
Run this script ONCE on a fresh database. Safe to re-run (idempotent).
"""
from pricing.database import get_session
from pricing.seed import seed_lot

# Match inventory lots for consistency
LOTS = [
    {"lot_id": 1, "base_price": 4.00},
    {"lot_id": 2, "base_price": 3.50},
]

def main():
    session = get_session()
    try:
        for lot in LOTS:
            count = seed_lot(session, lot["lot_id"], base_price=lot["base_price"])
            print(f"Seeded lot {lot['lot_id']} (added {count} bandit arms)")
        session.commit()
        print("Demo pricing configs and bandit arms seeded.")
    except Exception as exc:
        session.rollback()
        print(f"Seeding failed: {exc}")
    finally:
        session.close()

if __name__ == "__main__":
    main()
