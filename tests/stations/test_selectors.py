from decimal import Decimal

import pytest
from django.contrib.gis.geos import Point

from stations.selectors import stations_along_route
from tests.factories import StationFactory

pytestmark = pytest.mark.django_db

# Straight east-west route along 35°N; one degree of longitude there is about 56.6 miles.
ROUTE = ((-100.0, 35.0), (-98.0, 35.0))
ROUTE_MILES = 113.2


def station_at(lng: float, lat: float, **kwargs):
    return StationFactory(location=Point(lng, lat, srid=4326), **kwargs)


def test_returns_only_stations_inside_the_corridor_ordered_by_route_mile():
    far_north = station_at(-99.0, 35.30, name="20 miles off")
    on_route = station_at(-99.5, 35.0, name="quarter way")
    near = station_at(-99.0, 35.10, name="7 miles north")
    station_at(-101.0, 35.0, name="before the origin")
    StationFactory(location=None, name="never geocoded")

    found = stations_along_route(ROUTE, ROUTE_MILES, corridor_miles=10)

    assert [station.name for station in found] == [on_route.name, near.name]
    assert far_north not in found
    assert found[0].route_mile == pytest.approx(ROUTE_MILES / 4, abs=0.5)
    assert found[1].route_mile == pytest.approx(ROUTE_MILES / 2, abs=0.5)


def test_corridor_width_is_respected():
    station_at(-99.0, 35.20, name="14 miles north")

    assert stations_along_route(ROUTE, ROUTE_MILES, corridor_miles=10) == []
    assert len(stations_along_route(ROUTE, ROUTE_MILES, corridor_miles=15)) == 1


def test_stations_at_the_same_mile_are_ordered_by_price():
    pricey = station_at(-99.5, 35.0, price_per_gallon=Decimal("3.999"))
    cheap = station_at(-99.5, 35.0, price_per_gallon=Decimal("2.999"))

    found = stations_along_route(ROUTE, ROUTE_MILES, corridor_miles=10)

    assert [station.id for station in found] == [cheap.id, pricey.id]
