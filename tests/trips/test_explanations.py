import random
from decimal import Decimal
from pathlib import Path

import pytest
from django.contrib.gis.geos import Point
from django.core.management import call_command

from routing.types import Route
from stations.selectors import stations_along_route
from tests.factories import StationFactory
from trips import services
from trips.exceptions import NoFeasiblePlanError
from trips.planner import (
    FILL_UP,
    FINAL_LEG,
    PARTIAL,
    FuelStation,
    plan_fuel_stops,
    plan_naive_fill_ups,
)

RANGE = 500.0
MPG = 10.0


def station(mile: float, price: str, id: int | None = None) -> FuelStation:
    return FuelStation(route_mile=mile, price_per_gallon=Decimal(price), id=id or int(mile))


def test_each_stop_explains_its_purchase():
    stations = [station(100, "3.000"), station(550, "4.000"), station(700, "2.500")]

    plan = plan_fuel_stops(stations, 1000, RANGE, MPG)

    assert [stop.action for stop in plan.stops] == [FILL_UP, PARTIAL, FINAL_LEG]
    assert plan.stops[0].reason == (
        "Fill the tank: nothing cheaper within range; next stop at mile 550."
    )
    assert plan.stops[1].reason == (
        "Buy just enough to reach cheaper fuel ($2.500/gal) at mile 700."
    )
    assert plan.stops[2].reason == "Buy just enough to reach the destination."


def test_naive_driver_fills_the_tank_at_the_farthest_reachable_station():
    stations = [station(100, "3.000"), station(450, "4.000"), station(700, "2.500")]

    naive = plan_naive_fill_ups(stations, 1000, RANGE, MPG)

    assert [stop.station.route_mile for stop in naive.stops] == [450, 700]
    assert naive.stops[0].gallons == pytest.approx(45.0 + 50.0)
    assert naive.stops[0].action == FILL_UP
    assert naive.stops[1].fuel_on_arrival_gallons == pytest.approx(25.0)
    assert naive.stops[1].gallons == pytest.approx(5.0)
    assert naive.stops[1].action == FINAL_LEG
    assert naive.total_gallons == pytest.approx(100.0)
    assert naive.total_cost == Decimal("392.50")


def test_naive_plan_respects_free_initial_fuel_and_zero_stop_trips():
    assert plan_naive_fill_ups([station(100, "3.000")], 300, RANGE, MPG, 40).stops == []

    naive = plan_naive_fill_ups([station(300, "3.000")], 600, RANGE, MPG, initial_fuel_gallons=10)

    assert naive.stops[0].fuel_on_arrival_gallons == 0.0
    assert naive.starting_fuel.reserve_gallons == pytest.approx(20.0)
    assert naive.total_gallons == pytest.approx(50.0)


def test_naive_plan_reports_where_coverage_breaks():
    with pytest.raises(NoFeasiblePlanError) as excinfo:
        plan_naive_fill_ups([station(100, "3.000"), station(900, "3.000")], 1200, RANGE, MPG)

    assert excinfo.value.details == {"from_mile": 100.0}


@pytest.mark.parametrize("seed", range(200))
def test_optimal_plan_never_costs_more_than_the_naive_one(seed):
    rng = random.Random(seed)
    trip = rng.uniform(200, 3000)
    free = rng.choice([0.0, rng.uniform(0, RANGE / MPG)])
    stations = [
        station(round(rng.uniform(0, trip), 1), f"{rng.uniform(2.5, 5.0):.3f}", id=index)
        for index in range(rng.randint(1, 40))
    ]
    try:
        optimal = plan_fuel_stops(stations, trip, RANGE, MPG, initial_fuel_gallons=free)
    except NoFeasiblePlanError:
        with pytest.raises(NoFeasiblePlanError):
            plan_naive_fill_ups(stations, trip, RANGE, MPG, initial_fuel_gallons=free)
        return

    naive = plan_naive_fill_ups(stations, trip, RANGE, MPG, initial_fuel_gallons=free)

    assert optimal.total_cost <= naive.total_cost + Decimal("0.05")
    assert naive.total_gallons == pytest.approx(optimal.total_gallons)
    assert all(stop.action in {FILL_UP, PARTIAL, FINAL_LEG} for stop in optimal.stops)
    assert all(stop.reason for stop in optimal.stops)
    assert all(stop.gallons <= RANGE / MPG + 1e-6 for stop in naive.stops[1:])


# Corridor detour and API shape use the same synthetic routes as the other suites.


@pytest.mark.django_db
def test_corridor_reports_how_far_each_station_sits_off_the_route():
    StationFactory(name="on route", location=Point(-99.5, 35.0, srid=4326))
    StationFactory(name="7 miles north", location=Point(-99.0, 35.10, srid=4326))

    found = stations_along_route(((-100.0, 35.0), (-98.0, 35.0)), 113.2, corridor_miles=10)

    by_name = {station.name: station.detour_miles for station in found}
    assert by_name["on route"] < 0.5
    assert by_name["7 miles north"] == pytest.approx(6.9, abs=0.5)


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
    StationFactory(
        name="CHEAP EARLY",
        location=Point(-105.877348, 37.472041, srid=4326),
        price_per_gallon=Decimal("3.000"),
    )
    StationFactory(
        name="PRICEY LATE",
        location=Point(-104.0, 37.472041, srid=4326),
        price_per_gallon=Decimal("4.000"),
    )


@pytest.mark.django_db
def test_response_explains_stops_and_reports_savings_and_assumptions(api_client, api_setup):
    body = api_client.post(
        "/api/v1/trips/", {"origin": ORIGIN, "destination": DESTINATION}, format="json"
    ).json()

    assert [stop["station"]["name"] for stop in body["stops"]] == ["CHEAP EARLY"]
    assert body["stops"][0]["action"] == "final_leg"
    assert body["stops"][0]["reason"] == "Buy just enough to reach the destination."
    assert body["stops"][0]["detour_miles"] == 0.0
    assert body["totals"] == {"gallons": "44.000", "cost": "132.00", "stops": 1}
    assert body["savings"] == {
        "baseline": "fill the tank at the farthest reachable station",
        "baseline_cost": "176.00",
        "baseline_stops": 1,
        "amount": "44.00",
        "percent": "25.0",
    }
    assert body["assumptions"] == {
        "max_range_miles": "500.0",
        "mpg": "10.00",
        "tank_gallons": "50.00",
        "initial_fuel_gallons": "0.000",
        "corridor_miles": "10.0",
        "minimum_purchase_gallons": 0,
        "reserve_rule": "fuel needed to reach the first stop is billed at that stop",
        "detour_cost_modelled": False,
        "routing_profile": "car",
    }
    assert "Saves <strong>$44.00</strong>" in api_client.get(body["links"]["map"]).content.decode()
