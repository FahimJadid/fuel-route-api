import re
from dataclasses import dataclass

from geo.exceptions import OutsideUsaError, PlaceNotFoundError
from geo.models import Place, PlaceSource
from geo.normalize import name_key, normalize_name

CITY_STATE_PATTERN = re.compile(r"^\s*(?P<city>.+?)\s*,\s*(?P<state>[A-Za-z]{2})\s*$")

CONTIGUOUS_US_LAT = (24.5, 49.5)
CONTIGUOUS_US_LNG = (-125.0, -66.9)

SOURCE_RANK = {PlaceSource.GAZETTEER: 0, PlaceSource.GNIS: 1, PlaceSource.ALIAS: 2}


@dataclass(frozen=True)
class ResolvedLocation:
    label: str
    lat: float
    lng: float
    place: Place | None = None


def resolve_text(text: str) -> ResolvedLocation:
    match = CITY_STATE_PATTERN.match(text)
    if match is None:
        raise PlaceNotFoundError(
            f"Could not parse {text!r}. Use 'City, ST' or latitude/longitude.",
            details={"query": text},
        )
    place = resolve_city(match["city"], match["state"])
    return ResolvedLocation(
        label=f"{place.name}, {place.state}",
        lat=place.location.y,
        lng=place.location.x,
        place=place,
    )


def resolve_city(city: str, state: str) -> Place:
    state = state.upper()
    candidates = list(Place.objects.filter(state=state, name_normalized=normalize_name(city)))
    if not candidates:
        candidates = list(Place.objects.filter(state=state, name_key=name_key(city)))
    if not candidates:
        raise PlaceNotFoundError(
            f"No place named {city!r} in {state}.", details={"city": city, "state": state}
        )
    return min(candidates, key=_preference)


def resolve_coordinates(lat: float, lng: float) -> ResolvedLocation:
    if not (CONTIGUOUS_US_LAT[0] <= lat <= CONTIGUOUS_US_LAT[1]) or not (
        CONTIGUOUS_US_LNG[0] <= lng <= CONTIGUOUS_US_LNG[1]
    ):
        raise OutsideUsaError(
            "Coordinates must lie within the contiguous United States.",
            details={"lat": lat, "lng": lng},
        )
    return ResolvedLocation(label=f"{lat:.4f}, {lng:.4f}", lat=lat, lng=lng)


def _preference(place: Place) -> tuple[int, int, float, int]:
    return (SOURCE_RANK[place.source], place.priority, -(place.land_area_sqmi or 0), place.id)
