import logging
from dataclasses import replace
from functools import cache as memoize

from django.conf import settings
from django.contrib.gis.geos import LineString
from django.core.cache import cache

from routing.providers.base import RoutingProvider
from routing.providers.osrm import OsrmProvider
from routing.types import Coordinate, Route

logger = logging.getLogger(__name__)


def get_route(origin: Coordinate, destination: Coordinate) -> Route:
    provider = get_routing_provider()
    key = _cache_key(provider.name, origin, destination)
    route = cache.get(key)
    if route is not None:
        logger.info("route cache hit", extra={"cache_key": key})
        return route
    route = provider.route(origin, destination)
    route = replace(route, geometry=_simplify(route.geometry))
    cache.set(key, route, timeout=settings.ROUTING["CACHE_SECONDS"])
    return route


@memoize
def get_routing_provider() -> RoutingProvider:
    config = settings.ROUTING
    return OsrmProvider(
        base_urls=config["OSRM_BASE_URLS"],
        timeout_seconds=config["TIMEOUT_SECONDS"],
        user_agent=config["USER_AGENT"],
    )


def _cache_key(provider: str, origin: Coordinate, destination: Coordinate) -> str:
    # Four decimals is ~11 m, so nearby requests for the same pair share one route.
    return (
        f"route:{provider}:{origin.lat:.4f},{origin.lng:.4f}"
        f":{destination.lat:.4f},{destination.lng:.4f}"
    )


def _simplify(geometry: tuple[tuple[float, float], ...]) -> tuple[tuple[float, float], ...]:
    if len(geometry) < 2:
        return (geometry[0], geometry[0])
    tolerance = settings.ROUTING["SIMPLIFY_TOLERANCE_DEGREES"]
    simplified = LineString(geometry, srid=4326).simplify(tolerance, preserve_topology=True)
    return tuple(simplified.coords)
