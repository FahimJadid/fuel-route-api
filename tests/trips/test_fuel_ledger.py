import random
from decimal import Decimal
from pathlib import Path

import pytest
from django.contrib.gis.geos import Point
from django.core.management import call_command

from routing.types import Route
from tests.factories import StationFactory
from tests.trips.reference_planner import reference_cost
from trips import services
from trips.exceptions import NoFeasiblePlanError
from trips.planner import FuelStation, plan_fuel_stops, plan_naive_fill_ups

RANGE = 500.0
MPG = 10.0
TANK = RANGE / MPG


def station(mile: float, price: str, id: int | None = None) -> FuelStation:
    return FuelStation(route_mile=mile, price_per_gallon=Decimal(price), id=id or int(mile))


def ledger_balances(ledger) -> None:
    gallons_in = ledger.carried_in_gallons + ledger.purchased_gallons
    gallons_out = ledger.consumed_gallons + ledger.carried_out_gallons
    assert gallons_in == pytest.approx(gallons_out, abs=1e-6)
    value_in = ledger.carried_in_value + ledger.purchased_cost
    value_out = ledger.consumed_cost + ledger.carried_out_value
    assert value_in == value_out


def test_default_ledger_matches_the_plan_with_nothing_carried():
    plan = plan_fuel_stops([station(100, "3.000"), station(550, "4.000")], 800, RANGE, MPG)

    ledger = plan.ledger
    assert (ledger.carried_in_gallons, ledger.carried_in_price, ledger.carried_in_value) == (
        0.0,
        None,
        Decimal(0),
    )
    assert ledger.purchased_cost == plan.total_cost == Decimal("260.00")
    assert ledger.consumed_gallons == pytest.approx(80.0)
    assert ledger.consumed_cost == Decimal("260.00")
    assert (ledger.carried_out_gallons, ledger.carried_out_price) == (0.0, None)
    ledger_balances(ledger)


def test_end_fuel_is_bought_at_the_last_stop_and_carried_out_at_its_running_average():
    stations = [station(100, "3.000"), station(550, "4.000")]

    plan = plan_fuel_stops(stations, 800, RANGE, MPG, end_fuel_gallons=5)

    assert plan.stops[-1].gallons == pytest.approx(25.0)
    assert plan.stops[-1].reason == "Buy just enough to arrive with 5 gal in reserve."
    assert plan.total_gallons == pytest.approx(85.0)
    ledger = plan.ledger
    assert ledger.purchased_cost == Decimal("280.00")
    assert ledger.carried_out_gallons == pytest.approx(5.0)
    assert ledger.carried_out_value == Decimal("19.17")
    assert ledger.carried_out_price == Decimal("3.834")
    assert ledger.consumed_cost == Decimal("260.83")
    ledger_balances(ledger)


def test_carried_in_fuel_with_a_known_price_is_valued_not_free():
    plan = plan_fuel_stops(
        [station(300, "3.000")],
        600,
        RANGE,
        MPG,
        initial_fuel_gallons=10,
        initial_fuel_price_per_gallon=Decimal("2.500"),
    )

    ledger = plan.ledger
    assert ledger.carried_in_value == Decimal("25.00")
    assert plan.total_cost == Decimal("150.00")
    assert ledger.consumed_cost == Decimal("175.00")
    assert plan.starting_fuel.free_gallons == 10
    ledger_balances(ledger)


def test_mixed_tank_consumes_at_the_weighted_average():
    stations = [station(100, "2.000"), station(550, "4.000")]

    plan = plan_fuel_stops(stations, 800, RANGE, MPG, end_fuel_gallons=10)

    ledger = plan.ledger
    assert plan.stops[0].gallons == pytest.approx(60.0)
    assert plan.stops[1].fuel_on_arrival_gallons == pytest.approx(5.0)
    assert plan.stops[1].gallons == pytest.approx(30.0)
    assert ledger.carried_out_price == Decimal("3.714")
    assert ledger.carried_out_value == Decimal("37.14")
    ledger_balances(ledger)


def test_end_fuel_shrinks_the_usable_range():
    stations = [station(100, "3.000"), station(560, "3.000")]

    assert plan_fuel_stops(stations, 1000, RANGE, MPG).stops
    with pytest.raises(NoFeasiblePlanError):
        plan_fuel_stops(stations, 1000, RANGE, MPG, end_fuel_gallons=45)


