"""Named pre-ferment "type" definitions: reusable blends a recipe's pre_ferment can
reference by type_id instead of describing inline, e.g.:

    biga100             -> [{"name": "biga", "percentage": 100}]
    biga80_sourdough20  -> [{"name": "biga", "percentage": 80}, {"name": "sourdough", "percentage": 20}]

A recipe references one via `pre_ferment.type_id` (see schemas.py's PreFerment).
recipe.py's dough engine always computes ONE aggregate preferment formula from the
referenced blend - named components are descriptive/echoed metadata only, never
computed separately. A row deliberately carries no technique/hydration/resting-hours
columns - just the type_id and its preferments breakdown.

Prefers Postgres via `settings.postgres_url`, independent of the app's overall
DB_BACKEND - so a deployment can run everything else (recipes, flours) on sqlite or
Cosmos and still use this feature, just by pointing POSTGRES_URL at a real Postgres
instance (e.g. a small Render-managed Postgres database dedicated to this one table -
see render.yaml). If Postgres isn't reachable, falls back to a local sqlite file
(settings.sqlite_path) so the feature keeps working rather than erroring - e.g. local
dev with no Postgres running at all. The choice is made lazily on first actual use (not
at construction, keeping app startup non-blocking) and cached for the process, so a
single running instance doesn't flip-flop between backends mid-flight.
"""
from __future__ import annotations

import json
import sqlite3
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
        # create_engine() doesn't connect - safe to call eagerly even when POSTGRES_URL
        # isn't reachable. Each method below connects lazily via _run(), on actual use.
        self._engine = create_engine(settings.postgres_url, pool_pre_ping=True)

    def _run(self, fn):
        from sqlalchemy.exc import SQLAlchemyError

        try:
            with self._engine.begin() as conn:
                conn.execute(self._text(
                    """CREATE TABLE IF NOT EXISTS pre_ferment_types (
                        type_id TEXT PRIMARY KEY,
                        preferments JSONB NOT NULL
                    )"""
                ))
                return fn(conn)
        except SQLAlchemyError as exc:
            raise ValueError(
                "pre_ferment types require a reachable Postgres database - check that "
                f"POSTGRES_URL is set correctly ({exc})"
            ) from exc

    def create(self, type_id, preferments):
        record = {"type_id": type_id, "preferments": preferments}
        self._run(lambda conn: conn.execute(
            self._text("INSERT INTO pre_ferment_types (type_id, preferments) VALUES (:type_id, :preferments)"),
            {"type_id": type_id, "preferments": json.dumps(preferments)},
        ))
        return record

    def get(self, type_id):
        row = self._run(lambda conn: conn.execute(
            self._text("SELECT type_id, preferments FROM pre_ferment_types WHERE type_id = :type_id"),
            {"type_id": type_id},
        ).fetchone())
        if not row:
            return None
        return {"type_id": row[0], "preferments": row[1] if isinstance(row[1], list) else json.loads(row[1])}

    def list(self):
        rows = self._run(lambda conn: conn.execute(
            self._text("SELECT type_id, preferments FROM pre_ferment_types ORDER BY type_id")
        ).fetchall())
        return [{"type_id": r[0], "preferments": r[1] if isinstance(r[1], list) else json.loads(r[1])} for r in rows]

    def delete(self, type_id):
        result = self._run(lambda conn: conn.execute(
            self._text("DELETE FROM pre_ferment_types WHERE type_id = :type_id"), {"type_id": type_id},
        ))
        return result.rowcount > 0


class SqlitePreFermentTypeStore(PreFermentTypeStore):
    """Fallback used when Postgres isn't reachable - stores pre_ferment_types in the
    same local sqlite file as PizzaRepository's sqlite backend (settings.sqlite_path),
    independent of DB_BACKEND."""

    def __init__(self, settings: Settings):
        self._path = settings.sqlite_path
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS pre_ferment_types (type_id TEXT PRIMARY KEY, preferments TEXT NOT NULL)"
            )

    def _connect(self):
        return sqlite3.connect(self._path)

    def create(self, type_id, preferments):
        record = {"type_id": type_id, "preferments": preferments}
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO pre_ferment_types (type_id, preferments) VALUES (?, ?)",
                (type_id, json.dumps(preferments)),
            )
        return record

    def get(self, type_id):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT type_id, preferments FROM pre_ferment_types WHERE type_id = ?", (type_id,)
            ).fetchone()
        if not row:
            return None
        return {"type_id": row[0], "preferments": json.loads(row[1])}

    def list(self):
        with self._connect() as conn:
            rows = conn.execute("SELECT type_id, preferments FROM pre_ferment_types ORDER BY type_id").fetchall()
        return [{"type_id": r[0], "preferments": json.loads(r[1])} for r in rows]

    def delete(self, type_id):
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM pre_ferment_types WHERE type_id = ?", (type_id,))
        return cursor.rowcount > 0


class _FallbackPreFermentTypeStore(PreFermentTypeStore):
    """Prefers Postgres; falls back to sqlite the first time Postgres proves
    unreachable, then sticks with whichever backend it resolved to for the rest of the
    process. Resolution happens lazily on first actual use rather than at construction,
    so building this eagerly at app startup (main.py's lifespan) never blocks on a
    Postgres connection attempt."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._resolved: PreFermentTypeStore | None = None

    def _resolve(self) -> PreFermentTypeStore:
        if self._resolved is None:
            postgres = PostgresPreFermentTypeStore(self._settings)
            try:
                postgres.list()  # cheap connectivity probe; also ensures the table exists
                self._resolved = postgres
            except ValueError:
                self._resolved = SqlitePreFermentTypeStore(self._settings)
        return self._resolved

    def create(self, type_id, preferments):
        return self._resolve().create(type_id, preferments)

    def get(self, type_id):
        return self._resolve().get(type_id)

    def list(self):
        return self._resolve().list()

    def delete(self, type_id):
        return self._resolve().delete(type_id)


def build_pre_ferment_type_store(settings: Settings) -> PreFermentTypeStore:
    return _FallbackPreFermentTypeStore(settings)
