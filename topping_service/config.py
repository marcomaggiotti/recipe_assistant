"""Settings for topping-service - a separate microservice from the pizza recipe app
(app/), but packaged in the same repo/image and selected at container startup via the
SERVICE env var (see docker-entrypoint.sh). All env vars are prefixed TOPPING_ so the
two services can read the same .env file / process environment without colliding on
shared names like DB_BACKEND or POSTGRES_URL.
"""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", env_prefix="TOPPING_", extra="ignore",
    )

    service_name: str = "topping-service"
    api_key: str = ""  # empty disables auth (dev mode)

    db_backend: Literal["postgres", "cosmos", "sqlite"] = "sqlite"

    postgres_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/topping_db"

    cosmos_endpoint: str = ""
    cosmos_key: str = ""
    cosmos_database: str = "ai-agent"
    cosmos_container: str = "toppings"

    sqlite_path: str = "./topping_service.db"

    cors_allow_origins: str = "*"


@lru_cache
def get_settings() -> Settings:
    return Settings()
