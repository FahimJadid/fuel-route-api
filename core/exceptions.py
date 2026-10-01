import logging
from typing import Any

from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """Base for errors that map directly to an HTTP response with a stable error code."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "internal_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(ApiError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ServiceUnavailableError(ApiError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "service_unavailable"


def error_payload(code: str, message: str, details: dict[str, Any] | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def exception_handler(exc: Exception, context: dict) -> Response | None:
    if isinstance(exc, ApiError):
        return Response(error_payload(exc.code, exc.message, exc.details), status=exc.status_code)

    response = drf_exception_handler(exc, context)
    if response is not None:
        return _reshape_drf_response(exc, response)

    logger.exception("Unhandled exception", extra={"path": context["request"].path})
    return Response(
        error_payload(ApiError.code, "An unexpected error occurred."),
        status=ApiError.status_code,
    )


def _reshape_drf_response(exc: Exception, response: Response) -> Response:
    if isinstance(exc, ValidationError):
        response.data = error_payload("validation_error", "Invalid request.", exc.detail)
        return response

    code = getattr(exc, "default_code", "error") if isinstance(exc, APIException) else "error"
    message = response.data.get("detail", "") if isinstance(response.data, dict) else ""
    response.data = error_payload(str(code), str(message))
    return response