def test_zero_stop_trip_carries_the_remaining_fuel_out():
    plan = plan_fuel_stops(
        [], 200, RANGE, MPG, initial_fuel_gallons=30, initial_fuel_price_per_gallon=Decimal("3")
    )

    assert plan.stops == []
    assert plan.ledger.carried_out_gallons == pytest.approx(10.0)
    assert plan.ledger.carried_out_value == Decimal("30.00")
    assert plan.ledger.consumed_cost == Decimal("60.00")
    ledger_balances(plan.ledger)


@pytest.mark.parametrize("seed", range(150))
def test_random_instances_with_reserves_balance_and_beat_the_reference(seed):
    rng = random.Random(seed)
    trip = rng.uniform(200, 3000)
    free = rng.uniform(0, TANK)
    end = rng.uniform(0, TANK / 2)
    price = Decimal(f"{rng.uniform(2.5, 5.0):.3f}") if rng.random() < 0.5 else None
    stations = [
        station(round(rng.uniform(0, trip), 1), f"{rng.uniform(2.5, 5.0):.3f}", id=index)
        for index in range(rng.randint(0, 40))
    ]
    reference = reference_cost(stations, trip, RANGE, MPG, free, end)
    try:
        plan = plan_fuel_stops(stations, trip, RANGE, MPG, free, end, price)
    except NoFeasiblePlanError:
        assert reference is None
        with pytest.raises(NoFeasiblePlanError):
            plan_naive_fill_ups(stations, trip, RANGE, MPG, free, end, price)
        return

    assert reference is not None
    assert plan.total_cost <= reference.quantize(Decimal("0.01")) + Decimal("0.05")
    naive = plan_naive_fill_ups(stations, trip, RANGE, MPG, free, end, price)
    assert plan.total_cost <= naive.total_cost + Decimal("0.05")
    assert plan.total_gallons == pytest.approx(max(trip / MPG + end - free, 0.0))
    for ledger in (plan.ledger, naive.ledger):
        ledger_balances(ledger)
        assert ledger.carried_out_gallons >= end - 1e-6


# API: a two-leg chain where leg two carries in what leg one carried out.

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
        name="MIDWAY",
        location=Point(-105.877348, 37.472041, srid=4326),
        price_per_gallon=Decimal("3.250"),
    )


@pytest.mark.django_db
def test_two_legs_chain_through_the_fuel_ledger(api_client, api_setup):
    leg_one = api_client.post(
        "/api/v1/trips/",
        {"origin": ORIGIN, "destination": DESTINATION, "end_fuel_gallons": 5},
        format="json",
    ).json()

    assert leg_one["totals"]["gallons"] == "49.000"
    assert leg_one["fuel_ledger"] == {
        "carried_in": {"gallons": 0.0, "price_per_gallon": None, "value": "0.00"},
        "purchased": {"gallons": 49.0, "cost": "159.25"},
        "consumed": {"gallons": 44.0, "cost": "143.00"},
        "carried_out": {"gallons": 5.0, "price_per_gallon": "3.250", "value": "16.25"},
    }
    assert leg_one["assumptions"]["end_fuel_gallons"] == "5.000"

    carried = leg_one["fuel_ledger"]["carried_out"]
    leg_two = api_client.post(
        "/api/v1/trips/",
        {
            "origin": ORIGIN,
            "destination": DESTINATION,
            "initial_fuel_gallons": carried["gallons"],
            "initial_fuel_price_per_gallon": carried["price_per_gallon"],
        },
        format="json",
    ).json()

    assert leg_two["fuel_ledger"]["carried_in"] == {
        "gallons": 5.0,
        "price_per_gallon": "3.250",
        "value": "16.25",
    }
    assert leg_two["totals"]["gallons"] == "39.000"
    assert leg_two["fuel_ledger"]["purchased"]["cost"] == "126.75"
    assert leg_two["fuel_ledger"]["consumed"]["cost"] == "143.00"
    assert leg_two["fuel_ledger"]["carried_out"]["gallons"] == 0.0
    assert api_client.get(leg_two["links"]["map"]).status_code == 200


@pytest.mark.django_db
def test_end_fuel_above_capacity_is_a_400(api_client, api_setup):
    response = api_client.post(
        "/api/v1/trips/",
        {"origin": ORIGIN, "destination": DESTINATION, "end_fuel_gallons": 60},
        format="json",
    )

    assert response.status_code == 400
    assert "end_fuel_gallons" in response.json()["error"]["details"]
