from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routers import health, toppings
from .routers.toppings import get_repo

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Build the repo at boot rather than lazily on first request - with
    # TOPPING_DB_BACKEND=cosmos this is what creates/reseeds the toppings container, so
    # a deploy (not incoming traffic timing) is what determines when that happens.
    get_repo()
    yield


app = FastAPI(
    title="Topping Service",
    description="Microservice for the pizza topping catalog - create/list/get/delete "
                "named toppings (meat, vegetable, cheese, sauce, ...).",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_allow_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(toppings.router)
