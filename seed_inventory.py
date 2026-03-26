"""
Seed demo data for inventory-service: parking lots and spots.
Run this script ONCE on a fresh database. Safe to re-run (will not duplicate lots).
"""
from inventory_service.inventory.database import get_session
from inventory_service.inventory.models import ParkingLot, ParkingSpot
from sqlalchemy import select

LOTS = [
    {"lot_id": 1, "name": "Demo Lot A", "address": "123 Main St", "total_spots": 5},
    {"lot_id": 2, "name": "Demo Lot B", "address": "456 Elm St", "total_spots": 3},
]

SPOTS_PER_LOT = 5

def main():
    session = get_session()
    try:
        for lot in LOTS:
            exists = session.execute(select(ParkingLot).where(ParkingLot.lot_id == lot["lot_id"]))\
                .scalars().first()
            if not exists:
                pl = ParkingLot(**lot)
                session.add(pl)
                session.flush()
                for i in range(1, lot["total_spots"] + 1):
                    spot = ParkingSpot(lot_id=lot["lot_id"], label=f"S{i}", status="available")
                    session.add(spot)
        session.commit()
        print("Demo lots and spots seeded.")
    except Exception as exc:
        session.rollback()
        print(f"Seeding failed: {exc}")
    finally:
        session.close()

if __name__ == "__main__":
    main()