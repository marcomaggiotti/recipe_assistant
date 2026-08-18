"""Topping catalog storage - mirrors app/db.py's PizzaRepository pattern (sqlite by
default, Postgres or Azure Cosmos DB via DB_BACKEND/TOPPING_DB_BACKEND), but as its own
independent store for this service's own `toppings` table/container.

build_repository() seeds TOPPING_CATALOG (see catalog.py) into the table the first time
it's empty, so the service starts with a real pizzeria menu to browse/select from rather
than an empty list - toppings are still a fully mutable, user-editable catalog though
(unlike the read-mostly flour catalog), so this is just a starting point.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from .catalog import TOPPING_CATALOG
from .config import Settings


class ToppingRepository(ABC):
    @abstractmethod
    def create(self, topping: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def get(self, item_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def list(self, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]: ...

    @abstractmethod
    def delete(self, item_id: str) -> bool: ...


def _new_record(topping: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        **topping,
    }


class SqliteToppingRepository(ToppingRepository):
    """Zero-config default so the service runs out of the box without any managed DB."""

    def __init__(self, settings: Settings):
        self._conn = sqlite3.connect(settings.sqlite_path, check_same_thread=False)
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS toppings (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )"""
        )
        self._conn.commit()

    def create(self, topping):
        record = _new_record(topping)
        self._conn.execute(
            "INSERT INTO toppings (id, created_at, payload) VALUES (?, ?, ?)",
            (record["id"], record["created_at"], json.dumps(record)),
        )
        self._conn.commit()
        return record

    def get(self, item_id):
        row = self._conn.execute("SELECT payload FROM toppings WHERE id = ?", (item_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, limit, offset):
        total = self._conn.execute("SELECT COUNT(*) FROM toppings").fetchone()[0]
        rows = self._conn.execute(
            "SELECT payload FROM toppings ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset),
        ).fetchall()
        return [json.loads(r[0]) for r in rows], total

    def delete(self, item_id):
        cur = self._conn.execute("DELETE FROM toppings WHERE id = ?", (item_id,))
        self._conn.commit()
        return cur.rowcount > 0


class PostgresToppingRepository(ToppingRepository):
    """Works against any Postgres-wire-compatible DB, including Render's managed Postgres."""

    def __init__(self, settings: Settings):
        from sqlalchemy import create_engine, text

        self._text = text
        self._engine = create_engine(settings.postgres_url, pool_pre_ping=True)
        with self._engine.begin() as conn:
            conn.execute(text(
                """CREATE TABLE IF NOT EXISTS toppings (
                    id TEXT PRIMARY KEY,
                    created_at TIMESTAMPTZ NOT NULL,
                    payload JSONB NOT NULL
                )"""
            ))

    def create(self, topping):
        record = _new_record(topping)
        with self._engine.begin() as conn:
            conn.execute(self._text(
                "INSERT INTO toppings (id, created_at, payload) VALUES (:id, :created_at, :payload)"
            ), {"id": record["id"], "created_at": record["created_at"], "payload": json.dumps(record)})
        return record

    def get(self, item_id):
        with self._engine.begin() as conn:
            row = conn.execute(self._text(
                "SELECT payload FROM toppings WHERE id = :id"
            ), {"id": item_id}).fetchone()
        if not row:
            return None
        return row[0] if isinstance(row[0], dict) else json.loads(row[0])

    def list(self, limit, offset):
        with self._engine.begin() as conn:
            total = conn.execute(self._text("SELECT COUNT(*) FROM toppings")).scalar_one()
            rows = conn.execute(self._text(
                "SELECT payload FROM toppings ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
            ), {"limit": limit, "offset": offset}).fetchall()
        return [r[0] if isinstance(r[0], dict) else json.loads(r[0]) for r in rows], total

    def delete(self, item_id):
        with self._engine.begin() as conn:
            result = conn.execute(self._text("DELETE FROM toppings WHERE id = :id"), {"id": item_id})
        return result.rowcount > 0


class CosmosToppingRepository(ToppingRepository):
    """Azure Cosmos DB (NoSQL API)."""

    def __init__(self, settings: Settings):
        from azure.cosmos import CosmosClient, PartitionKey

        client = CosmosClient(settings.cosmos_endpoint, credential=settings.cosmos_key)
        database = client.create_database_if_not_exists(id=settings.cosmos_database)
        self._container = database.create_container_if_not_exists(
            id=settings.cosmos_container, partition_key=PartitionKey(path="/id")
        )

    def create(self, topping):
        record = _new_record(topping)
        self._container.create_item(body=record)
        return record

    def get(self, item_id):
        try:
            return self._container.read_item(item=item_id, partition_key=item_id)
        except Exception:
            return None

    def list(self, limit, offset):
        query = "SELECT * FROM c ORDER BY c.created_at DESC"
        items = list(self._container.query_items(query=query, enable_cross_partition_query=True))
        total = len(items)
        return items[offset: offset + limit], total

    def delete(self, item_id):
        try:
            self._container.delete_item(item=item_id, partition_key=item_id)
            return True
        except Exception:
            return False


def _seed_if_empty(repo: ToppingRepository) -> None:
    _, total = repo.list(1, 0)
    if total:
        return
    for topping in TOPPING_CATALOG:
        repo.create(dict(topping))


def build_repository(settings: Settings) -> ToppingRepository:
    if settings.db_backend == "postgres":
        repo: ToppingRepository = PostgresToppingRepository(settings)
    elif settings.db_backend == "cosmos":
        repo = CosmosToppingRepository(settings)
    else:
        repo = SqliteToppingRepository(settings)
    _seed_if_empty(repo)
    return repo
