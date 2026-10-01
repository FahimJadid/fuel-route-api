import csv
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

from django.contrib.gis.geos import Point

from geo.exceptions import PlaceNotFoundError
from geo.models import Place
from geo.services.resolver import resolve_city
from stations.models import Station

CANADIAN_PROVINCES = frozenset(
    {"AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT"}
)
PRICE_RANGE = (Decimal("1"), Decimal("20"))
PRICE_PRECISION = Decimal("0.001")
BATCH_SIZE = 2000


@dataclass(frozen=True)
class PriceRow:
    opis_id: int
    name: str
    address: str
    city: str
    state: str
    rack_id: int
    price: Decimal


@dataclass
class MergedStation:
    opis_id: int
    name: str
    address: str
    city: str
    state: str
    rack_id: int
    prices: list[Decimal] = field(default_factory=list)

    @property
    def mean_price(self) -> Decimal:
        total = sum(self.prices, Decimal(0))
        return (total / len(self.prices)).quantize(PRICE_PRECISION, rounding=ROUND_HALF_UP)


@dataclass
class ImportSummary:
    rows_read: int = 0
    rows_outside_usa: int = 0
    rows_invalid_price: int = 0
    stations: int = 0
    geocoded: int = 0
    unresolved: list[tuple[str, str]] = field(default_factory=list)


def import_stations(path: Path) -> ImportSummary:
    summary = ImportSummary()
    merged = _merge_by_station(_usable_rows(path, summary))
    places = _resolve_places(merged.values(), summary)
    for batch in _batched(merged.values(), BATCH_SIZE):
        Station.objects.bulk_create(
            [_to_station(station, places.get((station.state, station.city))) for station in batch],
            update_conflicts=True,
            unique_fields=["opis_id"],
            update_fields=[
                "name",
                "address",
                "city",
                "state",
                "rack_id",
                "price_per_gallon",
                "price_sample_count",
                "place",
                "location",
                "updated_at",
            ],
        )
    summary.stations = len(merged)
    return summary


def read_price_rows(path: Path) -> Iterator[PriceRow]:
    with open(path, encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            yield PriceRow(
                opis_id=int(row["OPIS Truckstop ID"]),
                name=_clean(row["Truckstop Name"]),
                address=_clean(row["Address"]),
                city=_clean(row["City"]),
                state=_clean(row["State"]).upper(),
                rack_id=int(row["Rack ID"]),
                price=_parse_price(row["Retail Price"]),
            )


def repair_mojibake(text: str) -> str:
    # The price file holds UTF-8 bytes that were decoded as cp1252, once or twice over.
    for _ in range(2):
        try:
            repaired = text.encode("cp1252").decode("utf-8")
        except UnicodeError:
            return text
        if repaired == text:
            return text
        text = repaired
    return text


def _usable_rows(path: Path, summary: ImportSummary) -> Iterator[PriceRow]:
    for row in read_price_rows(path):
        summary.rows_read += 1
        if row.state in CANADIAN_PROVINCES:
            summary.rows_outside_usa += 1
        elif row.price is None or not PRICE_RANGE[0] <= row.price <= PRICE_RANGE[1]:
            summary.rows_invalid_price += 1
        else:
            yield row


def _merge_by_station(rows: Iterable[PriceRow]) -> dict[int, MergedStation]:
    merged: dict[int, MergedStation] = {}
    for row in rows:
        station = merged.get(row.opis_id)
        if station is None:
            station = merged[row.opis_id] = MergedStation(
                row.opis_id, row.name, row.address, row.city, row.state, row.rack_id
            )
        station.prices.append(row.price)
    return merged


def _resolve_places(
    stations: Iterable[MergedStation], summary: ImportSummary
) -> dict[tuple[str, str], Place]:
    places: dict[tuple[str, str], Place] = {}
    for key in sorted({(station.state, station.city) for station in stations}):
        try:
            places[key] = resolve_city(city=key[1], state=key[0])
        except PlaceNotFoundError:
            summary.unresolved.append(key)
    summary.geocoded = sum(1 for station in stations if (station.state, station.city) in places)
    return places


def _to_station(merged: MergedStation, place: Place | None) -> Station:
    return Station(
        opis_id=merged.opis_id,
        name=merged.name,
        address=merged.address,
        city=merged.city,
        state=merged.state,
        rack_id=merged.rack_id,
        price_per_gallon=merged.mean_price,
        price_sample_count=len(merged.prices),
        place=place,
        location=Point(place.location.x, place.location.y, srid=4326) if place else None,
    )


def _clean(value: str) -> str:
    return " ".join(repair_mojibake(value).split())


def _parse_price(value: str) -> Decimal | None:
    try:
        return Decimal(value.strip())
    except InvalidOperation:
        return None


def _batched(items: Iterable[MergedStation], size: int) -> Iterator[list[MergedStation]]:
    batch: list[MergedStation] = []
    for item in items:
        batch.append(item)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch
