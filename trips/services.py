from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.contrib.gis.geos import LineString, Point

from geo.services.resolver import ResolvedLocation
from routing.service import get_route
from routing.types import Coordinate, Route
from stations.models import Station
from stations.selectors import stations_along_route
from trips.exceptions import NoFeasiblePlanError
from trips.models import Trip
from trips.planner import (
    FuelPlan,
    FuelStation,
    FuelStop,
    plan_fuel_stops,
    plan_naive_fill_ups,
)


@dataclass(frozen=True)
class TripRequest:
    origin: ResolvedLocation
    destination: ResolvedLocation
    max_range_miles: float
    mpg: float
    initial_fuel_gallons: float = 0.0
    end_fuel_gallons: float = 0.0
    initial_fuel_price_per_gallon: Decimal | None = None


def plan_trip(request: TripRequest) -> Trip:
    route = get_route(
        Coordinate(request.origin.lat, request.origin.lng),
        Coordinate(request.destination.lat, request.destination.lng),
    )
    corridor_miles = settings.FUEL_PLANNING["CORRIDOR_MILES"]
    corridor = stations_along_route(route.geometry, route.distance_miles, corridor_miles)
    candidates = [
        FuelStation(route_mile=s.route_mile, price_per_gallon=s.price_per_gallon, id=s.id)
        for s in corridor
    ]
    vehicle = (route.distance_miles, request.max_range_miles, request.mpg)
    tank = {
        "initial_fuel_gallons": request.initial_fuel_gallons,
        "end_fuel_gallons": request.end_fuel_gallons,
        "initial_fuel_price_per_gallon": request.initial_fuel_price_per_gallon,
    }
    try:
        plan = plan_fuel_stops(candidates, *vehicle, **tank)
    except NoFeasiblePlanError as exc:
        exc.details.update(_route_details(route))
        raise
    baseline = _baseline(candidates, vehicle, tank)

    stations_by_id = {station.id: station for station in corridor}
    return Trip.objects.create(
        origin_label=request.origin.label,
        destination_label=request.destination.label,
        origin=Point(request.origin.lng, request.origin.lat, srid=4326),
        destination=Point(request.destination.lng, request.destination.lat, srid=4326),
        route=LineString(route.geometry, srid=4326),
        distance_miles=_decimal(route.distance_miles, "0.1"),
        duration_minutes=route.duration_minutes,
        max_range_miles=_decimal(request.max_range_miles, "0.1"),
        mpg=_decimal(request.mpg, "0.01"),
        initial_fuel_gallons=_decimal(request.initial_fuel_gallons, "0.001"),
        initial_fuel_price_per_gallon=request.initial_fuel_price_per_gallon,
        end_fuel_gallons=_decimal(request.end_fuel_gallons, "0.001"),
        fuel_ledger=_ledger_snapshot(plan),
        corridor_miles=_decimal(corridor_miles, "0.1"),
        stops=[
            _stop_snapshot(sequence, stop, stations_by_id[stop.station.id])
            for sequence, stop in enumerate(plan.stops, start=1)
        ],
        total_gallons=_decimal(plan.total_gallons, "0.001"),
        total_cost=plan.total_cost,
        baseline_cost=baseline.total_cost if baseline else None,
        baseline_stops=len(baseline.stops) if baseline else None,
        routing_provider=route.provider,
    )


def _baseline(
    candidates: list[FuelStation], vehicle: tuple[float, float, float], tank: dict
) -> FuelPlan | None:
    try:
        return plan_naive_fill_ups(candidates, *vehicle, **tank)
    except NoFeasiblePlanError:
        return None


def _ledger_snapshot(plan: FuelPlan) -> dict:
    ledger = plan.ledger
    return {
        "carried_in": {
            "gallons": round(ledger.carried_in_gallons, 3),
            "price_per_gallon": _money(ledger.carried_in_price),
            "value": str(ledger.carried_in_value),
        },
        "purchased": {
            "gallons": round(ledger.purchased_gallons, 3),
            "cost": str(ledger.purchased_cost),
        },
        "consumed": {
            "gallons": round(ledger.consumed_gallons, 3),
            "cost": str(ledger.consumed_cost),
        },
        "carried_out": {
            "gallons": round(ledger.carried_out_gallons, 3),
            "price_per_gallon": _money(ledger.carried_out_price),
            "value": str(ledger.carried_out_value),
        },
    }


def _money(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _stop_snapshot(sequence: int, stop: FuelStop, station: Station) -> dict:
    return {
        "sequence": sequence,
        "station": {
            "id": station.id,
            "opis_id": station.opis_id,
            "name": station.name,
            "address": station.address,
            "city": station.city,
            "state": station.state,
            "lat": station.location.y,
            "lng": station.location.x,
        },
        "route_mile": round(stop.station.route_mile, 1),
        "detour_miles": round(station.detour_miles, 1),
        "price_per_gallon": str(stop.station.price_per_gallon),
        "gallons": round(stop.gallons, 3),
        "cost": str(stop.cost),
        "fuel_on_arrival_gallons": round(stop.fuel_on_arrival_gallons, 3),
        "fuel_on_departure_gallons": round(stop.fuel_on_arrival_gallons + stop.gallons, 3),
        "action": stop.action,
        "reason": stop.reason,
    }


def _route_details(route: Route) -> dict:
    return {
        "distance_miles": round(route.distance_miles, 1),
        "route": {"type": "LineString", "coordinates": [list(point) for point in route.geometry]},
    }


def _decimal(value: float, precision: str) -> Decimal:
    return Decimal(value).quantize(Decimal(precision))
