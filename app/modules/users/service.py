from app.modules.users.models import User
from app.modules.users.schemas import UserResponse


def serialize_user(user: User) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
    )
