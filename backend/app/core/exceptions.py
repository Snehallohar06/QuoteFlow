"""Domain exceptions and the FastAPI handlers that translate them to HTTP."""

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class QuoteFlowError(Exception):
    """Base class for every expected (non-bug) backend failure."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    error_code: str = "quoteflow_error"

    def __init__(self, message: str, *, details: object | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(QuoteFlowError):
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "not_found"


class ValidationError(QuoteFlowError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "validation_error"


class BusinessRuleError(QuoteFlowError):
    """A request was well-formed but violates a configured business rule."""

    status_code = status.HTTP_409_CONFLICT
    error_code = "business_rule_violation"


class WorkflowError(QuoteFlowError):
    """An illegal state transition was attempted on a workflow entity."""

    status_code = status.HTTP_409_CONFLICT
    error_code = "workflow_error"


class AuthenticationError(QuoteFlowError):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "authentication_failed"


class PermissionDeniedError(QuoteFlowError):
    status_code = status.HTTP_403_FORBIDDEN
    error_code = "permission_denied"


class ConflictError(QuoteFlowError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "conflict"


def _error_body(error_code: str, message: str, details: object | None = None) -> dict:
    body: dict = {"error": {"code": error_code, "message": message}}
    if details is not None:
        body["error"]["details"] = jsonable_encoder(details)
    return body


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(QuoteFlowError)
    async def _handle_domain_error(_: Request, exc: QuoteFlowError) -> JSONResponse:
        headers = (
            {"WWW-Authenticate": "Bearer"}
            if isinstance(exc, AuthenticationError)
            else None
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.error_code, exc.message, exc.details),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_request_validation(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_body(
                "request_validation_error",
                "The request payload failed schema validation.",
                jsonable_encoder(exc.errors()),
            ),
        )
