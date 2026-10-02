from django.core.cache import cache
from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    @extend_schema(
        summary="Service health",
        responses={200: dict, 503: dict},
    )
    def get(self, request: Request) -> Response:
        checks = {"database": _check_database(), "cache": _check_cache()}
        healthy = all(result == "ok" for result in checks.values())
        return Response(
            {"status": "ok" if healthy else "degraded", "checks": checks},
            status=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class UnknownEndpointView(APIView):
    """Catches every unmatched path under the API prefix so 404s share the JSON error shape."""

    def initial(self, request: Request, *args, **kwargs) -> None:
        super().initial(request, *args, **kwargs)
        raise NotFound(f"No endpoint at {request.path}.")


def _check_database() -> str:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return "ok"
    except Exception as exc:
        return f"error: {exc.__class__.__name__}"


def _check_cache() -> str:
    try:
        cache.set("health", "ok", timeout=5)
        return "ok" if cache.get("health") == "ok" else "error: readback mismatch"
    except Exception as exc:
        return f"error: {exc.__class__.__name__}"
