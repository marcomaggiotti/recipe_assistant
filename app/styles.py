"""Pizza-chef/cookbook style library storage.

STYLE_LIBRARY in recipe.py is seed data only. When the service is configured for
Cosmos DB (DB_BACKEND=cosmos), that seed data is written into its own Cosmos
container on first use and served from there afterwards - so styles live in the
database, not hardcoded in source, and can be added/edited/removed via Cosmos without
a redeploy. Non-Cosmos backends (local dev, tests) just serve the seed data directly.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .config import Settings
from .recipe import STYLE_LIBRARY


class StyleStore(ABC):
    @abstractmethod
    def get(self, key: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def list(self) -> dict[str, dict[str, Any]]: ...


class InMemoryStyleStore(StyleStore):
    def get(self, key):
        return STYLE_LIBRARY.get(key)

    def list(self):
        return dict(STYLE_LIBRARY)


class CosmosStyleStore(StyleStore):
    def __init__(self, settings: Settings):
        from azure.cosmos import CosmosClient, PartitionKey

        client = CosmosClient(settings.cosmos_endpoint, credential=settings.cosmos_key)
        database = client.create_database_if_not_exists(id=settings.cosmos_database)
        self._container = database.create_container_if_not_exists(
            id=settings.cosmos_styles_container, partition_key=PartitionKey(path="/id")
        )
        self._seed_if_empty()

    def _seed_if_empty(self):
        count = next(iter(self._container.query_items(
            query="SELECT VALUE COUNT(1) FROM c", enable_cross_partition_query=True
        )), 0)
        if count:
            return
        for key, style in STYLE_LIBRARY.items():
            self._container.upsert_item({"id": key, **style})

    def get(self, key):
        try:
            return self._container.read_item(item=key, partition_key=key)
        except Exception:
            return None

    def list(self):
        items = self._container.query_items(query="SELECT * FROM c", enable_cross_partition_query=True)
        return {item["id"]: item for item in items}


def build_style_store(settings: Settings) -> StyleStore:
    if settings.db_backend == "cosmos":
        return CosmosStyleStore(settings)
    return InMemoryStyleStore()
