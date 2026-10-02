import uuid

from django.contrib.gis.db import models
from django.core.serializers.json import DjangoJSONEncoder


class Trip(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    origin_label = models.CharField(max_length=120)
    destination_label = models.CharField(max_length=120)
    origin = models.PointField(srid=4326, spatial_index=False)
    destination = models.PointField(srid=4326, spatial_index=False)
    route = models.LineStringField(srid=4326, spatial_index=False)
    distance_miles = models.DecimalField(max_digits=8, decimal_places=1)
    duration_minutes = models.PositiveIntegerField()
    max_range_miles = models.DecimalField(max_digits=6, decimal_places=1)
    mpg = models.DecimalField(max_digits=5, decimal_places=2)
    initial_fuel_gallons = models.DecimalField(max_digits=8, decimal_places=3, default=0)
    corridor_miles = models.DecimalField(max_digits=4, decimal_places=1, default=10)
    stops = models.JSONField(encoder=DjangoJSONEncoder)
    total_gallons = models.DecimalField(max_digits=8, decimal_places=3)
    total_cost = models.DecimalField(max_digits=10, decimal_places=2)
    baseline_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    baseline_stops = models.PositiveSmallIntegerField(null=True, blank=True)
    routing_provider = models.CharField(max_length=16)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self) -> str:
        return f"{self.origin_label} -> {self.destination_label} ({self.distance_miles} mi)"
