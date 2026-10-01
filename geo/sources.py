import csv
import gzip
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from geo.models import PlaceSource
from geo.normalize import strip_gazetteer_suffix

INCORPORATED_FUNCSTAT = "A"


@dataclass(frozen=True)
class PlaceRecord:
    source: str
    source_id: str
    state: str
    name: str
    lat: float
    lng: float
    place_type: str = ""
    priority: int = 0
    land_area_sqmi: float | None = None


def read_gazetteer(path: Path) -> Iterator[PlaceRecord]:
    with _open_text(path) as file:
        for row in csv.DictReader(file, delimiter="|"):
            row = {key.strip(): value.strip() for key, value in row.items()}
            yield PlaceRecord(
                source=PlaceSource.GAZETTEER,
                source_id=row["GEOID"],
                state=row["USPS"],
                name=strip_gazetteer_suffix(row["NAME"], row["LSAD"]),
                lat=float(row["INTPTLAT"]),
                lng=float(row["INTPTLONG"]),
                place_type=row["LSAD"],
                priority=0 if row["FUNCSTAT"] == INCORPORATED_FUNCSTAT else 1,
                land_area_sqmi=float(row["ALAND_SQMI"].rstrip(".") or 0),
            )


def read_gnis(path: Path) -> Iterator[PlaceRecord]:
    with _open_text(path) as file:
        for row in csv.DictReader(file):
            yield PlaceRecord(
                source=PlaceSource.GNIS,
                source_id=row["feature_id"],
                state=row["state"],
                name=row["name"],
                lat=float(row["lat"]),
                lng=float(row["lng"]),
                place_type="PPL",
                priority=int(row["priority"]),
            )


def read_aliases(path: Path) -> Iterator[PlaceRecord]:
    with _open_text(path) as file:
        for row in csv.DictReader(file):
            yield PlaceRecord(
                source=PlaceSource.ALIAS,
                source_id=f"{row['state']}:{row['name']}",
                state=row["state"],
                name=row["name"],
                lat=float(row["lat"]),
                lng=float(row["lng"]),
            )


def _open_text(path: Path) -> IO[str]:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return open(path, encoding="utf-8", newline="")
