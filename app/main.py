from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import register_routers
from app.core.exceptions import register_exception_handlers


frontend_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


app = FastAPI(title="E-commerce Customer Support API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_exception_handlers(app)
register_routers(app)
