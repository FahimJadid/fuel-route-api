from typing import Protocol

from routing.types import Coordinate, Route


class RoutingProvider(Protocol):
    name: str

    def route(self, origin: Coordinate, destination: Coordinate) -> Route: ...
