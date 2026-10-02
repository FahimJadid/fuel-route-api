"""Exact shortest path over stops where each stop buys only enough fuel to reach the next one.

Used as an independent oracle: the production planner may also top up partially, so its
cost must never exceed this reference.
"""

from decimal import Decimal

from trips.planner import FuelStation


def reference_cost(
    stations: list[FuelStation], trip_miles: float, max_range_miles: float, mpg: float
) -> Decimal | None:
    stations = sorted(s for s in stations if 0 <= s.route_mile < trip_miles)
    best: dict[int, Decimal] = {}
    for index, station in enumerate(stations):
        if station.route_mile > max_range_miles:
            continue
        best[index] = _leg_cost(station, station.route_mile, mpg)
    finish: Decimal | None = None
    for index, station in enumerate(stations):
        if index not in best:
            continue
        here = best[index]
        if trip_miles - station.route_mile <= max_range_miles:
            total = here + _leg_cost(station, trip_miles - station.route_mile, mpg)
            finish = total if finish is None else min(finish, total)
        for nxt_index in range(index + 1, len(stations)):
            nxt = stations[nxt_index]
            leg = nxt.route_mile - station.route_mile
            if leg > max_range_miles:
                break
            candidate = here + _leg_cost(station, leg, mpg)
            if nxt_index not in best or candidate < best[nxt_index]:
                best[nxt_index] = candidate
    return finish


def _leg_cost(station: FuelStation, miles: float, mpg: float) -> Decimal:
    return Decimal(miles / mpg) * station.price_per_gallon
