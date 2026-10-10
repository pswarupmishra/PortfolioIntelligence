from fastapi.testclient import TestClient

from app.main import app


def test_live_health() -> None:
    response = TestClient(app).get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_admin_route_requires_role() -> None:
    response = TestClient(app).post("/api/v1/jira/test-connection")
    assert response.status_code == 403
