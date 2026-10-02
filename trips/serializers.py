from decimal import Decimal

from django.conf import settings
from django.urls import reverse
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from geo.services.resolver import ResolvedLocation, resolve_coordinates, resolve_text
from trips.models import Trip
from trips.planner import fuel_cost
from trips.services import TripRequest

LOCATION_SCHEMA = {
    "oneOf": [
        {"type": "string", "example": "Dallas, TX"},
        {
            "type": "object",
            "properties": {"lat": {"type": "number"}, "lng": {"type": "number"}},
            "required": ["lat", "lng"],
        },
    ]
}


@extend_schema_field(LOCATION_SCHEMA)
class LocationField(serializers.Field):
    default_error_messages = {
        "invalid": "Provide either 'City, ST' or an object with lat and lng.",
    }

    def to_internal_value(self, data) -> ResolvedLocation:
        if isinstance(data, str) and data.strip():
            return resolve_text(data)
        if isinstance(data, dict) and {"lat", "lng"} <= data.keys():
            try:
                return resolve_coordinates(float(data["lat"]), float(data["lng"]))
            except (TypeError, ValueError):
                self.fail("invalid")
        self.fail("invalid")

    def to_representation(self, value: ResolvedLocation) -> dict:
        return {"label": value.label, "lat": value.lat, "lng": value.lng}


class TripRequestSerializer(serializers.Serializer):
    origin = LocationField()
    destination = LocationField()
    max_range_miles = serializers.FloatField(
        min_value=50,
        max_value=2000,
        default=lambda: settings.FUEL_PLANNING["MAX_RANGE_MILES"],
    )
    mpg = serializers.FloatField(
        min_value=1, max_value=50, default=lambda: settings.FUEL_PLANNING["MPG"]
    )
    initial_fuel_gallons = serializers.FloatField(
        min_value=0,
        required=False,
        default=0,
        help_text="Fuel already in the tank at the origin; it is not billed. "
        "At most the tank capacity (max_range_miles / mpg).",
    )

    def validate(self, attrs: dict) -> dict:
        capacity = attrs["max_range_miles"] / attrs["mpg"]
        if attrs["initial_fuel_gallons"] > capacity:
            message = f"Cannot exceed the tank capacity of {capacity:.2f} gallons."
            raise serializers.ValidationError({"initial_fuel_gallons": message})
        return attrs

    def to_trip_request(self) -> TripRequest:
        return TripRequest(**self.validated_data)


class LocationSerializer(serializers.Serializer):
    label = serializers.CharField()
    lat = serializers.FloatField()
    lng = serializers.FloatField()


class VehicleSerializer(serializers.Serializer):
    max_range_miles = serializers.DecimalField(max_digits=6, decimal_places=1)
    mpg = serializers.DecimalField(max_digits=5, decimal_places=2)
    tank_gallons = serializers.DecimalField(max_digits=7, decimal_places=2)


class StopStationSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    opis_id = serializers.IntegerField()
    name = serializers.CharField()
    address = serializers.CharField()
    city = serializers.CharField()
    state = serializers.CharField()
    lat = serializers.FloatField()
    lng = serializers.FloatField()


class StopSerializer(serializers.Serializer):
    sequence = serializers.IntegerField()
    station = StopStationSerializer()
    route_mile = serializers.FloatField()
    detour_miles = serializers.FloatField(required=False)
    price_per_gallon = serializers.DecimalField(max_digits=6, decimal_places=3)
    gallons = serializers.FloatField()
    cost = serializers.DecimalField(max_digits=10, decimal_places=2)
    fuel_on_arrival_gallons = serializers.FloatField()
    fuel_on_departure_gallons = serializers.FloatField()
    action = serializers.ChoiceField(choices=["fill_up", "partial", "final_leg"], required=False)
    reason = serializers.CharField(required=False)


class TotalsSerializer(serializers.Serializer):
    gallons = serializers.DecimalField(max_digits=8, decimal_places=3)
    cost = serializers.DecimalField(max_digits=10, decimal_places=2)
    stops = serializers.IntegerField()


class StartingFuelSerializer(serializers.Serializer):
    free_gallons = serializers.DecimalField(max_digits=8, decimal_places=3)
    reserve_gallons = serializers.DecimalField(max_digits=8, decimal_places=3)
    reserve_billed_at_stop = serializers.IntegerField(allow_null=True)
    reserve_cost = serializers.DecimalField(max_digits=10, decimal_places=2)
    trip_gallons = serializers.DecimalField(max_digits=8, decimal_places=3)


class SavingsSerializer(serializers.Serializer):
    baseline = serializers.CharField()
    baseline_cost = serializers.DecimalField(max_digits=10, decimal_places=2)
    baseline_stops = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    percent = serializers.DecimalField(max_digits=5, decimal_places=1)


