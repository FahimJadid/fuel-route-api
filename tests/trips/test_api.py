import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from django.contrib.gis.geos import Point

from geo.services.importer import import_places
from geo.sources import read_gazetteer
from routing.types import Route
from tests.factories import StationFactory
from trips import services

pytestmark = pytest.mark.django_db

GEO_FIXTURES = Path(__file__).parents[1] / "geo" / "fixtures"

# Straight route along 37.47°N through Alamosa, CO; roughly 440 miles for 8° of longitude.
ROUTE = Route(
    provider="stub",
    distance_miles=440.0,
    duration_minutes=420,
    geometry=((-110.0, 37.472041), (-105.877348, 37.472041), (-102.0, 37.472041)),
)
ORIGIN = {"lat": 37.472041, "lng": -110.0}
DESTINATION = {"lat": 37.472041, "lng": -102.0}


@pytest.fixture(autouse=True)
def stub_route(monkeypatch):
    monkeypatch.setattr(services, "get_route", lambda origin, destination: ROUTE)


@pytest.fixture
def alamosa_station():
    return StationFactory(
        name="ALAMOSA TRUCK STOP",
        city="Alamosa",
        state="CO",
        location=Point(-105.877348, 37.472041, srid=4326),
        price_per_gallon=Decimal("3.250"),
    )


def test_post_trip_returns_plan_and_get_returns_the_same_trip(api_client, alamosa_station):
    response = api_client.post(
        "/api/v1/trips/", {"origin": ORIGIN, "destination": DESTINATION}, format="json"
    )

    assert response.status_code == 201
    body = response.json()
    assert body["origin"] == {"label": "37.4720, -110.0000", "lat": 37.472041, "lng": -110.0}
    assert body["distance_miles"] == "440.0"
    assert body["vehicle"] == {"max_range_miles": "500.0", "mpg": "10.00", "tank_gallons": "50.00"}
    assert body["route"]["type"] == "LineString"
    assert len(body["route"]["coordinates"]) == 3
    assert body["totals"] == {"gallons": "44.000", "cost": "143.00", "stops": 1}
    stop = body["stops"][0]
    assert stop["station"]["opis_id"] == alamosa_station.opis_id
    assert stop["price_per_gallon"] == "3.250"
    assert stop["gallons"] == 44.0
    assert body["links"] == {
        "self": f"http://testserver/api/v1/trips/{body['id']}/",
        "map": f"http://testserver/api/v1/trips/{body['id']}/map/",
    }

    fetched = api_client.get(body["links"]["self"])

    assert fetched.status_code == 200
    assert fetched.json() == body


def test_post_trip_accepts_city_names(api_client, alamosa_station):
    import_places(read_gazetteer(GEO_FIXTURES / "gazetteer_sample.txt"))

    response = api_client.post(
        "/api/v1/trips/",
        {"origin": "alamosa, co", "destination": DESTINATION, "max_range_miles": 300, "mpg": 8},
        format="json",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["origin"]["label"] == "Alamosa, CO"
    assert body["vehicle"]["max_range_miles"] == "300.0"
    assert body["vehicle"]["mpg"] == "8.00"


def test_unknown_place_is_a_400_with_a_hint(api_client):
    response = api_client.post(
        "/api/v1/trips/", {"origin": "Nowhere, ZZ", "destination": DESTINATION}, format="json"
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "place_not_found"


def test_missing_fields_and_bad_ranges_are_validation_errors(api_client):
    response = api_client.post(
        "/api/v1/trips/", {"origin": ORIGIN, "max_range_miles": 10}, format="json"
    )

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert set(error["details"]) == {"destination", "max_range_miles"}


def test_malformed_location_is_a_validation_error(api_client):
    response = api_client.post(
        "/api/v1/trips/", {"origin": {"lat": "north"}, "destination": DESTINATION}, format="json"
    )

    assert response.status_code == 400
    assert "lat and lng" in response.json()["error"]["details"]["origin"][0]


def test_route_without_stations_in_range_is_a_422_with_the_route(api_client):
    response = api_client.post(
        "/api/v1/trips/", {"origin": ORIGIN, "destination": DESTINATION}, format="json"
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "no_feasible_plan"
    assert error["details"]["from_mile"] == 0.0
    assert error["details"]["route"]["coordinates"][0] == [-110.0, 37.472041]


def test_map_page_renders_the_plan(api_client, alamosa_station):
    created = api_client.post(
        "/api/v1/trips/", {"origin": ORIGIN, "destination": DESTINATION}, format="json"
    ).json()

    response = api_client.get(created["links"]["map"])

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/html")
    html = response.content.decode()
    assert "ALAMOSA TRUCK STOP" in html
    assert 'id="map-data"' in html
    assert "143.00" in html


def test_map_page_for_unknown_trip_is_a_json_404(api_client):
    response = api_client.get(f"/api/v1/trips/{uuid.uuid4()}/map/")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_malformed_trip_id_and_unknown_api_paths_are_json_404s(api_client):
    for path in ("/api/v1/trips/not-a-uuid/", "/api/v1/nothing-here/"):
        response = api_client.get(path)

        assert response.status_code == 404, path
        assert response.json()["error"]["code"] == "not_found", path


def test_unknown_trip_is_a_404(api_client):
    response = api_client.get(f"/api/v1/trips/{uuid.uuid4()}/")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_openapi_schema_renders(api_client):
    response = api_client.get("/api/schema/")

    assert response.status_code == 200
    assert b"/api/v1/trips/" in response.content
