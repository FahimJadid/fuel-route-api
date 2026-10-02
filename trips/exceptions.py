from rest_framework import status

from core.exceptions import ApiError


class NoFeasiblePlanError(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "no_feasible_plan"

    def __init__(self, from_mile: float) -> None:
        super().__init__(
            f"No fuel station within range after mile {from_mile:.1f}.",
            details={"from_mile": round(from_mile, 1)},
        )
        self.from_mile = from_mile
