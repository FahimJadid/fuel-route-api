from dataclasses import dataclass

METERS_PER_MILE = 1609.344


@dataclass(frozen=True)
class Coordinate:
    lat: float
    lng: float


@dataclass(frozen=True)
class Route:
    provider: str
    distance_miles: float
    duration_minutes: int
    geometry: tuple[tuple[float, float], ...]
    """Route vertices as (lng, lat) pairs, the GeoJSON order."""
