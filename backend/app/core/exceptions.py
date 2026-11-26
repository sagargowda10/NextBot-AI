"""Domain exception hierarchy.

Services and plugins raise these; the API layer maps them to HTTP responses in
`register_exception_handlers`. Nothing here imports FastAPI at module level, so the
agent/plugin layer can raise them without depending on the web framework.
"""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    status_code = 400
    code = "domain_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(DomainError):
    status_code = 404
    code = "not_found"


class ConflictError(DomainError):
    status_code = 409
    code = "conflict"


class ValidationFailed(DomainError):
    status_code = 422
    code = "validation_failed"


class AuthenticationError(DomainError):
    status_code = 401
    code = "unauthenticated"


class PermissionDenied(DomainError):
    status_code = 403
    code = "forbidden"


class OutOfStockError(ConflictError):
    code = "out_of_stock"


class PaymentError(DomainError):
    status_code = 402
    code = "payment_failed"


class RateLimited(DomainError):
    status_code = 429
    code = "rate_limited"


class ExternalServiceNotConfigured(DomainError):
    """Raised by adapters for real providers when credentials are missing."""

    status_code = 503
    code = "provider_not_configured"


class PluginError(DomainError):
    status_code = 503
    code = "plugin_error"


def register_exception_handlers(app: Any) -> None:  # pragma: no cover - exercised via API tests
    from fastapi import Request
    from fastapi.responses import JSONResponse

    from app.core.logging import get_logger

    log = get_logger("errors")

    @app.exception_handler(DomainError)
    async def _domain(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", extra={"path": request.url.path})
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "Something went wrong."}},
        )
