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
    cosmos_styles_container: str = "pizza_styles"
    cosmos_flours_container: str = "pizza_flours"

    # sqlite fallback for zero-config local dev
    sqlite_path: str = "./pizza_service.db"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    cors_allow_origins: str = "*"

    # Standalone flour-catalogue microservice (github.com/marcomaggiotti/flour_service)
    # - the /flour-explorer page's JS calls this directly from the browser, no backend
    # proxying involved. Override for local dev (e.g. http://localhost:8001).
    flour_service_url: str = "https://flour-service.onrender.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()
