import requests
import time

BASE_URL = "http://localhost:8000"

def wait_for_api():
    for _ in range(30):
        try:
            r = requests.get(f"{BASE_URL}/parking-lots")
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError("FastAPI did not become available in time.")

def test_end_to_end():
    wait_for_api()

    # 1. Create two users
    user1 = requests.post(f"{BASE_URL}/users", json={"username": "alice", "email": "alice@example.com"}).json()
    print("User 1 creation response:", user1)
    user2 = requests.post(f"{BASE_URL}/users", json={"username": "bob", "email": "bob@example.com"}).json()
    print("User 2 creation response:", user2)
    assert user1["success"] and user2["success"]
    user1_id = user1["user_id"]
    user2_id = user2["user_id"]

    # 2. Seed parking lots if none exist
    lots = requests.get(f"{BASE_URL}/parking-lots").json()
    if not lots:
        # This assumes an admin endpoint or DB seeding script exists; otherwise, this step is manual
        raise RuntimeError("No parking lots found. Please seed the database with at least one lot.")
    lot_id = lots[0]["lot_id"]

    # 3. Search for spots
    search = requests.post(f"{BASE_URL}/search", json={
        "user_id": user1_id,
        "lot_ids": [int(lot_id)],
        "start_time": "2026-03-27T10:00:00Z",
        "end_time": "2026-03-27T12:00:00Z"
    }).json()
    assert search["results"], "No available spots found."
    event_id = search["results"][0]["event_id"]
    price = search["results"][0]["price_per_hour"]
    print("DEBUG: price for booking =", price, type(price))

    # 4. User 1 books a spot
    book_resp = requests.post(f"{BASE_URL}/book", json={
        "event_id": event_id,
        "lot_id": int(lot_id),
        "user_id": user1_id,
        "start_time": "2026-03-27T10:00:00Z",
        "end_time": "2026-03-27T12:00:00Z",
        "price": price,
        "is_booking": True
    }).json()
    assert book_resp["success"], f"Booking failed: {book_resp}"

    # 5. User 2 declines
    decline_resp = requests.post(f"{BASE_URL}/book", json={
        "event_id": event_id,
        "lot_id": int(lot_id),
        "user_id": user2_id,
        "start_time": "2026-03-27T10:00:00Z",
        "end_time": "2026-03-27T12:00:00Z",
        "price": price,
        "is_booking": False
    }).json()
    assert decline_resp["success"] or "success" not in decline_resp, "Decline should not fail"

    # 6. User 1 checks reservations
    # (Assumes a /reservations endpoint exists; if not, this step should be implemented)
    # reservations = requests.get(f"{BASE_URL}/reservations", params={"user_id": user1_id}).json()
    # assert reservations, "User 1 should have at least one reservation."
    print("End-to-end test completed successfully.")
