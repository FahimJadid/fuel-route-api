"""Cost-optimal fuel stops along a fixed route.

The truck starts with just enough reserve to reach its first stop, and that reserve is billed at
the first stop's price, as if the driver had filled there before leaving. Fuel already in the
tank (``initial_fuel_gallons``) is not bought on this trip; it carries the price it was bought at
on an earlier leg, or no price at all. From any stop the rule is the classic one for the
gas-station problem: if a cheaper station is reachable, buy just enough to get there; otherwise
fill the tank and drive to the cheapest reachable station. Every feasible first stop is tried
and the cheapest plan wins. ``end_fuel_gallons`` asks the plan to arrive with that much still in
the tank, which the next leg then carries in.

``plan_naive_fill_ups`` is the baseline a driver without price data follows (drive as far as the
tank allows, then fill it); the difference between the two is the value of optimising.
"""

from bisect import bisect_right
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from trips.exceptions import NoFeasiblePlanError

GALLON_PRECISION = Decimal("0.001")
CENT = Decimal("0.01")

FILL_UP = "fill_up"
PARTIAL = "partial"
FINAL_LEG = "final_leg"


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
    action: str = ""
    reason: str = ""

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
class FuelLedger:
    """Tank inventory at weighted-average cost: carried in + purchased = consumed + carried out."""

    carried_in_gallons: float
    carried_in_price: Decimal | None
    carried_in_value: Decimal
    purchased_gallons: float
    purchased_cost: Decimal
    consumed_gallons: float
    consumed_cost: Decimal
    carried_out_gallons: float
    carried_out_price: Decimal | None
    carried_out_value: Decimal


@dataclass(frozen=True)
class FuelPlan:
    stops: list[FuelStop]
    total_gallons: float
    total_cost: Decimal = field(compare=False)
    starting_fuel: StartingFuel = field(default=StartingFuel(0.0, 0.0, None, Decimal(0)))
    ledger: FuelLedger | None = field(default=None, compare=False)


@dataclass(frozen=True)
class Tank:
    capacity_gallons: float
    initial_gallons: float = 0.0
    initial_price: Decimal | None = None
    end_gallons: float = 0.0


def fuel_cost(gallons: float, price_per_gallon: Decimal) -> Decimal:
    quantity = Decimal(gallons).quantize(GALLON_PRECISION, rounding=ROUND_HALF_UP)
    return (quantity * price_per_gallon).quantize(CENT, rounding=ROUND_HALF_UP)


def plan_fuel_stops(
    stations: list[FuelStation],
    trip_miles: float,
    max_range_miles: float,
    mpg: float,
    initial_fuel_gallons: float = 0.0,
    end_fuel_gallons: float = 0.0,
    initial_fuel_price_per_gallon: Decimal | None = None,
) -> FuelPlan:
    tank = Tank(
        max_range_miles / mpg, initial_fuel_gallons, initial_fuel_price_per_gallon, end_fuel_gallons
    )
    fuel_target_miles = trip_miles + end_fuel_gallons * mpg
    if initial_fuel_gallons * mpg >= fuel_target_miles:
        return _no_stop_plan(tank, trip_miles, mpg)

    stations = sorted(s for s in stations if 0 <= s.route_mile < trip_miles)
    first_candidates = [s for s in stations if s.route_mile <= max_range_miles]
    if not first_candidates:
        raise NoFeasiblePlanError(from_mile=0.0)

    best: FuelPlan | None = None
    furthest_failure = 0.0
    for first in first_candidates:
        try:
            plan = _plan_from_first_stop(
                first, stations, trip_miles, fuel_target_miles, max_range_miles, mpg, tank
            )
        except NoFeasiblePlanError as exc:
            furthest_failure = max(furthest_failure, exc.from_mile)
            continue
        if best is None or (plan.total_cost, len(plan.stops)) < (best.total_cost, len(best.stops)):
            best = plan
    if best is None:
        raise NoFeasiblePlanError(from_mile=furthest_failure)
    return best


