"""app/flours.py's catalogue now lives entirely in the standalone flour-service
microservice (a separate repo/deployment) - this repo keeps no local copy. Tests
shouldn't depend on real network access to that service (unreachable in CI/sandboxed
environments, and flaky/slow even when reachable), so every test gets a small local
fixture catalogue instead, covering exactly the flour ids the test suite references.
"""
import pytest

from app.flours import FlourCatalogStore

_FIXTURE_FLOURS = [
    {
        "id": "soft_wheat_00", "pizza_flours_id": "soft_wheat_00", "category": "wheat",
        "gluten": True, "bread": True, "pizza": True, "max_blend_pct": 100, "description": None,
        "ash_min_pct": 0.00, "ash_max_pct": 0.55,
        "names": {"en": "Soft wheat flour type 00", "it": "Farina 00", "fr": "Farine T45", "de": "Weizenmehl 405"},
    },
    {
        "id": "whole_wheat", "pizza_flours_id": "whole_wheat", "category": "wheat",
        "gluten": True, "bread": True, "pizza": True, "max_blend_pct": 100, "description": None,
        "ash_min_pct": 1.20, "ash_max_pct": 1.80,
        "names": {"en": "Whole wheat flour", "it": "Farina integrale", "fr": "Farine T150", "de": "Weizenvollkornmehl"},
    },
    {
        "id": "durum_semolina", "pizza_flours_id": "durum_semolina", "category": "durum_wheat",
        "gluten": True, "bread": True, "pizza": False, "max_blend_pct": 100, "description": None,
        "names": {"en": "Durum wheat semolina", "it": "Semola di grano duro", "fr": "Semoule de blé dur", "de": "Hartweizengriess"},
    },
    {
        "id": "durum_rimacinata", "pizza_flours_id": "durum_rimacinata", "category": "durum_wheat",
        "gluten": True, "bread": True, "pizza": True, "max_blend_pct": 100, "description": "Pane di Altamura, Sicilian bread",
        "names": {"en": "Re-milled durum semolina", "it": "Semola rimacinata", "fr": "Semoule fine de blé dur", "de": "Hartweizenmehl"},
    },
    {
        "id": "rice_white", "pizza_flours_id": "rice_white", "category": "cereal_gf",
        "gluten": False, "bread": True, "pizza": True, "max_blend_pct": 30, "description": "Base of most GF blends",
        "names": {"en": "White rice flour", "it": "Farina di riso", "fr": "Farine de riz", "de": "Reismehl"},
    },
]


class _FixtureFlourCatalogStore(FlourCatalogStore):
    def list(self):
        return _FIXTURE_FLOURS

    def resolve(self, description, ash_pct=None):
        needle = description.strip().lower()
        matches = [
            f for f in self.list()
            if needle == f["id"].strip().lower() or needle in {n.strip().lower() for n in f.get("names", {}).values() if n}
        ]
        if not matches:
            return None
        if ash_pct is not None and len(matches) > 1:
            for f in matches:
                lo, hi = f.get("ash_min_pct"), f.get("ash_max_pct")
                if lo is not None and hi is not None and lo <= ash_pct <= hi:
                    return f
        return matches[0]


@pytest.fixture(autouse=True)
def _stub_flour_catalog_store(monkeypatch):
    from app.routers import pizza

    monkeypatch.setattr(pizza, "get_flour_catalog_store", lambda: _FixtureFlourCatalogStore())
