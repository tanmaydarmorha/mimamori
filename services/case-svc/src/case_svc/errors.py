from __future__ import annotations


class ApiProblem(Exception):
    """Raised anywhere; the app turns it into HTTP status + ApiError {error, detail}."""

    def __init__(self, status: int, error: str, detail: str | None = None) -> None:
        super().__init__(f"{status} {error}: {detail}")
        self.status, self.error, self.detail = status, error, detail


def not_found(what: str, ident: str) -> ApiProblem:
    return ApiProblem(404, "not_found", f"{what} {ident} not found")


def conflict(error: str, detail: str | None = None) -> ApiProblem:
    return ApiProblem(409, error, detail)
