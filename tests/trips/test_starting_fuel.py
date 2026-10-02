import random
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

import pytest
from django.contrib.gis.geos import Point
from django.core.management import call_command

from routing.types import Route
from tests.factories import StationFactory
from tests.trips.reference_planner import reference_cost
from trips import services
from trips.exceptions import NoFeasiblePlanError
from trips.models import Trip
from trips.planner import FuelStation, StartingFuel, plan_fuel_stops
from trips.services import TripRequest, plan_trip

RANGE = 500.0
MPG = 10.0
TANK = RANGE / MPG


def station(mile: float, price: str, id: int | None = None) -> FuelStation:
    return FuelStation(route_mile=mile, price_per_gallon=Decimal(price), id=id or int(mile))


def stop_miles(plan) -> list[float]:
    return [stop.station.route_mile for stop in plan.stops]


def test_default_zero_initial_fuel_matches_previous_behaviour():
    stations = [station(100, "3.000"), station(550, "4.000"), station(700, "2.500")]

    plan = plan_fuel_stops(stations, trip_miles=1000, max_range_miles=RANGE, mpg=MPG)

    assert stop_miles(plan) == [100, 550, 700]
    assert [stop.gallons for stop in plan.stops] == pytest.approx([60.0, 10.0, 30.0])
    assert plan.stops[0].fuel_on_arrival_gallons == 0.0
    assert plan.total_gallons == pytest.approx(100.0)
    assert plan.total_cost == Decimal("295.00")
    assert plan.starting_fuel == StartingFuel(
        free_gallons=0.0, reserve_gallons=10.0, reserve_billed_at_stop=1, reserve_cost=Decimal(0)
    )
    assert plan.starting_fuel.reserve_cost == Decimal("30.00")


def test_initial_fuel_covers_whole_trip_returns_zero_stops():
    stations = [station(100, "3.000"), station(250, "2.000")]

    plan = plan_fuel_stops(stations, 300, RANGE, MPG, initial_fuel_gallons=35)

    assert plan.stops == []
    assert plan.total_gallons == 0.0
    assert plan.total_cost == Decimal(0)
    assert plan.starting_fuel == StartingFuel(35, 0.0, None, Decimal(0))


def test_initial_fuel_covers_whole_trip_even_with_no_stations():
    plan = plan_fuel_stops([], 300, RANGE, MPG, initial_fuel_gallons=30)

    assert plan.stops == []
    assert plan.starting_fuel.reserve_billed_at_stop is None


def test_partial_initial_fuel_reduces_first_purchase_and_sets_fuel_on_arrival():
    stations = [station(100, "3.000"), station(550, "4.000"), station(700, "2.500")]

    plan = plan_fuel_stops(stations, 1000, RANGE, MPG, initial_fuel_gallons=25)

    assert stop_miles(plan) == [100, 550, 700]
    assert plan.stops[0].fuel_on_arrival_gallons == pytest.approx(15.0)
    assert plan.stops[0].gallons == pytest.approx(35.0)
    assert plan.starting_fuel.reserve_gallons == 0.0
    assert plan.starting_fuel.reserve_billed_at_stop is None
    assert plan.starting_fuel.reserve_cost == Decimal(0)
    assert plan.total_gallons == pytest.approx(75.0)


def test_initial_fuel_exactly_reaching_first_stop_has_zero_reserve_and_billed_at_none():
    plan = plan_fuel_stops([station(200, "3.000")], 400, RANGE, MPG, initial_fuel_gallons=20)

    assert plan.stops[0].fuel_on_arrival_gallons == 0.0
    assert plan.stops[0].gallons == pytest.approx(20.0)
    assert plan.starting_fuel.reserve_gallons == 0.0
    assert plan.starting_fuel.reserve_billed_at_stop is None


def test_initial_fuel_equal_to_tank_capacity_is_allowed():
    stations = [station(300, "3.000"), station(650, "3.500")]

    plan = plan_fuel_stops(stations, 900, RANGE, MPG, initial_fuel_gallons=TANK)

    assert plan.starting_fuel.free_gallons == TANK
    assert plan.total_gallons == pytest.approx(90.0 - TANK)


def test_initial_fuel_short_of_first_stop_bills_only_the_shortfall():
    plan = plan_fuel_stops([station(300, "2.000")], 400, RANGE, MPG, initial_fuel_gallons=10)

    assert plan.starting_fuel.reserve_gallons == pytest.approx(20.0)
    assert plan.starting_fuel.reserve_cost == Decimal("40.00")
    assert plan.stops[0].gallons == pytest.approx(30.0)
    assert plan.total_cost == Decimal("60.00")


@pytest.mark.parametrize("seed", range(200))
def test_random_instances_with_free_fuel_satisfy_invariants_and_beat_the_reference(seed):
    rng = random.Random(seed)
    trip = rng.uniform(200, 3000)
    free = rng.uniform(0, TANK)
    stations = [
        station(round(rng.uniform(0, trip), 1), f"{rng.uniform(2.5, 5.0):.3f}", id=index)
        for index in range(rng.randint(0, 40))
    ]
    reference = reference_cost(stations, trip, RANGE, MPG, initial_fuel_gallons=free)

    try:
        plan = plan_fuel_stops(stations, trip, RANGE, MPG, initial_fuel_gallons=free)
    except NoFeasiblePlanError:
        assert reference is None
        return

    assert reference is not None
    assert plan.total_gallons == pytest.approx(max(trip / MPG - free, 0.0))
    assert plan.total_cost <= reference.quantize(Decimal("0.01")) + Decimal("0.05")
    assert plan.starting_fuel.free_gallons == free
    miles = [0.0, *stop_miles(plan), trip]
    assert all(b - a <= RANGE + 1e-6 for a, b in pairwise(miles))
    assert all(stop.fuel_on_arrival_gallons >= -1e-9 for stop in plan.stops)
    assert all(stop.gallons > 0 for stop in plan.stops)
    if plan.stops:
        first = plan.stops[0]
        assert plan.starting_fuel.reserve_gallons == pytest.approx(
            max(first.station.route_mile / MPG - free, 0.0)
        )
        assert first.fuel_on_arrival_gallons == pytest.approx(
            max(free - first.station.route_mile / MPG, 0.0)
        )


