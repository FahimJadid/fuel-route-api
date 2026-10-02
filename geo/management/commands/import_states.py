import json
from pathlib import Path

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.core.management.base import BaseCommand, CommandError, CommandParser

from geo.models import State

DEFAULT_FILE = Path(settings.BASE_DIR) / "data" / "conus_states.geojson"


class Command(BaseCommand):
    help = "Load the contiguous US state boundaries used to validate coordinates."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--file", type=Path, default=DEFAULT_FILE)

    def handle(self, *args, **options) -> None:
        path = options["file"]
        if not path.exists():
            raise CommandError(f"state boundary file not found: {path}")
        with open(path, encoding="utf-8") as file:
            features = json.load(file)["features"]
        states = [
            State(
                usps=feature["properties"]["STUSPS"],
                name=feature["properties"]["NAME"],
                boundary=_multipolygon(feature["geometry"]),
            )
            for feature in features
        ]
        State.objects.bulk_create(
            states,
            update_conflicts=True,
            unique_fields=["usps"],
            update_fields=["name", "boundary"],
        )
        self.stdout.write(f"states: {len(states)}")


def _multipolygon(geometry: dict) -> MultiPolygon:
    shape = GEOSGeometry(json.dumps(geometry), srid=4326)
    return shape if isinstance(shape, MultiPolygon) else MultiPolygon(shape, srid=4326)
