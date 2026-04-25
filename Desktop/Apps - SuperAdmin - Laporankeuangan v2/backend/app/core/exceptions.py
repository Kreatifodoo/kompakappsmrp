"""Custom exception classes mapped to HTTP responses."""

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse


class AppException(Exception):
    """Base for all domain exceptions."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str, *, code: str | None = None, details: dict | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.details = details or {}


class NotFoundError(AppException):
    status_code = 404
    code = "not_found"


class ConflictError(AppException):
    status_code = 409
    code = "conflict"


class ValidationError(AppException):
    status_code = 422
    code = "validation_error"


class AuthenticationError(AppException):
    status_code = 401
    code = "authentication_error"


class AuthorizationError(AppException):
    status_code = 403
    code = "authorization_error"


class TenantIsolationError(AuthorizationError):
    code = "tenant_isolation_error"


class RateLimitError(AppException):
    status_code = 429
    code = "rate_limit_exceeded"


def app_exception_handler(_: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": _http_code(exc.status_code),
                "message": exc.detail,
                "details": {},
            }
        },
    )


def _http_code(status_code: int) -> str:
    return {
        status.HTTP_400_BAD_REQUEST: "bad_request",
        status.HTTP_401_UNAUTHORIZED: "authentication_error",
        status.HTTP_403_FORBIDDEN: "authorization_error",
        status.HTTP_404_NOT_FOUND: "not_found",
        status.HTTP_409_CONFLICT: "conflict",
        status.HTTP_422_UNPROCESSABLE_ENTITY: "validation_error",
        status.HTTP_429_TOO_MANY_REQUESTS: "rate_limit_exceeded",
    }.get(status_code, "error")
