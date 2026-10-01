from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser

from stations.services.importer import import_stations

DEFAULT_FILE = Path(settings.BASE_DIR) / "data" / "fuel-prices-for-be-assessment.csv"


class Command(BaseCommand):
    help = "Load truck stops and diesel prices from the OPIS price file."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--file", type=Path, default=DEFAULT_FILE)

    def handle(self, *args, **options) -> None:
        summary = import_stations(options["file"])
        self.stdout.write(f"rows read: {summary.rows_read}")
        self.stdout.write(f"skipped outside USA: {summary.rows_outside_usa}")
        self.stdout.write(f"skipped invalid price: {summary.rows_invalid_price}")
        self.stdout.write(f"stations: {summary.stations}")
        self.stdout.write(f"geocoded: {summary.geocoded}")
        self.stdout.write(f"unresolved: {len(summary.unresolved)}")
        for state, city in summary.unresolved:
            self.stdout.write(f"  {city}, {state}")
