from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class InvalidOTPError(Exception):
    pass


class EmailDeliveryError(Exception):
    pass


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


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(InvalidOTPError, invalid_otp_exception_handler)
    app.add_exception_handler(EmailDeliveryError, email_delivery_exception_handler)
