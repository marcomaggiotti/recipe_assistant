"""Repository abstraction so the service can run against local sqlite (zero-config dev),
Render/managed Postgres, or Azure Cosmos DB by flipping DB_BACKEND in the environment.

Saved recipes store the full computed result (flours, ingredients, fermentation
schedule, pre-ferment breakdown, ...) as a JSON payload alongside a few indexed columns.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from .config import Settings


class PizzaRepository(ABC):
    @abstractmethod
    def create(self, name: str, result: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def get(self, item_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def list(self, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]: ...

    @abstractmethod
    def delete(self, item_id: str) -> bool: ...


def _new_record(name: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        **result,
    }


class SqlitePizzaRepository(PizzaRepository):
    """Zero-config default so the service runs out of the box without any managed DB."""

    def __init__(self, settings: Settings):
        self._conn = sqlite3.connect(settings.sqlite_path, check_same_thread=False)
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS pizza_recipes (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )"""
        )
        self._conn.commit()

    def create(self, name, result):
        record = _new_record(name, result)
        self._conn.execute(
            "INSERT INTO pizza_recipes (id, name, created_at, payload) VALUES (?, ?, ?, ?)",
            (record["id"], record["name"], record["created_at"], json.dumps(record)),
        )
        self._conn.commit()
        return record

    def get(self, item_id):
        row = self._conn.execute("SELECT payload FROM pizza_recipes WHERE id = ?", (item_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, limit, offset):
        total = self._conn.execute("SELECT COUNT(*) FROM pizza_recipes").fetchone()[0]
        rows = self._conn.execute(
            "SELECT payload FROM pizza_recipes ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset),
        ).fetchall()
        return [json.loads(r[0]) for r in rows], total

    def delete(self, item_id):
        cur = self._conn.execute("DELETE FROM pizza_recipes WHERE id = ?", (item_id,))
        self._conn.commit()
        return cur.rowcount > 0


class PostgresPizzaRepository(PizzaRepository):
    """Works against any Postgres-wire-compatible DB, including Render's managed Postgres."""

    def __init__(self, settings: Settings):
        from sqlalchemy import create_engine, text

        self._text = text
        self._engine = create_engine(settings.postgres_url, pool_pre_ping=True)
        with self._engine.begin() as conn:
            conn.execute(text(
                """CREATE TABLE IF NOT EXISTS pizza_recipes (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    payload JSONB NOT NULL
                )"""
            ))

    def create(self, name, result):
        record = _new_record(name, result)
        with self._engine.begin() as conn:
            conn.execute(self._text(
                "INSERT INTO pizza_recipes (id, name, created_at, payload)"
                " VALUES (:id, :name, :created_at, :payload)"
            ), {
                "id": record["id"], "name": record["name"], "created_at": record["created_at"],
                "payload": json.dumps(record),
            })
        return record

    def get(self, item_id):
        with self._engine.begin() as conn:
            row = conn.execute(self._text(
                "SELECT payload FROM pizza_recipes WHERE id = :id"
            ), {"id": item_id}).fetchone()
        if not row:
            return None
        return row[0] if isinstance(row[0], dict) else json.loads(row[0])

    def list(self, limit, offset):
        with self._engine.begin() as conn:
            total = conn.execute(self._text("SELECT COUNT(*) FROM pizza_recipes")).scalar_one()
            rows = conn.execute(self._text(
                "SELECT payload FROM pizza_recipes ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
            ), {"limit": limit, "offset": offset}).fetchall()
        return [r[0] if isinstance(r[0], dict) else json.loads(r[0]) for r in rows], total

    def delete(self, item_id):
        with self._engine.begin() as conn:
            result = conn.execute(self._text("DELETE FROM pizza_recipes WHERE id = :id"), {"id": item_id})
        return result.rowcount > 0


class CosmosPizzaRepository(PizzaRepository):
    """Azure Cosmos DB (NoSQL API).

    get()/delete() deliberately do NOT do a partition-key point read/delete keyed on
    item_id (i.e. container.read_item(item=id, partition_key=id)) - that only returns
    correct results if the container's actual partition key path is "/id". This code
    only sets that partition key when IT creates a brand-new container;
    create_container_if_not_exists() silently returns an already-existing container
    as-is, ignoring the partition_key argument, if one by that name/id already exists
    (e.g. created manually in the Azure Portal, or by an earlier version of this code).
    A point read/delete against the wrong partition key value looks in the wrong
    physical partition and Cosmos correctly reports "not found" even though the
    document exists elsewhere in the container - which would silently 404 a real,
    listable recipe. Querying by id (like list() already does) is slightly more
    expensive in RUs but correct regardless of the container's actual partition key.
    """

    def __init__(self, settings: Settings):
        from azure.cosmos import CosmosClient, PartitionKey

        client = CosmosClient(settings.cosmos_endpoint, credential=settings.cosmos_key)
        database = client.create_database_if_not_exists(id=settings.cosmos_database)
        self._container = database.create_container_if_not_exists(
            id=settings.cosmos_container, partition_key=PartitionKey(path="/id")
        )
        # The actual partition key path (only known for certain once the container
        # exists - see class docstring) - used to pull the right value out of a found
        # record for delete_item(), which unlike query_items() always needs one.
        # Assumes a single-segment top-level path ("/id", "/pk", ...), true for every
        # container this app creates or expects; a deeper path (e.g. "/a/b") isn't
        # supported and would need this to walk record[a][b] instead.
        self._partition_key_field = self._container.read()["partitionKey"]["paths"][0].lstrip("/")

    def create(self, name, result):
        record = _new_record(name, result)
        self._container.create_item(body=record)
        return record

    def _find(self, item_id):
        query = "SELECT * FROM c WHERE c.id = @id"
        items = list(self._container.query_items(
            query=query, parameters=[{"name": "@id", "value": item_id}],
            enable_cross_partition_query=True,
        ))
        return items[0] if items else None

    def get(self, item_id):
        return self._find(item_id)

    def list(self, limit, offset):
        query = "SELECT * FROM c ORDER BY c.created_at DESC"
        items = list(self._container.query_items(query=query, enable_cross_partition_query=True))
        total = len(items)
        return items[offset: offset + limit], total

    def delete(self, item_id):
        record = self._find(item_id)
        if record is None:
            return False
        self._container.delete_item(item=record, partition_key=record[self._partition_key_field])
        return True


def build_repository(settings: Settings) -> PizzaRepository:
    if settings.db_backend == "postgres":
        return PostgresPizzaRepository(settings)
    if settings.db_backend == "cosmos":
        return CosmosPizzaRepository(settings)
    return SqlitePizzaRepository(settings)
