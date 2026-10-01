from decimal import Decimal

import factory
from django.contrib.gis.geos import Point

from stations.models import Station


class StationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Station

    opis_id = factory.Sequence(lambda n: 1000 + n)
    name = factory.Sequence(lambda n: f"TRUCK STOP #{n}")
    address = "I-40, EXIT 100"
    city = "Amarillo"
    state = "TX"
    rack_id = 600
    price_per_gallon = Decimal("3.499")
    location = factory.LazyFunction(lambda: Point(-101.8313, 35.2220, srid=4326))
