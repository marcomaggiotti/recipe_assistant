from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .routers import agent, health, pages, pizza, pre_ferment_types
from .routers.pizza import get_flour_catalog_store, get_repo
from .routers.pre_ferment_types import get_pre_ferment_type_store

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Build the repo/flour/pre_ferment_type stores at boot rather than lazily on first
    # request - with DB_BACKEND=cosmos this is what creates/reseeds the pizza_recipes
    # container, so a deploy (not incoming traffic timing) is what determines when that
    # happens. get_flour_catalog_store() just wraps flour-service's HTTP API (see
    # app/flours.py) - constructing it does no I/O, so it's safe to build eagerly
    # regardless of whether flour-service is reachable. get_pre_ferment_type_store()
    # always uses Postgres (see app/pre_ferments.py - no local-storage fallback, since
    # Render's free tier has no persistent disk to fall back onto), independent of
    # DB_BACKEND, and is likewise safe to build eagerly - the actual connection happens
    # lazily on first use, not here, so it never blocks startup on a Postgres connection
    # attempt.
    get_repo()
    get_flour_catalog_store()
    get_pre_ferment_type_store()
    yield


app = FastAPI(
    title="Pizza Service AI Agent",
    description="Microservice AI agent that generates pizza dough recipes from a flour "
                 "blend and an optional pre-ferment (poolish, biga, sourdough, or a "
                 "custom combination).",
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

app.mount("/static", StaticFiles(directory=Path(__file__).resolve().parent / "static"), name="static")

app.include_router(health.router)
app.include_router(pizza.router)
app.include_router(pre_ferment_types.router)
app.include_router(agent.router)
app.include_router(pages.router)
