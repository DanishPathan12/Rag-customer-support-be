import uuid

from app.core.config import Settings
from app.core.security import create_access_token, hash_otp, verify_otp


def test_otp_hash_is_bound_to_email_and_purpose() -> None:
    pepper = "p" * 32
    code_hash = hash_otp("012345", "person@example.com", "signup", pepper)

    assert verify_otp("012345", "person@example.com", "signup", pepper, code_hash)
    assert not verify_otp("012345", "other@example.com", "signup", pepper, code_hash)
    assert not verify_otp("012345", "person@example.com", "login", pepper, code_hash)
    assert not verify_otp("999999", "person@example.com", "signup", pepper, code_hash)


def test_access_token_has_expected_subject_and_issuer() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost/db",
        jwt_secret="j" * 32,
        otp_pepper="p" * 32,
    )
    user_id = uuid.uuid4()

    import jwt

    token = create_access_token(user_id, settings)
    payload = jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
        issuer=settings.jwt_issuer,
    )

    assert payload["sub"] == str(user_id)
