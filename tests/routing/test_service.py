from routing import service
from routing.types import Coordinate, Route

ORIGIN = Coordinate(lat=32.0, lng=-96.0)
DESTINATION = Coordinate(lat=33.0, lng=-96.0)


class StubProvider:
    name = "stub"

    def __init__(self, geometry):
        self.geometry = geometry
        self.calls = []

    def route(self, origin, destination):
        self.calls.append((origin, destination))
        return Route(
            provider=self.name, distance_miles=69.0, duration_minutes=70, geometry=self.geometry
        )


def test_get_route_drops_vertices_within_the_simplification_tolerance(monkeypatch):
    nearly_straight = ((-96.0, 32.0), (-96.0002, 32.5), (-96.0, 33.0))
    provider = StubProvider(nearly_straight)
    monkeypatch.setattr(service, "get_routing_provider", lambda: provider)

    route = service.get_route(ORIGIN, DESTINATION)

    assert provider.calls == [(ORIGIN, DESTINATION)]
    assert route.geometry == ((-96.0, 32.0), (-96.0, 33.0))
    assert route.distance_miles == 69.0


def test_get_route_keeps_real_bends(monkeypatch):
    bent = ((-96.0, 32.0), (-96.5, 32.5), (-96.0, 33.0))
    monkeypatch.setattr(service, "get_routing_provider", lambda: StubProvider(bent))

    route = service.get_route(ORIGIN, DESTINATION)

    assert route.geometry == bent
