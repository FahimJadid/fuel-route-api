import logging
from collections.abc import Sequence

import httpx

from routing.exceptions import NoRouteError, RoutingUnavailableError
from routing.types import METERS_PER_MILE, Coordinate, Route

logger = logging.getLogger(__name__)

NO_ROUTE_CODES = {"NoRoute", "NoSegment", "InvalidQuery"}
ATTEMPTS = 2


class OsrmProvider:
    """Public OSRM deployments share one API; attempts rotate through the configured hosts."""

    name = "osrm"

    def __init__(self, base_urls: Sequence[str], timeout_seconds: float, user_agent: str) -> None:
        self._base_urls = [url.rstrip("/") for url in base_urls]
        self._client = httpx.Client(timeout=timeout_seconds, headers={"User-Agent": user_agent})

    def route(self, origin: Coordinate, destination: Coordinate) -> Route:
        path = f"/route/v1/driving/{origin.lng},{origin.lat};{destination.lng},{destination.lat}"
        params = {"overview": "full", "geometries": "geojson", "steps": "false"}
        payload = self._get(path, params)
        if payload.get("code") != "Ok":
            raise self._error_for(payload)
        return _parse_route(payload["routes"][0])

    def _get(self, path: str, params: dict[str, str]) -> dict:
        for attempt in range(ATTEMPTS):
            base_url = self._base_urls[attempt % len(self._base_urls)]
            last = attempt == ATTEMPTS - 1
            try:
                response = self._client.get(base_url + path, params=params)
            except httpx.TransportError as exc:
                logger.warning("OSRM request failed", extra={"host": base_url, "error": str(exc)})
                if last:
                    raise RoutingUnavailableError("Routing service did not respond.") from exc
                continue
            if response.status_code >= 500:
                logger.warning(
                    "OSRM server error", extra={"host": base_url, "status": response.status_code}
                )
                if last:
                    raise RoutingUnavailableError("Routing service returned an error.")
                continue
            try:
                return response.json()
            except ValueError as exc:
                raise RoutingUnavailableError("Routing service returned invalid JSON.") from exc
        raise AssertionError("unreachable")

    @staticmethod
    def _error_for(payload: dict) -> Exception:
        code = payload.get("code", "Unknown")
        message = payload.get("message", "")
        if code in NO_ROUTE_CODES:
            return NoRouteError(
                "No drivable route between these points.", details={"provider_code": code}
            )
        return RoutingUnavailableError(
            f"Routing service error: {code} {message}".strip(), details={"provider_code": code}
        )


def _parse_route(route: dict) -> Route:
    return Route(
        provider=OsrmProvider.name,
        distance_miles=route["distance"] / METERS_PER_MILE,
        duration_minutes=round(route["duration"] / 60),
        geometry=tuple((lng, lat) for lng, lat in route["geometry"]["coordinates"]),
    )
