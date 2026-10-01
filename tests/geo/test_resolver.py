from pathlib import Path

import pytest

from geo.exceptions import OutsideUsaError, PlaceNotFoundError
from geo.models import PlaceSource
from geo.services.importer import import_places
from geo.services.resolver import resolve_city, resolve_coordinates, resolve_text
from geo.sources import read_gazetteer, read_gnis

FIXTURES = Path(__file__).parent / "fixtures"

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def places():
    import_places(read_gazetteer(FIXTURES / "gazetteer_sample.txt"))
    import_places(read_gnis(FIXTURES / "gnis_sample.csv"))


def test_resolve_text_prefers_gazetteer_over_gnis_for_the_same_name():
    location = resolve_text("big cabin , ok")

    assert location.label == "Big Cabin, OK"
    assert location.place.source == PlaceSource.GAZETTEER
    assert (location.lat, location.lng) == (36.538520, -95.220912)


def test_resolve_city_prefers_incorporated_place_over_cdp():
    assert resolve_city("Alamosa", "co").place_type == "25"


def test_resolve_city_falls_back_to_gnis_when_gazetteer_lacks_the_place():
    assert resolve_city("Sterling", "ND").source == PlaceSource.GNIS


def test_resolve_city_matches_spacing_variants_through_name_key():
    assert resolve_city("De Witt", "IA").name == "DeWitt"


def test_resolve_city_unknown_place_raises_with_details():
    with pytest.raises(PlaceNotFoundError) as excinfo:
        resolve_city("Nowhere", "OK")

    assert excinfo.value.details == {"city": "Nowhere", "state": "OK"}


def test_resolve_text_requires_city_comma_state():
    with pytest.raises(PlaceNotFoundError) as excinfo:
        resolve_text("Dallas")

    assert "City, ST" in excinfo.value.message


def test_resolve_coordinates_inside_contiguous_usa():
    location = resolve_coordinates(32.7767, -96.797)

    assert location.label == "32.7767, -96.7970"
    assert location.place is None


@pytest.mark.parametrize(("lat", "lng"), [(21.3, -157.8), (61.2, -149.9), (48.8, 2.3)])
def test_resolve_coordinates_outside_contiguous_usa(lat, lng):
    with pytest.raises(OutsideUsaError):
        resolve_coordinates(lat, lng)
