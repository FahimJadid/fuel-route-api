from django.contrib.gis.db import models
from django.contrib.gis.db.models.functions import Transform
from django.contrib.postgres.indexes import GistIndex

PLANNING_SRID = 5070


class Station(models.Model):
    opis_id = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=120)
    address = models.CharField(max_length=200)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2, db_index=True)
    rack_id = models.PositiveIntegerField()
    price_per_gallon = models.DecimalField(max_digits=6, decimal_places=3)
    price_sample_count = models.PositiveSmallIntegerField(default=1)
    place = models.ForeignKey(
        "geo.Place", null=True, blank=True, on_delete=models.SET_NULL, related_name="stations"
    )
    location = models.PointField(srid=4326, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(price_per_gallon__gt=0), name="station_price_positive"
            ),
        ]
        indexes = [
            # The corridor query measures distance in the CONUS Albers projection (metres).
            GistIndex(Transform("location", PLANNING_SRID), name="station_location_albers_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.city}, {self.state})"
