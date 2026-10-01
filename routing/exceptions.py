from rest_framework import status

from core.exceptions import ApiError


class NoRouteError(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "no_route"


class RoutingUnavailableError(ApiError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "routing_unavailable"
