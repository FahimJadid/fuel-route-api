from decimal import Decimal

import pytest
from django.contrib.gis.geos import Point

from geo.services.resolver import ResolvedLocation
from routing.types import Route
from tests.factories import StationFactory
from trips import services
from trips.exceptions import NoFeasiblePlanError
from trips.models import Trip
from trips.services import TripRequest, plan_trip

pytestmark = pytest.mark.django_db

# Straight route along 35°N from -100° to -90°, roughly 566 miles.
ROUTE = Route(
    provider="stub",
    distance_miles=566.0,
    duration_minutes=540,
    geometry=((-100.0, 35.0), (-95.0, 35.0), (-90.0, 35.0)),
)
ORIGIN = ResolvedLocation(label="Start, TX", lat=35.0, lng=-100.0)
DESTINATION = ResolvedLocation(label="End, TN", lat=35.0, lng=-90.0)


@pytest.fixture(autouse=True)
def stub_route(monkeypatch):
    monkeypatch.setattr(services, "get_route", lambda origin, destination: ROUTE)


def request(max_range_miles: float = 500, mpg: float = 10) -> TripRequest:
    return TripRequest(ORIGIN, DESTINATION, max_range_miles=max_range_miles, mpg=mpg)


def test_plan_trip_persists_route_stops_and_totals():
    cheap = StationFactory(
        name="CHEAP", location=Point(-98.0, 35.0, srid=4326), price_per_gallon=Decimal("3.000")
    )
    StationFactory(
        name="PRICEY", location=Point(-96.0, 35.0, srid=4326), price_per_gallon=Decimal("4.000")
    )

    trip = plan_trip(request())

    assert Trip.objects.get(pk=trip.pk) == trip
    assert trip.origin_label == "Start, TX"
    assert trip.distance_miles == Decimal("566.0")
    assert trip.duration_minutes == 540
    assert trip.route.coords == ROUTE.geometry
    assert trip.routing_provider == "stub"
    assert [stop["station"]["name"] for stop in trip.stops] == ["CHEAP"]
    assert trip.stops[0]["station"]["opis_id"] == cheap.opis_id
    assert trip.stops[0]["price_per_gallon"] == "3.000"
    assert trip.stops[0]["gallons"] == pytest.approx(56.6)
    assert trip.stops[0]["fuel_on_arrival_gallons"] == 0.0
    assert trip.total_gallons == Decimal("56.600")
    assert trip.total_cost == Decimal("169.80")


def test_plan_trip_honours_vehicle_parameters():
    StationFactory(location=Point(-98.0, 35.0, srid=4326))
    StationFactory(location=Point(-94.0, 35.0, srid=4326))

    trip = plan_trip(request(max_range_miles=250, mpg=5))

    assert len(trip.stops) == 2
    assert trip.max_range_miles == Decimal("250.0")
    assert trip.mpg == Decimal("5.00")
    assert trip.total_gallons == Decimal("113.200")


def test_plan_trip_reports_coverage_gap_with_the_route():
    StationFactory(location=Point(-99.5, 35.0, srid=4326))

    with pytest.raises(NoFeasiblePlanError) as excinfo:
        plan_trip(request())

    details = excinfo.value.details
    assert details["from_mile"] == pytest.approx(28.3, abs=0.1)
    assert details["distance_miles"] == 566.0
    assert details["route"]["coordinates"][0] == [-100.0, 35.0]
    assert Trip.objects.count() == 0
