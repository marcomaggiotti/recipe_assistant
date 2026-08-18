from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    service_name: str = "pizza-service"
    api_key: str = ""  # empty disables auth (dev mode)

    db_backend: Literal["postgres", "cosmos", "sqlite"] = "sqlite"

    # Postgres (works for local docker-compose Postgres AND Render managed Postgres -
    # Render's Postgres is wire-compatible, just point postgres_url at its connection string)
    postgres_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/pizza_db"

    # Azure Cosmos DB (NoSQL API)
    cosmos_endpoint: str = ""
    cosmos_key: str = ""
    cosmos_database: str = "ai-agent"
    cosmos_container: str = "pizza_recipes"

    # sqlite fallback for zero-config local dev
    sqlite_path: str = "./pizza_service.db"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    cors_allow_origins: str = "*"

    # Standalone flour-catalogue microservice (github.com/marcomaggiotti/flour_service)
    # - the /flour-explorer page's JS calls this directly from the browser, and
    # app/flours.py's HttpFlourCatalogStore calls it server-side too (for
    # /recipes/generate's flour validation) - there's no local flour catalogue copy in
    # this repo. Override flour_service_url for local dev (e.g. http://localhost:8001).
    # flour_service_api_key is only needed if that deployment has its own API_KEY set.
    flour_service_url: str = "https://flour-service.onrender.com"
    flour_service_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
