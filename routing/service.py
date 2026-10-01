from dataclasses import replace
from functools import cache

from django.conf import settings
from django.contrib.gis.geos import LineString

from routing.providers.base import RoutingProvider
from routing.providers.osrm import OsrmProvider
from routing.types import Coordinate, Route


def get_route(origin: Coordinate, destination: Coordinate) -> Route:
    route = get_routing_provider().route(origin, destination)
    return replace(route, geometry=_simplify(route.geometry))


@cache
def get_routing_provider() -> RoutingProvider:
    config = settings.ROUTING
    return OsrmProvider(
        base_url=config["OSRM_BASE_URL"],
        timeout_seconds=config["TIMEOUT_SECONDS"],
        user_agent=config["USER_AGENT"],
    )


def _simplify(geometry: tuple[tuple[float, float], ...]) -> tuple[tuple[float, float], ...]:
    tolerance = settings.ROUTING["SIMPLIFY_TOLERANCE_DEGREES"]
    simplified = LineString(geometry, srid=4326).simplify(tolerance, preserve_topology=True)
    return tuple(simplified.coords)
