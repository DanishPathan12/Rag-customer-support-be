from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class InvalidOTPError(Exception):
    pass


class EmailDeliveryError(Exception):
    pass


class AdminAccessDeniedError(Exception):
    pass


class IngestionStorageError(Exception):
    pass


class AIIngestionConfigurationError(Exception):
    def __init__(self, detail: str = "Document ingestion is not configured.") -> None:
        self.detail = detail
        super().__init__(detail)


class AIIngestionError(Exception):
    pass


class AIIngestionRateLimitError(Exception):
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__("The Gemini API rate limit was exceeded.")


class AIResponseError(Exception):
    pass


class AIResponseUnavailableError(Exception):
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__("Gemini answer generation is temporarily unavailable.")


async def invalid_otp_exception_handler(_: Request, __: InvalidOTPError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"detail": "The verification code is invalid or expired."},
    )


async def email_delivery_exception_handler(_: Request, __: EmailDeliveryError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "Unable to send a verification code right now."},
    )


async def admin_access_denied_exception_handler(
    _: Request, __: AdminAccessDeniedError
) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={"detail": "Administrator access is required."},
    )


async def ingestion_storage_exception_handler(
    _: Request, __: IngestionStorageError
) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "Unable to save the ingestion file right now."},
    )


async def ai_ingestion_configuration_exception_handler(
    _: Request, exc: AIIngestionConfigurationError
) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": exc.detail},
    )


async def ai_ingestion_exception_handler(_: Request, __: AIIngestionError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={"detail": "The document was saved, but embedding ingestion failed."},
    )


async def ai_ingestion_rate_limit_exception_handler(
    _: Request, exc: AIIngestionRateLimitError
) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Gemini's quota is temporarily exhausted. Retry shortly."
        },
        headers={"Retry-After": str(exc.retry_after_seconds)},
    )


async def ai_response_exception_handler(_: Request, __: AIResponseError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={"detail": "Unable to generate an answer from the knowledge base."},
    )


async def ai_response_unavailable_exception_handler(
    _: Request, exc: AIResponseUnavailableError
) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "detail": "The answer service is experiencing high demand. Retry shortly."
        },
        headers={"Retry-After": str(exc.retry_after_seconds)},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(InvalidOTPError, invalid_otp_exception_handler)
    app.add_exception_handler(EmailDeliveryError, email_delivery_exception_handler)
    app.add_exception_handler(AdminAccessDeniedError, admin_access_denied_exception_handler)
    app.add_exception_handler(IngestionStorageError, ingestion_storage_exception_handler)
    app.add_exception_handler(
        AIIngestionConfigurationError,
        ai_ingestion_configuration_exception_handler,
    )
    app.add_exception_handler(AIIngestionError, ai_ingestion_exception_handler)
    app.add_exception_handler(
        AIIngestionRateLimitError,
        ai_ingestion_rate_limit_exception_handler,
    )
    app.add_exception_handler(AIResponseError, ai_response_exception_handler)
    app.add_exception_handler(
        AIResponseUnavailableError,
        ai_response_unavailable_exception_handler,
    )
