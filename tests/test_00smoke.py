import requests

BASE_URL = "http://localhost:8000"

def test_health_parking_lots():
    r = requests.get(f"{BASE_URL}/parking-lots", timeout=5)
    assert r.status_code == 200

def test_health_users():
    r = requests.post(f"{BASE_URL}/users", json={"username": "smoketest", "email": "smoke@example.com"}, timeout=5)
    assert r.status_code == 200
    assert "success" in r.json()

def test_health_search():
    lots = requests.get(f"{BASE_URL}/parking-lots", timeout=5).json()
    if lots:
        lot_id = lots[0]["lot_id"]
        # Use a dummy user_id for health check
        r = requests.post(f"{BASE_URL}/search", json={
            "user_id": "healthcheck-user",
            "lot_ids": [str(lot_id)],
            "start_time": "2026-03-27T10:00:00Z",
            "end_time": "2026-03-27T12:00:00Z"
        }, timeout=5)
        assert r.status_code == 200
