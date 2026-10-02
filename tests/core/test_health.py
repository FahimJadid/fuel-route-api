import pytest
from django.core.cache import cache


@pytest.mark.django_db
def test_health_reports_ok_when_dependencies_respond(api_client):
    response = api_client.get("/api/v1/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok", "cache": "ok"}}


@pytest.mark.django_db
def test_every_response_carries_its_server_time(api_client):
    response = api_client.get("/api/v1/health/")

    assert float(response["X-Response-Time-Ms"]) >= 0


@pytest.mark.django_db
def test_health_reports_degraded_when_cache_fails(api_client, monkeypatch):
    def broken_set(*args, **kwargs):
        raise ConnectionError

    monkeypatch.setattr(cache, "set", broken_set)

    response = api_client.get("/api/v1/health/")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["checks"]["cache"] == "error: ConnectionError"
