from collections.abc import Iterable, Iterator
from itertools import islice

from django.contrib.gis.geos import Point

from geo.models import Place
from geo.normalize import name_key, normalize_name
from geo.sources import PlaceRecord

BATCH_SIZE = 5000
UPDATABLE_FIELDS = [
    "state",
    "name",
    "name_normalized",
    "name_key",
    "place_type",
    "priority",
    "land_area_sqmi",
    "location",
]


def import_places(records: Iterable[PlaceRecord]) -> int:
    imported = 0
    for batch in _batched(map(_to_place, _last_per_source_id(records)), BATCH_SIZE):
        Place.objects.bulk_create(
            batch,
            update_conflicts=True,
            unique_fields=["source", "source_id"],
            update_fields=UPDATABLE_FIELDS,
        )
        imported += len(batch)
    return imported


def _last_per_source_id(records: Iterable[PlaceRecord]) -> Iterator[PlaceRecord]:
    # Postgres rejects an upsert batch that touches the same row twice.
    unique = {(record.source, record.source_id): record for record in records}
    yield from unique.values()


def _to_place(record: PlaceRecord) -> Place:
    return Place(
        source=record.source,
        source_id=record.source_id,
        state=record.state,
        name=record.name,
        name_normalized=normalize_name(record.name),
        name_key=name_key(record.name),
        place_type=record.place_type,
        priority=record.priority,
        land_area_sqmi=record.land_area_sqmi,
        location=Point(record.lng, record.lat, srid=4326),
    )


def _batched(items: Iterator[Place], size: int) -> Iterator[list[Place]]:
    while batch := list(islice(items, size)):
        yield batch
