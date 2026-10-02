"""Exact shortest path over stops where each stop buys only enough fuel to reach the next one.

Used as an independent oracle: the production planner may also top up partially, so its
cost must never exceed this reference. Free starting fuel is modelled as a first layer of
stations that can be reached without buying anything; the first purchase moves to the normal
layer where every arrival happens with no fuel left. A required end reserve simply lengthens
the final leg by the miles that reserve represents.
"""

from decimal import Decimal

from trips.planner import FuelStation


def reference_cost(
    stations: list[FuelStation],
    trip_miles: float,
    max_range_miles: float,
    mpg: float,
    initial_fuel_gallons: float = 0.0,
    end_fuel_gallons: float = 0.0,
) -> Decimal | None:
    free_miles = initial_fuel_gallons * mpg
    target_miles = trip_miles + end_fuel_gallons * mpg
    if free_miles >= target_miles:
        return Decimal(0)
    stations = sorted(s for s in stations if 0 <= s.route_mile < trip_miles)
    free_arrival: dict[int, float] = {}
    best: dict[int, Decimal] = {}
    for index, station in enumerate(stations):
        if station.route_mile > max_range_miles:
            continue
        if station.route_mile <= free_miles:
            free_arrival[index] = initial_fuel_gallons - station.route_mile / mpg
        else:
            best[index] = _leg_cost(station, station.route_mile - free_miles, mpg)

    finish: Decimal | None = None
    for index, station in enumerate(stations):
        leftover = free_arrival.get(index, 0.0)
        here = Decimal(0) if index in free_arrival else best.get(index)
        if here is None:
            continue
        if target_miles - station.route_mile <= max_range_miles:
            final_leg = target_miles - station.route_mile - leftover * mpg
            total = here + _leg_cost(station, final_leg, mpg)
            finish = total if finish is None else min(finish, total)
        for nxt_index in range(index + 1, len(stations)):
            leg = stations[nxt_index].route_mile - station.route_mile
            if leg > max_range_miles:
                break
            if leg <= leftover * mpg:
                continue
            candidate = here + _leg_cost(station, leg - leftover * mpg, mpg)
            if nxt_index not in best or candidate < best[nxt_index]:
                best[nxt_index] = candidate
    return finish


def _leg_cost(station: FuelStation, miles: float, mpg: float) -> Decimal:
    return Decimal(max(miles, 0.0) / mpg) * station.price_per_gallon
