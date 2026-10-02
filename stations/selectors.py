from collections.abc import Sequence

from django.contrib.gis.geos import LineString

from routing.types import METERS_PER_MILE
from stations.models import PLANNING_SRID, Station

CORRIDOR_SQL = """
WITH route AS MATERIALIZED (
    SELECT ST_Transform(ST_GeomFromText(%(wkt)s, 4326), %(srid)s) AS geom
)
SELECT station.*,
       ST_LineLocatePoint(route.geom, ST_Transform(station.location, %(srid)s))
           * %(distance_miles)s AS route_mile,
       ST_Distance(ST_Transform(station.location, %(srid)s), route.geom)
           / %(meters_per_mile)s AS detour_miles
FROM stations_station AS station, route
WHERE station.location IS NOT NULL
  AND ST_DWithin(ST_Transform(station.location, %(srid)s), route.geom, %(corridor_meters)s)
ORDER BY route_mile, station.price_per_gallon, station.id
"""


def stations_along_route(
    geometry: Sequence[tuple[float, float]], distance_miles: float, corridor_miles: float
) -> list[Station]:
    """Stations within the corridor, annotated with ``route_mile`` and ``detour_miles``."""
    params = {
        "wkt": LineString(geometry, srid=4326).wkt,
        "srid": PLANNING_SRID,
        "distance_miles": distance_miles,
        "corridor_meters": corridor_miles * METERS_PER_MILE,
        "meters_per_mile": METERS_PER_MILE,
    }
    return list(Station.objects.raw(CORRIDOR_SQL, params))