def plan_naive_fill_ups(
    stations: list[FuelStation],
    trip_miles: float,
    max_range_miles: float,
    mpg: float,
    initial_fuel_gallons: float = 0.0,
    end_fuel_gallons: float = 0.0,
    initial_fuel_price_per_gallon: Decimal | None = None,
) -> FuelPlan:
    tank = Tank(
        max_range_miles / mpg, initial_fuel_gallons, initial_fuel_price_per_gallon, end_fuel_gallons
    )
    fuel_target_miles = trip_miles + end_fuel_gallons * mpg
    if initial_fuel_gallons * mpg >= fuel_target_miles:
        return _no_stop_plan(tank, trip_miles, mpg)

    stations = sorted(s for s in stations if 0 <= s.route_mile < trip_miles)
    miles = [s.route_mile for s in stations]
    position, fuel = 0.0, initial_fuel_gallons
    stops: list[FuelStop] = []
    reserve = 0.0

    while fuel_target_miles - position > fuel * mpg + 1e-9:
        reach = position + (max_range_miles if not stops else fuel * mpg)
        candidates = stations[bisect_right(miles, position) : bisect_right(miles, reach)]
        if not candidates:
            raise NoFeasiblePlanError(from_mile=position)
        station = candidates[-1]
        leg_gallons = (station.route_mile - position) / mpg
        if not stops:
            reserve = max(leg_gallons - fuel, 0.0)
            arrival = max(fuel - leg_gallons, 0.0)
        else:
            arrival = fuel - leg_gallons
        remaining_gallons = (fuel_target_miles - station.route_mile) / mpg
        buy = min(tank.capacity_gallons - arrival, remaining_gallons - arrival)
        action = FINAL_LEG if remaining_gallons <= tank.capacity_gallons else FILL_UP
        stops.append(
            FuelStop(
                station,
                fuel_on_arrival_gallons=arrival,
                gallons=(reserve if not stops else 0.0) + max(buy, 0.0),
                action=action,
                reason="Farthest reachable station; fill the tank.",
            )
        )
        position, fuel = station.route_mile, arrival + max(buy, 0.0)

    return _finish_plan(stops, reserve, tank, trip_miles, mpg)


def _plan_from_first_stop(
    first: FuelStation,
    stations: list[FuelStation],
    trip_miles: float,
    fuel_target_miles: float,
    max_range_miles: float,
    mpg: float,
    tank: Tank,
) -> FuelPlan:
    miles = [s.route_mile for s in stations]
    reserve = max(first.route_mile / mpg - tank.initial_gallons, 0.0)
    fuel = max(tank.initial_gallons - first.route_mile / mpg, 0.0)
    stops = [FuelStop(first, fuel_on_arrival_gallons=fuel, gallons=reserve)]
    current = first

    while True:
        remaining = fuel_target_miles - current.route_mile
        reachable = stations[
            bisect_right(miles, current.route_mile) : bisect_right(
                miles, current.route_mile + max_range_miles
            )
        ]
        cheaper = [s for s in reachable if s.price_per_gallon < current.price_per_gallon]

        if remaining <= max_range_miles and not cheaper:
            stops[-1].gallons += max(remaining / mpg - fuel, 0.0)
            stops[-1].action = FINAL_LEG
            stops[-1].reason = (
                "Buy just enough to reach the destination."
                if tank.end_gallons == 0
                else f"Buy just enough to arrive with {tank.end_gallons:g} gal in reserve."
            )
            break
        if cheaper:
            nxt = cheaper[0]
            buy = (nxt.route_mile - current.route_mile) / mpg - fuel
            stops[-1].action = PARTIAL
            stops[-1].reason = (
                f"Buy just enough to reach cheaper fuel (${nxt.price_per_gallon}/gal) "
                f"at mile {nxt.route_mile:.0f}."
            )
        elif reachable:
            nxt = min(reachable, key=lambda s: (s.price_per_gallon, -s.route_mile))
            buy = tank.capacity_gallons - fuel
            stops[-1].action = FILL_UP
            stops[-1].reason = (
                f"Fill the tank: nothing cheaper within range; next stop at mile "
                f"{nxt.route_mile:.0f}."
            )
        else:
            raise NoFeasiblePlanError(from_mile=current.route_mile)

        buy = max(buy, 0.0)
        stops[-1].gallons += buy
        fuel = fuel + buy - (nxt.route_mile - current.route_mile) / mpg
        current = nxt
        stops.append(FuelStop(current, fuel_on_arrival_gallons=fuel))

    return _finish_plan(stops, reserve, tank, trip_miles, mpg)


