"""
API integration tests for Flask web endpoints.
"""

from app.routes import app
from seed_data import seed_database


def test_flask_endpoints():
    seed_database()
    client = app.test_client()

    # 1. Main UI
    res = client.get("/")
    assert res.status_code == 200
    assert b"Smart Blood Bank Management System" in res.data

    # 2. Stats
    res = client.get("/api/stats")
    assert res.status_code == 200
    assert res.json["total_donors"] == 10

    # 3. Slide 9 Inventory
    res = client.get("/api/reports/inventory")
    assert res.status_code == 200
    assert len(res.json) > 0

    # 4. Slide 9 Expiry (FEFO)
    res = client.get("/api/reports/expiry")
    assert res.status_code == 200
    assert len(res.json) > 0

    # 5. Slide 9 Quality
    res = client.get("/api/reports/quality")
    assert res.status_code == 200
    assert res.json["quarantined_count"] >= 1

    # 6. Slide 9 Requests
    res = client.get("/api/reports/requests")
    assert res.status_code == 200
    assert len(res.json) == 3

    # 7. Concurrency Test API
    res = client.post("/api/concurrency-test")
    assert res.status_code == 200
    assert res.json["report"]["acid_properties_verified"] is True
