import requests
import time
from datetime import datetime, timedelta

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

    # 3. User 1 Search for spots
    future_start = (datetime.utcnow() + timedelta(hours=2)).replace(microsecond=0).isoformat() + "Z"
    future_end = (datetime.utcnow() + timedelta(hours=4)).replace(microsecond=0).isoformat() + "Z"
    search = requests.post(f"{BASE_URL}/search", json={
        "user_id": user1_id,
        "lot_ids": [str(lot_id)],
        "start_time": future_start,
        "end_time": future_end
    }).json()
    assert search["results"], "No available spots found."
    event_id = search["results"][0]["event_id"]
    price = search["results"][0]["price_per_hour"]
    print("DEBUG: price for booking =", price, type(price))


    # 4. User 1 books a spot
    book_resp = requests.post(f"{BASE_URL}/book", json={
        "event_id": event_id,
        "lot_id": str(lot_id),
        "user_id": user1_id,
        "start_time": future_start,
        "end_time": future_end,
        "price": price,
        "is_booking": True
    }).json()
    print("User 1 booking response:", book_resp)
    assert book_resp["success"], f"Booking failed: {book_resp}"


    # 5. User 2 searches for spots
    search2 = requests.post(f"{BASE_URL}/search", json={
        "user_id": user2_id,
        "lot_ids": [str(lot_id)],
        "start_time": future_start,
        "end_time": future_end
    }).json()
    assert search2["results"], "No available spots found for user 2."
    event_id2 = search2["results"][0]["event_id"]
    price2 = search2["results"][0]["price_per_hour"]

    # 5. User 2 declines (using their own event_id)
    decline_resp = requests.post(f"{BASE_URL}/book", json={
        "event_id": event_id2,
        "lot_id": str(lot_id),
        "user_id": user2_id,
        "start_time": future_start,
        "end_time": future_end,
        "price": price2,
        "is_booking": False
    }).json()
    print("User 2 decline response:", decline_resp)
    assert decline_resp["success"] or "success" not in decline_resp, "Decline should not fail"


    # 6. User 1 checks reservations
    reservations_resp = requests.post(f"{BASE_URL}/reservations", json={"user_id": user1_id}).json()
    print("User 1 reservations response:", reservations_resp)
    reservations = reservations_resp.get("reservations", [])
    assert reservations, "User 1 should have at least one reservation."

    # 7. User 1 cancels the reservation
    reservation_id = reservations[0]["reservation_id"]
    cancel_resp = requests.post(f"{BASE_URL}/cancel-reservation", json={
        "user_id": user1_id,
        "reservation_id": reservation_id
    }).json()
    print("User 1 cancel reservation response:", cancel_resp)
    assert cancel_resp["success"], f"Cancellation failed: {cancel_resp}"

    # 8. User 1 checks reservations again (should be cancelled or empty)
    reservations_resp2 = requests.post(f"{BASE_URL}/reservations", json={"user_id": user1_id}).json()
    print("User 1 reservations after cancellation:", reservations_resp2)
    reservations2 = reservations_resp2.get("reservations", [])
    assert not reservations2 or all(r["status"] == "cancelled" for r in reservations2), "Reservation should be cancelled or gone."

    # 1b. User 1 logs in
    login1 = requests.post(f"{BASE_URL}/login", json={"username": "alice", "email": "alice@example.com"}).json()
    print("User 1 login response:", login1)
    assert login1["success"] and login1["user_id"] == user1_id

    # 1c. User 2 logs in
    login2 = requests.post(f"{BASE_URL}/login", json={"username": "bob", "email": "bob@example.com"}).json()
    print("User 2 login response:", login2)
    assert login2["success"] and login2["user_id"] == user2_id

    print("End-to-end test completed successfully.")
