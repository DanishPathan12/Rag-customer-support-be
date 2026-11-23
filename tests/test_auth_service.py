import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import AdminAccessDeniedError, InvalidOTPError
from app.db.base import Base
from app.modules.auth.models import EmailOTP
from app.modules.auth.schemas import OTPVerification, SignupRequest
from app.modules.auth.service import AuthService
from app.modules.users.models import User
import app.modules.auth.service as auth_service_module


def test_signup_persists_names_after_otp_verification(monkeypatch) -> None:
    settings = Settings(
        database_url="sqlite://",
        jwt_secret="j" * 32,
        otp_pepper="p" * 32,
    )
    monkeypatch.setattr(auth_service_module, "get_settings", lambda: settings)
    sent_codes: list[str] = []
    monkeypatch.setattr(
        auth_service_module,
        "send_otp_email",
        lambda email, otp, purpose, config: sent_codes.append(otp),
    )

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        auth_service = AuthService(db)
        auth_service.request_signup_otp(
            SignupRequest(
                email="person@example.com",
                first_name="  Jane ",
                last_name=" Doe  ",
            )
        )
        otp_record = db.scalar(select(EmailOTP).where(EmailOTP.email == "person@example.com"))
        assert otp_record is not None
        token = auth_service.verify_signup_otp(
            OTPVerification(email="person@example.com", otp=sent_codes[0])
        )
        user = db.scalar(select(User).where(User.email == "person@example.com"))

    assert token
    assert user is not None
    assert user.first_name == "Jane"
    assert user.last_name == "Doe"


def test_admin_login_requires_an_admin_account_and_a_dedicated_otp(monkeypatch) -> None:
    settings = Settings(
        database_url="sqlite://",
        jwt_secret="j" * 32,
        otp_pepper="p" * 32,
    )
    monkeypatch.setattr(auth_service_module, "get_settings", lambda: settings)
    sent_codes: list[str] = []
    monkeypatch.setattr(
        auth_service_module,
        "send_otp_email",
        lambda email, otp, purpose, config: sent_codes.append(otp),
    )

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        admin = User(email="admin@example.com", is_admin=True)
        regular_user = User(email="customer@example.com")
        db.add_all([admin, regular_user])
        db.commit()
        auth_service = AuthService(db)

        auth_service.request_admin_login_otp("admin@example.com")
        assert len(sent_codes) == 1
        admin_otp = db.scalar(select(EmailOTP).where(EmailOTP.email == admin.email))
        assert admin_otp is not None
        assert admin_otp.purpose.value == "admin_login"
        assert auth_service.verify_admin_login_otp(
            OTPVerification(email=admin.email, otp=sent_codes[0])
        )

        auth_service.request_admin_login_otp(regular_user.email)
        assert len(sent_codes) == 1
        with pytest.raises(AdminAccessDeniedError):
            auth_service.verify_admin_login_otp(
                OTPVerification(email=regular_user.email, otp="123456")
            )

        auth_service.request_login_otp(admin.email)
        with pytest.raises(InvalidOTPError):
            auth_service.verify_admin_login_otp(
                OTPVerification(email=admin.email, otp=sent_codes[-1])
            )
