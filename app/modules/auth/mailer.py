import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import Settings
from app.modules.auth.models import OTPPurpose


def send_otp_email(email: str, otp: str, purpose: OTPPurpose, settings: Settings) -> None:
    if not settings.mail_host or not settings.mail_from:
        raise RuntimeError("Email delivery is not configured.")

    message = EmailMessage()
    message["Subject"] = "Your verification code"
    message["From"] = settings.mail_from
    message["To"] = email
    action = "sign up" if purpose is OTPPurpose.SIGNUP else "log in"
    message.set_content(
        f"Your code to {action} is {otp}. It expires in "
        f"{settings.otp_ttl_minutes} minutes. If you did not request this, ignore this email."
    )

    with smtplib.SMTP(settings.mail_host, settings.mail_port, timeout=10) as smtp:
        if settings.mail_starttls:
            smtp.starttls(context=ssl.create_default_context())
        if settings.mail_username:
            if settings.mail_password is None:
                raise RuntimeError("MAIL_PASSWORD is required when MAIL_USERNAME is set.")
            smtp.login(settings.mail_username, settings.mail_password.get_secret_value())
        smtp.send_message(message)