# API and service checks below use the same synthetic route as tests/trips/test_api.py.

GEO_FIXTURES = Path(__file__).parents[1] / "geo" / "fixtures"
ROUTE = Route(
    provider="stub",
    distance_miles=440.0,
    duration_minutes=420,
    geometry=((-110.0, 37.472041), (-105.877348, 37.472041), (-102.0, 37.472041)),
)
ORIGIN = {"lat": 37.472041, "lng": -110.0}
DESTINATION = {"lat": 37.472041, "lng": -102.0}


@pytest.fixture
def api_setup(monkeypatch):
    monkeypatch.setattr(services, "get_route", lambda origin, destination: ROUTE)
    call_command("import_states", file=GEO_FIXTURES / "states_sample.geojson")
    return StationFactory(
        name="ALAMOSA TRUCK STOP",
        location=Point(-105.877348, 37.472041, srid=4326),
        price_per_gallon=Decimal("3.250"),
    )


@pytest.mark.django_db
def test_request_without_the_field_keeps_the_previous_response_and_adds_starting_fuel(
    api_client, api_setup
):
    body = api_client.post(
        "/api/v1/trips/", {"origin": ORIGIN, "destination": DESTINATION}, format="json"
    ).json()

    assert body["vehicle"] == {"max_range_miles": "500.0", "mpg": "10.00", "tank_gallons": "50.00"}
    assert body["totals"] == {"gallons": "44.000", "cost": "143.00", "stops": 1}
    assert body["stops"][0]["gallons"] == 44.0
    assert body["stops"][0]["fuel_on_arrival_gallons"] == 0.0
    assert body["starting_fuel"] == {
        "free_gallons": "0.000",
        "reserve_gallons": "22.670",
        "reserve_billed_at_stop": 1,
        "reserve_cost": "73.68",
        "trip_gallons": "44.000",
    }


@pytest.mark.django_db
def test_free_fuel_reduces_the_first_purchase_in_the_response(api_client, api_setup):
    body = api_client.post(
        "/api/v1/trips/",
        {"origin": ORIGIN, "destination": DESTINATION, "initial_fuel_gallons": 30},
        format="json",
    ).json()

    assert body["stops"][0]["fuel_on_arrival_gallons"] == pytest.approx(7.33, abs=0.01)
    assert body["stops"][0]["gallons"] == pytest.approx(14.0, abs=0.01)
    assert body["totals"]["gallons"] == "14.000"
    assert body["starting_fuel"]["free_gallons"] == "30.000"
    assert body["starting_fuel"]["reserve_gallons"] == "0.000"
    assert body["starting_fuel"]["reserve_billed_at_stop"] is None
    assert body["starting_fuel"]["trip_gallons"] == "44.000"


@pytest.mark.django_db
def test_initial_fuel_above_tank_capacity_is_a_400_naming_the_field(api_client, api_setup):
    response = api_client.post(
        "/api/v1/trips/",
        {"origin": ORIGIN, "destination": DESTINATION, "initial_fuel_gallons": 51},
        format="json",
    )

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"]["initial_fuel_gallons"] == [
        "Cannot exceed the tank capacity of 50.00 gallons."
    ]


@pytest.mark.django_db
def test_negative_initial_fuel_is_a_400(api_client, api_setup):
    response = api_client.post(
        "/api/v1/trips/",
        {"origin": ORIGIN, "destination": DESTINATION, "initial_fuel_gallons": -1},
        format="json",
    )

    assert response.status_code == 400
    assert "initial_fuel_gallons" in response.json()["error"]["details"]


@pytest.mark.django_db
def test_zero_stop_trip_serialises_cleanly(api_client, api_setup):
    response = api_client.post(
        "/api/v1/trips/",
        {"origin": ORIGIN, "destination": DESTINATION, "initial_fuel_gallons": 50},
        format="json",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["stops"] == []
    assert body["totals"] == {"gallons": "0.000", "cost": "0.00", "stops": 0}
    assert body["starting_fuel"]["reserve_billed_at_stop"] is None
    assert body["starting_fuel"]["reserve_cost"] == "0.00"
    assert api_client.get(body["links"]["map"]).status_code == 200


@pytest.mark.django_db
def test_trips_planned_without_initial_fuel_read_back_zero(api_setup):
    origin = services.ResolvedLocation(label="Start", lat=37.472041, lng=-110.0)
    destination = services.ResolvedLocation(label="End", lat=37.472041, lng=-102.0)

    trip = plan_trip(TripRequest(origin, destination, max_range_miles=500, mpg=10))

    assert Trip.objects.get(pk=trip.pk).initial_fuel_gallons == Decimal("0.000")
