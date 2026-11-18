from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import Settings
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
