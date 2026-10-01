from django.contrib.gis.db import models


class PlaceSource(models.TextChoices):
    GAZETTEER = "gazetteer", "Census Gazetteer"
    GNIS = "gnis", "USGS GNIS"
    ALIAS = "alias", "Manual alias"


class Place(models.Model):
    source = models.CharField(max_length=16, choices=PlaceSource.choices)
    source_id = models.CharField(max_length=32)
    state = models.CharField(max_length=2, db_index=True)
    name = models.CharField(max_length=120)
    name_normalized = models.CharField(max_length=120)
    name_key = models.CharField(max_length=120)
    place_type = models.CharField(max_length=4, blank=True)
    priority = models.PositiveSmallIntegerField(default=0)
    land_area_sqmi = models.FloatField(null=True, blank=True)
    location = models.PointField(srid=4326, spatial_index=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["source", "source_id"], name="place_unique_source_id"),
        ]
        indexes = [
            models.Index(fields=["state", "name_normalized"], name="place_state_name_idx"),
            models.Index(fields=["state", "name_key"], name="place_state_key_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.name}, {self.state} ({self.source})"
