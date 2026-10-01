from rest_framework import status

from core.exceptions import ApiError


class PlaceNotFoundError(ApiError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "place_not_found"


class OutsideUsaError(ApiError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "outside_usa"
