"""API checks that do not call Garmin."""

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


def test_health_and_status_do_not_reveal_the_api_key() -> None:
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        status = client.get("/api/garmin/status")
        assert status.status_code == 200
        payload = status.json()
        assert payload["fit_download_implemented"] is True
        assert payload["fit_download_documented"] is True
        key = get_settings().garmin_personal_api_key.strip()
        if key:
            assert key not in status.text

        activities = client.get("/api/activities")
        assert activities.status_code == 200
        body = activities.json()
        assert isinstance(body["total"], int)
        assert isinstance(body["activities"], list)
