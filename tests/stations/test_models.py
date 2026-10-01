from decimal import Decimal

import pytest
from django.db import IntegrityError

from tests.factories import StationFactory

pytestmark = pytest.mark.django_db


def test_station_rejects_non_positive_price():
    with pytest.raises(IntegrityError):
        StationFactory(price_per_gallon=Decimal("0"))


def test_station_opis_id_is_unique():
    StationFactory(opis_id=7)

    with pytest.raises(IntegrityError):
        StationFactory(opis_id=7)


def test_station_may_exist_without_a_resolved_location():
    station = StationFactory(location=None, place=None)

    assert station.location is None
    assert str(station) == f"{station.name} (Amarillo, TX)"
