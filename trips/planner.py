"""Cost-optimal fuel stops along a fixed route.

The truck starts with just enough reserve to reach its first stop, and that reserve is billed at
the first stop's price, as if the driver had filled there before leaving. Fuel already in the
tank (``initial_fuel_gallons``) is free; only the shortfall to the first stop is billed. From any
stop the rule is the classic one for the gas-station problem: if a cheaper station is reachable,
buy just enough to get there; otherwise fill the tank and drive to the cheapest reachable
station. Every feasible first stop is tried and the cheapest plan wins.
"""

from bisect import bisect_right
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from trips.exceptions import NoFeasiblePlanError

GALLON_PRECISION = Decimal("0.001")
CENT = Decimal("0.01")


@dataclass(frozen=True, order=True)
class FuelStation:
    route_mile: float
    price_per_gallon: Decimal
    id: int


@dataclass
class FuelStop:
    station: FuelStation
    fuel_on_arrival_gallons: float
    gallons: float = 0.0

    @property
    def cost(self) -> Decimal:
        return fuel_cost(self.gallons, self.station.price_per_gallon)


@dataclass(frozen=True)
class StartingFuel:
    free_gallons: float
    reserve_gallons: float
    reserve_billed_at_stop: int | None
    reserve_cost: Decimal = field(compare=False)


@dataclass(frozen=True)
class FuelPlan:
    stops: list[FuelStop]
    total_gallons: float
    total_cost: Decimal = field(compare=False)
    starting_fuel: StartingFuel = field(default=StartingFuel(0.0, 0.0, None, Decimal(0)))


def fuel_cost(gallons: float, price_per_gallon: Decimal) -> Decimal:
    quantity = Decimal(gallons).quantize(GALLON_PRECISION, rounding=ROUND_HALF_UP)
    return (quantity * price_per_gallon).quantize(CENT, rounding=ROUND_HALF_UP)


def plan_fuel_stops(
    stations: list[FuelStation],
    trip_miles: float,
    max_range_miles: float,
    mpg: float,
    initial_fuel_gallons: float = 0.0,
) -> FuelPlan:
    if initial_fuel_gallons * mpg >= trip_miles:
        return FuelPlan(
            stops=[],
            total_gallons=0.0,
            total_cost=Decimal(0),
            starting_fuel=StartingFuel(initial_fuel_gallons, 0.0, None, Decimal(0)),
        )

    stations = sorted(s for s in stations if 0 <= s.route_mile < trip_miles)
    first_candidates = [s for s in stations if s.route_mile <= max_range_miles]
    if not first_candidates:
        raise NoFeasiblePlanError(from_mile=0.0)

    best: FuelPlan | None = None
    furthest_failure = 0.0
    for first in first_candidates:
        try:
            plan = _plan_from_first_stop(
                first, stations, trip_miles, max_range_miles, mpg, initial_fuel_gallons
            )
        except NoFeasiblePlanError as exc:
            furthest_failure = max(furthest_failure, exc.from_mile)
            continue
        if best is None or (plan.total_cost, len(plan.stops)) < (best.total_cost, len(best.stops)):
            best = plan
    if best is None:
        raise NoFeasiblePlanError(from_mile=furthest_failure)
    return best


def _plan_from_first_stop(
    first: FuelStation,
    stations: list[FuelStation],
    trip_miles: float,
    max_range_miles: float,
    mpg: float,
    initial_fuel_gallons: float,
) -> FuelPlan:
    tank_gallons = max_range_miles / mpg
    miles = [s.route_mile for s in stations]
    reserve = max(first.route_mile / mpg - initial_fuel_gallons, 0.0)
    fuel = max(initial_fuel_gallons - first.route_mile / mpg, 0.0)
    stops = [FuelStop(first, fuel_on_arrival_gallons=fuel, gallons=reserve)]
    current = first

    while True:
        remaining = trip_miles - current.route_mile
        reachable = stations[
            bisect_right(miles, current.route_mile) : bisect_right(
                miles, current.route_mile + max_range_miles
            )
        ]
        cheaper = [s for s in reachable if s.price_per_gallon < current.price_per_gallon]

        if remaining <= max_range_miles and not cheaper:
            stops[-1].gallons += max(remaining / mpg - fuel, 0.0)
            break
        if cheaper:
            nxt = cheaper[0]
            buy = (nxt.route_mile - current.route_mile) / mpg - fuel
        elif reachable:
            nxt = min(reachable, key=lambda s: (s.price_per_gallon, -s.route_mile))
            buy = tank_gallons - fuel
        else:
            raise NoFeasiblePlanError(from_mile=current.route_mile)

        buy = max(buy, 0.0)
        stops[-1].gallons += buy
        fuel = fuel + buy - (nxt.route_mile - current.route_mile) / mpg
        current = nxt
        stops.append(FuelStop(current, fuel_on_arrival_gallons=fuel))

    purchases = [stop for stop in stops if stop.gallons > 0]
    return FuelPlan(
        stops=purchases,
        total_gallons=sum(stop.gallons for stop in purchases),
        total_cost=sum((stop.cost for stop in purchases), Decimal(0)),
        starting_fuel=StartingFuel(
            free_gallons=initial_fuel_gallons,
            reserve_gallons=reserve,
            reserve_billed_at_stop=1 if reserve > 0 else None,
            reserve_cost=fuel_cost(reserve, first.price_per_gallon),
        ),
    )
