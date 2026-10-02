import random
from decimal import Decimal
from itertools import pairwise

import pytest

from tests.trips.reference_planner import reference_cost
from trips.exceptions import NoFeasiblePlanError
from trips.planner import FuelStation, plan_fuel_stops

RANGE = 500.0
MPG = 10.0


def station(mile: float, price: str, id: int | None = None) -> FuelStation:
    return FuelStation(route_mile=mile, price_per_gallon=Decimal(price), id=id or int(mile))


def stop_miles(plan) -> list[float]:
    return [stop.station.route_mile for stop in plan.stops]


def test_short_trip_with_one_station_buys_the_whole_trip_there():
    plan = plan_fuel_stops([station(120, "3.000")], trip_miles=300, max_range_miles=RANGE, mpg=MPG)

    assert stop_miles(plan) == [120]
    assert plan.stops[0].gallons == pytest.approx(30.0)
    assert plan.total_cost == Decimal("90.00")


def test_no_station_within_range_of_the_origin_is_infeasible():
    with pytest.raises(NoFeasiblePlanError) as excinfo:
        plan_fuel_stops([station(600, "3.000")], trip_miles=900, max_range_miles=RANGE, mpg=MPG)

    assert excinfo.value.details == {"from_mile": 0.0}


def test_gap_longer_than_range_reports_where_coverage_breaks():
    stations = [station(100, "3.000"), station(300, "3.000"), station(900, "3.000")]

    with pytest.raises(NoFeasiblePlanError) as excinfo:
        plan_fuel_stops(stations, trip_miles=1200, max_range_miles=RANGE, mpg=MPG)

    assert excinfo.value.details == {"from_mile": 300.0}


def test_buys_just_enough_to_reach_a_cheaper_station_within_range():
    stations = [station(100, "4.000"), station(550, "3.000")]

    plan = plan_fuel_stops(stations, trip_miles=800, max_range_miles=RANGE, mpg=MPG)

    assert stop_miles(plan) == [100, 550]
    assert plan.stops[0].gallons == pytest.approx(55.0)
    assert plan.stops[1].gallons == pytest.approx(25.0)


def test_fills_up_at_a_cheap_station_when_the_next_cheaper_one_is_out_of_range():
    stations = [station(100, "3.000"), station(550, "4.000"), station(700, "2.500")]

    plan = plan_fuel_stops(stations, trip_miles=1000, max_range_miles=RANGE, mpg=MPG)

    assert stop_miles(plan) == [100, 550, 700]
    assert plan.stops[0].gallons == pytest.approx(60.0)
    assert plan.stops[1].fuel_on_arrival_gallons == pytest.approx(5.0)
    assert plan.stops[1].gallons == pytest.approx(10.0)
    assert plan.stops[2].gallons == pytest.approx(30.0)
    assert plan.total_cost == Decimal("295.00")


def test_cheapest_first_stop_wins_even_when_it_is_not_the_nearest():
    stations = [station(50, "4.000"), station(450, "3.000")]

    plan = plan_fuel_stops(stations, trip_miles=600, max_range_miles=RANGE, mpg=MPG)

    assert stop_miles(plan) == [450]
    assert plan.total_cost == Decimal("180.00")


def test_price_ties_prefer_the_farther_station_for_fewer_stops():
    stations = [station(400, "3.000"), station(500, "3.000"), station(900, "3.000")]

    plan = plan_fuel_stops(stations, trip_miles=1300, max_range_miles=RANGE, mpg=MPG)

    assert stop_miles(plan) == [400, 900]


def test_stations_at_or_beyond_the_destination_are_ignored():
    stations = [station(100, "3.000"), station(300, "1.000"), station(350, "0.500")]

    plan = plan_fuel_stops(stations, trip_miles=300, max_range_miles=RANGE, mpg=MPG)

    assert stop_miles(plan) == [100]


def test_station_at_the_origin_is_a_valid_first_stop():
    stations = [station(0, "3.000", id=1)]

    plan = plan_fuel_stops(stations, trip_miles=200, max_range_miles=RANGE, mpg=MPG)

    assert stop_miles(plan) == [0]
    assert plan.stops[0].gallons == pytest.approx(20.0)


def test_vehicle_parameters_change_the_plan():
    stations = [station(100, "3.000"), station(250, "3.000"), station(400, "3.000")]

    plan = plan_fuel_stops(stations, trip_miles=450, max_range_miles=200, mpg=5)

    assert stop_miles(plan) == [100, 250]
    assert plan.total_gallons == pytest.approx(90.0)


@pytest.mark.parametrize("seed", range(200))
def test_random_instances_satisfy_invariants_and_beat_the_exact_stop_only_reference(seed):
    rng = random.Random(seed)
    trip = rng.uniform(200, 3000)
    stations = [
        station(round(rng.uniform(0, trip), 1), f"{rng.uniform(2.5, 5.0):.3f}", id=index)
        for index in range(rng.randint(1, 40))
    ]
    reference = reference_cost(stations, trip, RANGE, MPG)

    try:
        plan = plan_fuel_stops(stations, trip, RANGE, MPG)
    except NoFeasiblePlanError:
        assert reference is None
        return

    assert reference is not None
    assert plan.total_gallons == pytest.approx(trip / MPG)
    assert plan.total_cost <= reference.quantize(Decimal("0.01")) + Decimal("0.05")
    miles = [0.0, *stop_miles(plan), trip]
    assert all(b - a <= RANGE + 1e-6 for a, b in pairwise(miles))
    assert all(stop.fuel_on_arrival_gallons >= -1e-9 for stop in plan.stops)
    assert all(stop.gallons > 0 for stop in plan.stops)
    first, *later = plan.stops
    assert first.gallons <= RANGE / MPG + first.station.route_mile / MPG + 1e-9
    assert all(stop.gallons <= RANGE / MPG + 1e-9 for stop in later)
