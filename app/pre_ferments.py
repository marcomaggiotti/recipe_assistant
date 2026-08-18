"""Named pre-ferment "type" definitions: reusable blends a recipe's pre_ferment can
reference by type_id instead of describing inline, e.g.:

    biga100             -> [{"name": "biga", "percentage": 100}]
    biga80_sourdough20  -> [{"name": "biga", "percentage": 80}, {"name": "sourdough", "percentage": 20}]

A recipe references one via `pre_ferment.type_id` (see schemas.py's PreFerment).
recipe.py's dough engine always computes ONE aggregate preferment formula from the
referenced blend - named components are descriptive/echoed metadata only, never
computed separately. A row deliberately carries no technique/hydration/resting-hours
columns - just the type_id and its preferments breakdown.

Postgres-only, unlike flours.py's in-memory-by-default pattern - there's no
seed data for this table (it's populated by callers via POST /pre-ferment-types), and
it's explicitly modeled as a relational table from the start. Other DB_BACKEND values
raise clearly when the store is actually used, rather than silently behaving as if no
types exist.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from .config import Settings


class PreFermentTypeStore(ABC):
    @abstractmethod
    def create(self, type_id: str, preferments: list[dict[str, Any]]) -> dict[str, Any]: ...

    @abstractmethod
    def get(self, type_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def list(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def delete(self, type_id: str) -> bool: ...


class PostgresPreFermentTypeStore(PreFermentTypeStore):
    def __init__(self, settings: Settings):
        from sqlalchemy import create_engine, text

        self._text = text
        self._engine = create_engine(settings.postgres_url, pool_pre_ping=True)
        with self._engine.begin() as conn:
            conn.execute(text(
                """CREATE TABLE IF NOT EXISTS pre_ferment_types (
                    type_id TEXT PRIMARY KEY,
                    preferments JSONB NOT NULL
                )"""
            ))

    def create(self, type_id, preferments):
        record = {"type_id": type_id, "preferments": preferments}
        with self._engine.begin() as conn:
            conn.execute(self._text(
                "INSERT INTO pre_ferment_types (type_id, preferments) VALUES (:type_id, :preferments)"
            ), {"type_id": type_id, "preferments": json.dumps(preferments)})
        return record

    def get(self, type_id):
        with self._engine.begin() as conn:
            row = conn.execute(self._text(
                "SELECT type_id, preferments FROM pre_ferment_types WHERE type_id = :type_id"
            ), {"type_id": type_id}).fetchone()
        if not row:
            return None
        return {"type_id": row[0], "preferments": row[1] if isinstance(row[1], list) else json.loads(row[1])}

    def list(self):
        with self._engine.begin() as conn:
            rows = conn.execute(self._text("SELECT type_id, preferments FROM pre_ferment_types ORDER BY type_id")).fetchall()
        return [{"type_id": r[0], "preferments": r[1] if isinstance(r[1], list) else json.loads(r[1])} for r in rows]

    def delete(self, type_id):
        with self._engine.begin() as conn:
            result = conn.execute(self._text("DELETE FROM pre_ferment_types WHERE type_id = :type_id"), {"type_id": type_id})
        return result.rowcount > 0


class UnsupportedBackendPreFermentTypeStore(PreFermentTypeStore):
    """DB_BACKEND != postgres: pre_ferment types simply aren't available - raise
    clearly on actual use rather than silently behaving as if none exist (construction
    itself doesn't raise, so this is safe to build eagerly at app startup regardless of
    backend)."""

    def __init__(self, backend: str):
        self._backend = backend

    def _unsupported(self):
        raise ValueError(f"pre_ferment types require DB_BACKEND=postgres (current backend: '{self._backend}')")

    def create(self, type_id, preferments):
        self._unsupported()

    def get(self, type_id):
        self._unsupported()

    def list(self):
        self._unsupported()

    def delete(self, type_id):
        self._unsupported()


def build_pre_ferment_type_store(settings: Settings) -> PreFermentTypeStore:
    if settings.db_backend == "postgres":
        return PostgresPreFermentTypeStore(settings)
    return UnsupportedBackendPreFermentTypeStore(settings.db_backend)
