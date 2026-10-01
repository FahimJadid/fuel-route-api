from decimal import Decimal
from pathlib import Path

import pytest
from django.core.management import call_command

from geo.services.importer import import_places
from geo.sources import read_gazetteer, read_gnis
from stations.models import Station
from stations.services.importer import import_stations, repair_mojibake

GEO_FIXTURES = Path(__file__).parents[1] / "geo" / "fixtures"
PRICES = Path(__file__).parent / "fixtures" / "prices_sample.csv"

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def places():
    import_places(read_gazetteer(GEO_FIXTURES / "gazetteer_sample.txt"))
    import_places(read_gnis(GEO_FIXTURES / "gnis_sample.csv"))


def test_import_merges_duplicate_ids_into_mean_price_with_sample_count():
    import_stations(PRICES)

    station = Station.objects.get(opis_id=105)
    assert station.price_per_gallon == Decimal("3.346")
    assert station.price_sample_count == 3
    assert station.name == "TA SAGINAW I 75 TRAVEL CENTER"
    assert station.address == "I-75, EXIT 144-B"


def test_import_cleans_whitespace_and_geocodes_from_places():
    import_stations(PRICES)

    station = Station.objects.get(opis_id=7)
    assert station.city == "Big Cabin"
    assert station.price_per_gallon == Decimal("3.007")
    assert station.place.name == "Big Cabin"
    assert (station.location.y, station.location.x) == (36.538520, -95.220912)


def test_import_skips_canada_and_invalid_prices_and_reports_unresolved():
    summary = import_stations(PRICES)

    assert summary.rows_read == 7
    assert summary.rows_outside_usa == 1
    assert summary.rows_invalid_price == 1
    assert summary.stations == 3
    assert summary.geocoded == 2
    assert summary.unresolved == [("TX", "Nowhere")]
    assert not Station.objects.filter(state="AB").exists()
    assert Station.objects.get(opis_id=71108).location is None


def test_import_repairs_double_encoded_names():
    import_stations(PRICES)

    assert Station.objects.get(opis_id=71108).name == "Stuckey’s Travel Center West"


def test_import_is_idempotent():
    import_stations(PRICES)
    import_stations(PRICES)

    assert Station.objects.count() == 3


def test_import_stations_command_prints_summary(capsys):
    call_command("import_stations", file=PRICES)

    output = capsys.readouterr().out
    assert "stations: 3" in output
    assert "unresolved: 1" in output
    assert "Nowhere, TX" in output


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("StuckeyÃ¢â‚¬â„¢s", "Stuckey’s"),
        ("Stuckeyâ€™s", "Stuckey’s"),
        ("Piñon Hills", "Piñon Hills"),
        ("PLAIN ASCII", "PLAIN ASCII"),
    ],
)
def test_repair_mojibake(raw, expected):
    assert repair_mojibake(raw) == expected