def _finish_plan(
    stops: list[FuelStop], reserve: float, tank: Tank, trip_miles: float, mpg: float
) -> FuelPlan:
    purchases = [stop for stop in stops if stop.gallons > 0]
    first_price = stops[0].station.price_per_gallon
    return FuelPlan(
        stops=purchases,
        total_gallons=sum(stop.gallons for stop in purchases),
        total_cost=sum((stop.cost for stop in purchases), Decimal(0)),
        starting_fuel=StartingFuel(
            free_gallons=tank.initial_gallons,
            reserve_gallons=reserve,
            reserve_billed_at_stop=1 if reserve > 0 else None,
            reserve_cost=fuel_cost(reserve, first_price),
        ),
        ledger=build_ledger(purchases, reserve, tank, trip_miles, mpg),
    )


def _no_stop_plan(tank: Tank, trip_miles: float, mpg: float) -> FuelPlan:
    return FuelPlan(
        stops=[],
        total_gallons=0.0,
        total_cost=Decimal(0),
        starting_fuel=StartingFuel(tank.initial_gallons, 0.0, None, Decimal(0)),
        ledger=build_ledger([], 0.0, tank, trip_miles, mpg),
    )


def build_ledger(
    stops: list[FuelStop], reserve: float, tank: Tank, trip_miles: float, mpg: float
) -> FuelLedger:
    """Walk the trip keeping the tank's gallons and value; consumption draws at the running average.

    The reserve is burned before the first stop but billed there, so it enters the tank at the
    origin at the first stop's price and the first purchase is the stop's cost minus that.
    """
    carried_in_value = (
        fuel_cost(tank.initial_gallons, tank.initial_price) if tank.initial_price else Decimal(0)
    )
    reserve_value = fuel_cost(reserve, stops[0].station.price_per_gallon) if stops else Decimal(0)
    gallons, value = tank.initial_gallons + reserve, carried_in_value + reserve_value
    position = 0.0
    purchased_cost = Decimal(0)
    for index, stop in enumerate(stops):
        burned = (stop.station.route_mile - position) / mpg
        if gallons > 0:
            value -= value * Decimal(min(burned / gallons, 1.0))
        gallons = max(gallons - burned, 0.0)
        purchase = stop.cost - reserve_value if index == 0 else stop.cost
        gallons += stop.gallons - (reserve if index == 0 else 0.0)
        value += purchase
        purchased_cost += stop.cost
        position = stop.station.route_mile
    burned = (trip_miles - position) / mpg
    if gallons > 0:
        value -= value * Decimal(min(burned / gallons, 1.0))
    carried_out_gallons = gallons - burned if gallons - burned > 1e-9 else 0.0
    carried_out_value = (
        value.quantize(CENT, rounding=ROUND_HALF_UP) if carried_out_gallons > 0 else Decimal(0)
    )
    carried_out_price = (
        (carried_out_value / Decimal(carried_out_gallons)).quantize(GALLON_PRECISION)
        if carried_out_gallons > 0
        else None
    )
    purchased_gallons = sum(stop.gallons for stop in stops)
    return FuelLedger(
        carried_in_gallons=tank.initial_gallons,
        carried_in_price=tank.initial_price,
        carried_in_value=carried_in_value,
        purchased_gallons=purchased_gallons,
        purchased_cost=purchased_cost,
        consumed_gallons=trip_miles / mpg,
        consumed_cost=(carried_in_value + purchased_cost - carried_out_value).quantize(CENT),
        carried_out_gallons=carried_out_gallons,
        carried_out_price=carried_out_price,
        carried_out_value=carried_out_value,
    )
