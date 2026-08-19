"""Named pre-ferment "type" definitions: reusable blends a recipe's pre_ferment can
reference by type_id instead of describing inline, e.g.:

    biga100             -> [{"name": "biga", "percentage": 100}]
    biga80_sourdough20  -> [{"name": "biga", "percentage": 80}, {"name": "sourdough", "percentage": 20}]

A recipe references one via `pre_ferment.type_id` (see schemas.py's PreFerment).
recipe.py's dough engine always computes ONE aggregate preferment formula from the
referenced blend - named components are descriptive/echoed metadata only, never
computed separately. A row deliberately carries no technique/hydration/resting-hours
columns - just the type_id and its preferments breakdown.

Always backed by Postgres via `settings.postgres_url`, independent of the app's overall
DB_BACKEND - so a deployment can run everything else (recipes, flours) on sqlite or
Cosmos and still use this feature, just by pointing POSTGRES_URL at a real Postgres
instance (e.g. a small Render-managed Postgres database dedicated to this one table -
see render.yaml). There is deliberately no local-storage fallback: Render's free web
service tier has no persistent disk, so a sqlite fallback would silently write
composed pre-ferment types to storage that's wiped on the next restart/redeploy - if
Postgres isn't reachable, this raises a clear ValueError (surfaced as a 400) instead.
The engine connects lazily on first actual use (not at construction, keeping app
startup non-blocking), same as before.
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


def build_pre_ferment_type_store(settings: Settings) -> PreFermentTypeStore:
    return PostgresPreFermentTypeStore(settings)