class AssumptionsSerializer(serializers.Serializer):
    max_range_miles = serializers.DecimalField(max_digits=6, decimal_places=1)
    mpg = serializers.DecimalField(max_digits=5, decimal_places=2)
    tank_gallons = serializers.DecimalField(max_digits=7, decimal_places=2)
    initial_fuel_gallons = serializers.DecimalField(max_digits=8, decimal_places=3)
    corridor_miles = serializers.DecimalField(max_digits=4, decimal_places=1)
    minimum_purchase_gallons = serializers.IntegerField()
    reserve_rule = serializers.CharField()
    detour_cost_modelled = serializers.BooleanField()
    routing_profile = serializers.CharField()


class LinksSerializer(serializers.Serializer):
    self = serializers.CharField()
    map = serializers.CharField()


class TripSerializer(serializers.ModelSerializer):
    origin = serializers.SerializerMethodField()
    destination = serializers.SerializerMethodField()
    vehicle = serializers.SerializerMethodField()
    route = serializers.SerializerMethodField()
    stops = StopSerializer(many=True)
    totals = serializers.SerializerMethodField()
    starting_fuel = serializers.SerializerMethodField()
    savings = serializers.SerializerMethodField()
    assumptions = serializers.SerializerMethodField()
    links = serializers.SerializerMethodField()

    class Meta:
        model = Trip
        fields = [
            "id",
            "origin",
            "destination",
            "distance_miles",
            "duration_minutes",
            "vehicle",
            "route",
            "stops",
            "totals",
            "starting_fuel",
            "savings",
            "assumptions",
            "links",
            "created_at",
        ]

    @extend_schema_field(LocationSerializer)
    def get_origin(self, trip: Trip) -> dict:
        return {"label": trip.origin_label, "lat": trip.origin.y, "lng": trip.origin.x}

    @extend_schema_field(LocationSerializer)
    def get_destination(self, trip: Trip) -> dict:
        return {
            "label": trip.destination_label,
            "lat": trip.destination.y,
            "lng": trip.destination.x,
        }

    @extend_schema_field(VehicleSerializer)
    def get_vehicle(self, trip: Trip) -> dict:
        return VehicleSerializer(
            {
                "max_range_miles": trip.max_range_miles,
                "mpg": trip.mpg,
                "tank_gallons": trip.max_range_miles / trip.mpg,
            }
        ).data

    @extend_schema_field(
        {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["LineString"]},
                "coordinates": {"type": "array", "items": {"type": "array"}},
            },
        }
    )
    def get_route(self, trip: Trip) -> dict:
        return {"type": "LineString", "coordinates": [list(point) for point in trip.route.coords]}

    @extend_schema_field(TotalsSerializer)
    def get_totals(self, trip: Trip) -> dict:
        return TotalsSerializer(
            {"gallons": trip.total_gallons, "cost": trip.total_cost, "stops": len(trip.stops)}
        ).data

    @extend_schema_field(StartingFuelSerializer)
    def get_starting_fuel(self, trip: Trip) -> dict:
        free = trip.initial_fuel_gallons
        reserve = Decimal(0)
        reserve_cost = Decimal(0)
        if trip.stops:
            first = trip.stops[0]
            reserve = max(Decimal(str(first["route_mile"])) / trip.mpg - free, Decimal(0))
            reserve_cost = fuel_cost(float(reserve), Decimal(first["price_per_gallon"]))
        return StartingFuelSerializer(
            {
                "free_gallons": free,
                "reserve_gallons": reserve,
                "reserve_billed_at_stop": 1 if reserve > 0 else None,
                "reserve_cost": reserve_cost,
                "trip_gallons": trip.distance_miles / trip.mpg,
            }
        ).data

    @extend_schema_field(SavingsSerializer(allow_null=True))
    def get_savings(self, trip: Trip) -> dict | None:
        if trip.baseline_cost is None:
            return None
        amount = trip.baseline_cost - trip.total_cost
        percent = amount / trip.baseline_cost * 100 if trip.baseline_cost else Decimal(0)
        return SavingsSerializer(
            {
                "baseline": "fill the tank at the farthest reachable station",
                "baseline_cost": trip.baseline_cost,
                "baseline_stops": trip.baseline_stops,
                "amount": amount,
                "percent": percent,
            }
        ).data

    @extend_schema_field(AssumptionsSerializer)
    def get_assumptions(self, trip: Trip) -> dict:
        return AssumptionsSerializer(
            {
                "max_range_miles": trip.max_range_miles,
                "mpg": trip.mpg,
                "tank_gallons": trip.max_range_miles / trip.mpg,
                "initial_fuel_gallons": trip.initial_fuel_gallons,
                "corridor_miles": trip.corridor_miles,
                "minimum_purchase_gallons": 0,
                "reserve_rule": "fuel needed to reach the first stop is billed at that stop",
                "detour_cost_modelled": False,
                "routing_profile": "car",
            }
        ).data

    @extend_schema_field(LinksSerializer)
    def get_links(self, trip: Trip) -> dict:
        return {"self": self._link("trip-detail", trip), "map": self._link("trip-map", trip)}

    def _link(self, url_name: str, trip: Trip) -> str:
        path = reverse(url_name, kwargs={"pk": trip.pk})
        request = self.context.get("request")
        return request.build_absolute_uri(path) if request else path
