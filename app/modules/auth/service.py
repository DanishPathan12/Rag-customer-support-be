import logging
import smtplib
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.utils import as_utc
from app.core.config import get_settings
from app.core.exceptions import AdminAccessDeniedError, EmailDeliveryError, InvalidOTPError
from app.core.security import create_access_token, generate_otp, hash_otp, verify_otp
from app.modules.auth.mailer import send_otp_email
from app.modules.auth.models import EmailOTP, OTPPurpose
from app.modules.auth.schemas import MessageResponse, OTPVerification, SignupRequest
from app.modules.users.repository import create_user, get_user_by_email


logger = logging.getLogger(__name__)
GENERIC_OTP_MESSAGE = "If the address can receive a code, one has been sent."


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def request_signup_otp(self, request: SignupRequest) -> MessageResponse:
        if get_user_by_email(self.db, request.email) is None:
            self._issue_otp(
                request.email,
                OTPPurpose.SIGNUP,
                first_name=request.first_name,
                last_name=request.last_name,
            )
        return MessageResponse(message=GENERIC_OTP_MESSAGE)

    def verify_signup_otp(self, request: OTPVerification) -> str:
        otp_record = self._consume_otp(request, OTPPurpose.SIGNUP)
        if otp_record.first_name is None or otp_record.last_name is None:
            raise InvalidOTPError
        try:
            user = create_user(
                self.db,
                request.email,
                otp_record.first_name,
                otp_record.last_name,
            )
        except IntegrityError as exc:
            raise InvalidOTPError from exc
        return create_access_token(user.id, get_settings())

    def request_login_otp(self, email: str) -> MessageResponse:
        if get_user_by_email(self.db, email) is not None:
            self._issue_otp(email, OTPPurpose.LOGIN)
        return MessageResponse(message=GENERIC_OTP_MESSAGE)

    def verify_login_otp(self, request: OTPVerification) -> str:
        user = get_user_by_email(self.db, request.email)
        if user is None:
            raise InvalidOTPError
        self._consume_otp(request, OTPPurpose.LOGIN)
        return create_access_token(user.id, get_settings())

    def request_admin_login_otp(self, email: str) -> MessageResponse:
        user = get_user_by_email(self.db, email)
        if user is not None and user.is_admin:
            self._issue_otp(email, OTPPurpose.ADMIN_LOGIN)
        return MessageResponse(message=GENERIC_OTP_MESSAGE)

    def verify_admin_login_otp(self, request: OTPVerification) -> str:
        user = get_user_by_email(self.db, request.email)
        if user is None or not user.is_admin:
            raise AdminAccessDeniedError
        self._consume_otp(request, OTPPurpose.ADMIN_LOGIN)
        return create_access_token(user.id, get_settings())

    def _issue_otp(
        self,
        email: str,
        purpose: OTPPurpose,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> None:
        settings = get_settings()
        now = datetime.now(timezone.utc)
        recent_otp = self.db.scalar(
            select(EmailOTP)
            .where(EmailOTP.email == email, EmailOTP.purpose == purpose)
            .order_by(EmailOTP.created_at.desc())
            .limit(1)
        )
        if recent_otp and (now - as_utc(recent_otp.created_at)) < timedelta(
            seconds=settings.otp_resend_cooldown_seconds
        ):
            return

        self.db.query(EmailOTP).filter(
            EmailOTP.email == email,
            EmailOTP.purpose == purpose,
            EmailOTP.used_at.is_(None),
        ).update({EmailOTP.used_at: now}, synchronize_session=False)

        otp = generate_otp()
        record = EmailOTP(
            email=email,
            purpose=purpose,
            first_name=first_name,
            last_name=last_name,
            code_hash=hash_otp(
                otp,
                email,
                purpose.value,
                settings.otp_pepper.get_secret_value(),
            ),
            expires_at=now + timedelta(minutes=settings.otp_ttl_minutes),
        )
        self.db.add(record)
        self.db.commit()
        try:
            send_otp_email(email, otp, purpose, settings)
        except (OSError, RuntimeError, smtplib.SMTPException) as exc:
            record.used_at = datetime.now(timezone.utc)
            self.db.commit()
            logger.exception("Could not send an authentication code.")
            raise EmailDeliveryError from exc

    def _consume_otp(self, request: OTPVerification, purpose: OTPPurpose) -> EmailOTP:
        settings = get_settings()
        record = self.db.scalar(
            select(EmailOTP)
            .where(
                EmailOTP.email == request.email,
                EmailOTP.purpose == purpose,
                EmailOTP.used_at.is_(None),
            )
            .order_by(EmailOTP.created_at.desc())
            .limit(1)
            .with_for_update()
        )
        now = datetime.now(timezone.utc)
        if (
            record is None
            or as_utc(record.expires_at) <= now
            or record.attempts >= settings.otp_max_attempts
        ):
            raise InvalidOTPError

        valid = verify_otp(
            request.otp,
            request.email,
            purpose.value,
            settings.otp_pepper.get_secret_value(),
            record.code_hash,
        )
        if not valid:
            record.attempts += 1
            if record.attempts >= settings.otp_max_attempts:
                record.used_at = now
            self.db.commit()
            raise InvalidOTPError

        record.used_at = now
        self.db.commit()
        return record
