from fastapi import APIRouter, Depends

from app.common.dependencies import get_current_user
from app.modules.users.models import User
from app.modules.users.schemas import UserResponse
from app.modules.users.service import serialize_user


router = APIRouter(prefix="/auth", tags=["users"])


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get the authenticated user",
    description="Returns the profile for the user identified by the bearer access token.",
)
def read_current_user(user: User = Depends(get_current_user)) -> UserResponse:
    return serialize_user(user)
