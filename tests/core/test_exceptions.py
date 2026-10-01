from rest_framework.exceptions import MethodNotAllowed, ValidationError
from rest_framework.test import APIRequestFactory

from core.exceptions import ApiError, NotFoundError, exception_handler


class PlanFailedError(ApiError):
    status_code = 422
    code = "no_feasible_plan"


def _context() -> dict:
    return {"request": APIRequestFactory().get("/api/v1/anything/")}


def test_api_error_maps_to_its_status_code_and_shape():
    response = exception_handler(
        PlanFailedError("No station within range.", details={"from_mile": 120.5}), _context()
    )

    assert response.status_code == 422
    assert response.data == {
        "error": {
            "code": "no_feasible_plan",
            "message": "No station within range.",
            "details": {"from_mile": 120.5},
        }
    }


def test_not_found_defaults_to_404_with_empty_details():
    response = exception_handler(NotFoundError("Trip not found."), _context())

    assert response.status_code == 404
    assert response.data["error"] == {
        "code": "not_found",
        "message": "Trip not found.",
        "details": {},
    }


def test_drf_validation_error_keeps_field_details():
    error = ValidationError({"origin": ["This field is required."]})

    response = exception_handler(error, _context())

    assert response.status_code == 400
    assert response.data["error"]["code"] == "validation_error"
    assert response.data["error"]["details"] == {"origin": ["This field is required."]}


def test_other_drf_exceptions_use_their_default_code():
    response = exception_handler(MethodNotAllowed("PUT"), _context())

    assert response.status_code == 405
    assert response.data["error"]["code"] == "method_not_allowed"
    assert response.data["error"]["message"] == 'Method "PUT" not allowed.'


def test_unexpected_exception_becomes_generic_500():
    response = exception_handler(RuntimeError("boom"), _context())

    assert response.status_code == 500
    assert response.data["error"]["code"] == "internal_error"
    assert "boom" not in response.data["error"]["message"]
