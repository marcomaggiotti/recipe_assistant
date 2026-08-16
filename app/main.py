from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routers import agent, health, pizza
from .routers.pizza import get_flour_catalog_store, get_repo, get_style_store

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Build the repo/style/flour stores at boot rather than lazily on first request -
    # with DB_BACKEND=cosmos this is what creates/reseeds the pizza_recipes/
    # pizza_styles/pizza_flours containers, so a deploy (not incoming traffic timing)
    # is what determines when that happens.
    get_repo()
    get_style_store()
    get_flour_catalog_store()
    yield


app = FastAPI(
    title="Pizza Service AI Agent",
    description="Microservice AI agent that generates pizza dough recipes from a flour "
                 "blend, fermentation technique, and pizza-chef/cookbook style.",
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
app.include_router(pizza.router)
app.include_router(agent.router)
