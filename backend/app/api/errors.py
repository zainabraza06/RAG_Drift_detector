"""Domain exception -> HTTP response mapping.

Registered once on the application rather than caught in route handlers, so
handlers stay free of error plumbing and every failure leaves the API in the
same envelope:

    {"error": {"code": "run_not_found", "message": "...", "detail": {...}}}

Clients branch on ``code``, never on ``message`` -- wording is allowed to
change, codes are not.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.errors import (
    CollectionNotFoundError,
    ConfigurationError,
    DiagnosticsUnavailableError,
    DriftDetectorError,
    EvaluationError,
    GoldenSetError,
    VectorStoreError,
    VectorStoreUnavailableError,
)
from app.repositories.golden_sets import DuplicateGoldenSetError
from app.repositories.runs import UnknownMetricError
from app.services.corpus import CorpusError
from app.services.demo_scenarios import DemoDisabledError
from app.services.golden_set_service import (
    GoldenSetNotFoundError,
    NoActiveGoldenSetError,
)
from app.services.run_service import RunNotFoundError

logger = logging.getLogger(__name__)

#: Most specific first - the first matching entry wins.
_ERROR_MAP: tuple[tuple[type[DriftDetectorError], int, str], ...] = (
    (RunNotFoundError, status.HTTP_404_NOT_FOUND, "run_not_found"),
    (DemoDisabledError, status.HTTP_403_FORBIDDEN, "demo_disabled"),
    (
        DiagnosticsUnavailableError,
        status.HTTP_404_NOT_FOUND,
        "diagnostics_unavailable",
    ),
    (GoldenSetNotFoundError, status.HTTP_404_NOT_FOUND, "golden_set_not_found"),
    (DuplicateGoldenSetError, status.HTTP_409_CONFLICT, "golden_set_exists"),
    (NoActiveGoldenSetError, status.HTTP_409_CONFLICT, "no_active_golden_set"),
    (UnknownMetricError, status.HTTP_400_BAD_REQUEST, "unknown_metric"),
    (CorpusError, status.HTTP_400_BAD_REQUEST, "invalid_corpus"),
    (GoldenSetError, status.HTTP_400_BAD_REQUEST, "invalid_golden_set"),
    (
        CollectionNotFoundError,
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "collection_not_found",
    ),
    (
        VectorStoreUnavailableError,
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "vector_store_unavailable",
    ),
    (VectorStoreError, status.HTTP_503_SERVICE_UNAVAILABLE, "vector_store_error"),
    (EvaluationError, status.HTTP_500_INTERNAL_SERVER_ERROR, "evaluation_failed"),
    (
        ConfigurationError,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "configuration_error",
    ),
)


def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    detail: Any = None,
) -> JSONResponse:
    """Build the standard error envelope."""
    payload: dict[str, Any] = {"code": code, "message": message}
    if detail is not None:
        payload["detail"] = detail
    return JSONResponse(status_code=status_code, content={"error": payload})


def classify(exc: DriftDetectorError) -> tuple[int, str]:
    """Map a domain error onto ``(status_code, machine-readable code)``."""
    for error_type, status_code, code in _ERROR_MAP:
        if isinstance(exc, error_type):
            return status_code, code
    return status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error"


def register_exception_handlers(app: FastAPI) -> None:
    """Install the handlers on ``app``."""

    @app.exception_handler(DriftDetectorError)
    async def _domain_error(
        _request: Request, exc: DriftDetectorError
    ) -> JSONResponse:
        status_code, code = classify(exc)
        if status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
            logger.exception("unhandled domain error (%s)", code)
        else:
            logger.info("%s: %s", code, exc)
        return error_response(status_code=status_code, code=code, message=str(exc))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Field-level detail, so a form can highlight the offending input
        # rather than showing one opaque message.
        return error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="validation_error",
            message="The request payload failed validation.",
            detail=[
                {
                    "field": ".".join(str(part) for part in error.get("loc", ())[1:]),
                    "message": error.get("msg", "invalid value"),
                }
                for error in exc.errors()
            ],
        )
