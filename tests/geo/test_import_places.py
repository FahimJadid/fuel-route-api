from pathlib import Path

import pytest
from django.core.management import call_command

from geo.models import Place, PlaceSource
from geo.services.importer import import_places
from geo.sources import read_aliases, read_gazetteer, read_gnis

FIXTURES = Path(__file__).parent / "fixtures"


def test_read_gazetteer_strips_suffix_and_ranks_incorporated_first():
    records = {record.name: record for record in read_gazetteer(FIXTURES / "gazetteer_sample.txt")}

    assert set(records) == {"Big Cabin", "Alamosa", "Alamosa East"}
    assert records["Alamosa"].priority == 0
    assert records["Alamosa East"].priority == 1
    assert records["Alamosa"].land_area_sqmi == pytest.approx(4.424)
    assert (records["Big Cabin"].lat, records["Big Cabin"].lng) == (36.538520, -95.220912)


def test_read_gnis_and_aliases():
    gnis = list(read_gnis(FIXTURES / "gnis_sample.csv"))
    aliases = list(read_aliases(FIXTURES / "aliases_sample.csv"))

    assert [record.name for record in gnis] == ["Big Cabin", "Sterling"]
    assert gnis[0].source == PlaceSource.GNIS
    assert aliases[0].source == PlaceSource.ALIAS
    assert aliases[0].source_id == "OK:S Coffeyville"


@pytest.mark.django_db
def test_import_places_upserts_on_source_id():
    import_places(read_gazetteer(FIXTURES / "gazetteer_sample.txt"))
    import_places(read_gazetteer(FIXTURES / "gazetteer_sample.txt"))

    assert Place.objects.count() == 3
    big_cabin = Place.objects.get(source=PlaceSource.GAZETTEER, source_id="4006050")
    assert big_cabin.name_normalized == "BIG CABIN"
    assert big_cabin.name_key == "BIGCABIN"
    assert big_cabin.location.x == pytest.approx(-95.220912)


@pytest.mark.django_db
def test_import_places_tolerates_repeated_source_ids_in_one_stream():
    records = list(read_gnis(FIXTURES / "gnis_sample.csv"))

    imported = import_places(records + records)

    assert imported == 2
    assert Place.objects.filter(source=PlaceSource.GNIS).count() == 2


@pytest.mark.django_db
def test_import_places_command_loads_every_source(capsys):
    call_command(
        "import_places",
        gazetteer=FIXTURES / "gazetteer_sample.txt",
        gnis=FIXTURES / "gnis_sample.csv",
        aliases=FIXTURES / "aliases_sample.csv",
    )

    output = capsys.readouterr().out
    assert "gazetteer: 3 places" in output
    assert "gnis: 2 places" in output
    assert "aliases: 1 places" in output
    assert Place.objects.filter(state="OK", name_normalized="BIG CABIN").count() == 2
