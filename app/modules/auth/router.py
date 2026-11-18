from fastapi import APIRouter, Depends, status

from app.modules.auth.dependencies import get_auth_service
from app.modules.auth.schemas import (
    EmailRequest,
    MessageResponse,
    OTPVerification,
    SignupRequest,
    TokenResponse,
)
from app.modules.auth.service import AuthService


router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post(
    "/signup/request-otp",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a signup verification code",
    description=(
        "Send a six-digit verification code to the supplied email. "
        "The first and last names are saved with the pending signup and used "
        "to create the account after OTP verification."
    ),
)
def request_signup_otp(
    payload: SignupRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    return auth_service.request_signup_otp(payload)


@router.post(
    "/signup/verify-otp",
    response_model=TokenResponse,
    summary="Verify signup code and create account",
    description="Verify the emailed code, create the user, and return a JWT access token.",
)
def verify_signup_otp(
    payload: OTPVerification,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    return TokenResponse(access_token=auth_service.verify_signup_otp(payload))


@router.post(
    "/login/request-otp",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a login verification code",
    description="Send a six-digit login code to a registered email address.",
)
def request_login_otp(
    payload: EmailRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    return auth_service.request_login_otp(payload.email)


@router.post(
    "/login/verify-otp",
    response_model=TokenResponse,
    summary="Verify login code",
    description="Verify the emailed code and return a JWT access token.",
)
def verify_login_otp(
    payload: OTPVerification,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    return TokenResponse(access_token=auth_service.verify_login_otp(payload))
