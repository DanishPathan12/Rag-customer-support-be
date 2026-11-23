from fastapi import FastAPI

from app.modules.auth.router import router as auth_router
from app.modules.ingestion.router import router as ingestion_router
from app.modules.users.router import router as users_router


def register_routers(app: FastAPI) -> None:
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(ingestion_router)
