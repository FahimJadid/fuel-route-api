from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser

from geo.services.importer import import_places
from geo.sources import read_aliases, read_gazetteer, read_gnis

DATA_DIR = Path(settings.BASE_DIR) / "data"


class Command(BaseCommand):
    help = "Load US place centroids from the Census Gazetteer, USGS GNIS and the alias file."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--gazetteer", type=Path, default=DATA_DIR / "2026_Gaz_place_national.txt"
        )
        parser.add_argument("--gnis", type=Path, default=DATA_DIR / "gnis_populated_places.csv.gz")
        parser.add_argument("--aliases", type=Path, default=DATA_DIR / "city_aliases.csv")

    def handle(self, *args, **options) -> None:
        sources = [
            ("gazetteer", options["gazetteer"], read_gazetteer),
            ("gnis", options["gnis"], read_gnis),
            ("aliases", options["aliases"], read_aliases),
        ]
        for label, path, reader in sources:
            if not path.exists():
                self.stdout.write(f"{label}: skipped, {path} not found")
                continue
            count = import_places(reader(path))
            self.stdout.write(f"{label}: {count} places")
