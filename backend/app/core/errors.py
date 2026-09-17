"""Typed application errors.

Every error carries a stable machine code plus an operator-facing message.
The rule for this platform: *never lose the original document*. Processing
errors degrade a stage, they do not delete or invalidate an upload.
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.logging import get_logger

logger = get_logger(__name__)


class AppError(Exception):
    code = "internal_error"
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    message = "An unexpected error occurred."
    retryable = False

    def __init__(self, message: str | None = None, *, details: Any = None, retryable: bool | None = None):
        self.message = message or self.message
        self.details = details
        if retryable is not None:
            self.retryable = retryable
        super().__init__(self.message)

    def payload(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
                "retryable": self.retryable,
            }
        }


class NotFoundError(AppError):
    code = "not_found"
    status_code = status.HTTP_404_NOT_FOUND
    message = "The requested resource does not exist."


class ValidationFailure(AppError):
    code = "validation_failed"
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    message = "The submitted data is not valid."


class AuthenticationError(AppError):
    code = "not_authenticated"
    status_code = status.HTTP_401_UNAUTHORIZED
    message = "Authentication is required."


class PermissionDenied(AppError):
    code = "permission_denied"
    status_code = status.HTTP_403_FORBIDDEN
    message = "Your role does not permit this operation."


class RateLimited(AppError):
    code = "rate_limited"
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    message = "Too many requests. Please slow down."
    retryable = True


class UnsupportedDocument(AppError):
    code = "unsupported_document"
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    message = "This file type is not supported for document analysis."


class FileTooLarge(AppError):
    code = "file_too_large"
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    message = "The uploaded file exceeds the configured size limit."


class CorruptDocument(AppError):
    code = "corrupt_document"
    status_code = status.HTTP_400_BAD_REQUEST
    message = "The file could not be parsed. It may be corrupt or truncated."


class SecurityRejection(AppError):
    code = "security_rejected"
    status_code = status.HTTP_400_BAD_REQUEST
    message = "The file was rejected by the pre-ingest security check."


class ProviderUnavailable(AppError):
    """Raised by OCR / AIGC / verification adapters when a dependency is down.

    The pipeline catches this per stage: the document is preserved, the stage is
    marked ``unavailable`` and can be reprocessed later.
    """

    code = "provider_unavailable"
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    message = "An analysis provider is temporarily unavailable."
    retryable = True

    def __init__(self, provider: str, message: str | None = None, **kw):
        self.provider = provider
        super().__init__(message or f"Provider '{provider}' is temporarily unavailable.", **kw)


class ProcessingTimeout(AppError):
    code = "processing_timeout"
    status_code = status.HTTP_504_GATEWAY_TIMEOUT
    message = "Processing exceeded the configured time budget."
    retryable = True


class ConflictError(AppError):
    code = "conflict"
    status_code = status.HTTP_409_CONFLICT
    message = "The request conflicts with the current state of the resource."


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):  # pragma: no cover - thin
        if exc.status_code >= 500:
            logger.error("app_error", extra={"code": exc.code, "path": request.url.path})
        return JSONResponse(status_code=exc.status_code, content=exc.payload())

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "validation_failed",
                    "message": "Request validation failed.",
                    "details": [
                        {"loc": list(e.get("loc", [])), "msg": e.get("msg")} for e in exc.errors()
                    ],
                    "retryable": False,
                }
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def _db(request: Request, exc: SQLAlchemyError):
        logger.error("database_error", extra={"path": request.url.path, "kind": type(exc).__name__})
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": {
                    "code": "database_unavailable",
                    "message": "The database is currently unavailable. No data was modified.",
                    "details": None,
                    "retryable": True,
                }
            },
        )
