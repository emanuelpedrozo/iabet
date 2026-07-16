from fastapi.testclient import TestClient
from app.main import app


def test_admin_overview_requires_auth():
    r = TestClient(app).get("/api/v1/admin/overview")
    assert r.status_code == 401


def test_admin_sync_requires_auth():
    r = TestClient(app).post("/api/v1/admin/sync/predictions")
    assert r.status_code == 401
