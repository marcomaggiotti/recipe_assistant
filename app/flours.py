"""International flour catalogue.

Fetched live from the standalone flour-service microservice
(github.com/marcomaggiotti/flour_service, `flour_service_url`) - the same catalogue the
/flour-explorer and /new-recipe browser pages already call directly from client-side
JS. This repo keeps no local copy of the catalogue data; flour-service is the single
source of truth for it.

Every flour cited when creating a recipe (POST /recipes, /recipes/generate, and the
agent's generate/save tools) is identified by its `pizza_flours_id` field, resolved via
flour-service's `GET /flours/by-name` - which is purpose-built to match against a
flour's id, any of its localized names, or a bare national type code ("00", "T45",
"405", ...), case-insensitively, disambiguated by `ash%` when more than one entry
matches (see that endpoint's own docstring in flour-service). This service doesn't
reimplement that matching logic - it just calls the endpoint that already does.

There's no local caching here - every list()/resolve() call hits flour-service live, so
catalogue edits made there are picked up immediately, with no redeploy of this service
needed. The tradeoff: /recipes/generate, POST /recipes, and the agent's recipe tools
now have a hard runtime dependency on flour-service being reachable, and fail clearly
(ValueError, surfaced as a 400 / agent tool error) if it isn't, rather than falling
back to stale local data.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .config import Settings


class FlourCatalogStore(ABC):
    @abstractmethod
    def list(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def resolve(self, description: str, ash_pct: float | None = None) -> dict[str, Any] | None: ...


class HttpFlourCatalogStore(FlourCatalogStore):
    """Talks to flour-service's own GET /flours and GET /flours/by-name - not a generic
    cache of the full catalogue, since /flours/by-name already implements the exact
    id/name/type-code/ash disambiguation this service needs."""

    def __init__(self, settings: Settings):
        self._base_url = settings.flour_service_url.rstrip("/")
        self._api_key = settings.flour_service_api_key

    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self._api_key} if self._api_key else {}

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        import httpx

        try:
            response = httpx.get(f"{self._base_url}{path}", params=params, headers=self._headers(), timeout=5.0)
        except httpx.HTTPError as exc:
            raise ValueError(
                f"flour catalogue unavailable - could not reach flour-service at {self._base_url} ({exc})"
            ) from exc
        if response.status_code == 404:
            return None
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ValueError(f"flour-service returned an error ({exc})") from exc
        return response.json()

    def list(self):
        return self._get("/flours")["items"]

    def resolve(self, description, ash_pct=None):
        params: dict[str, Any] = {"name": description}
        if ash_pct is not None:
            params["ash%"] = ash_pct
        return self._get("/flours/by-name", params=params)


def build_flour_catalog_store(settings: Settings) -> FlourCatalogStore:
    return HttpFlourCatalogStore(settings)
