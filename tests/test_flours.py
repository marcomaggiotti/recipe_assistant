from app.config import Settings
from app.flours import FLOUR_CATALOG, InMemoryFlourCatalogStore, build_flour_catalog_store


def test_resolves_by_id():
    store = InMemoryFlourCatalogStore()
    assert store.resolve("soft_wheat_00")["id"] == "soft_wheat_00"


def test_resolves_by_localized_name_case_insensitively():
    store = InMemoryFlourCatalogStore()
    assert store.resolve("Farina 00")["id"] == "soft_wheat_00"
    assert store.resolve("farina 00")["id"] == "soft_wheat_00"
    assert store.resolve("Weizenmehl 405")["id"] == "soft_wheat_00"
    assert store.resolve("Farine T45")["id"] == "soft_wheat_00"
    assert store.resolve("Farina di riso")["id"] == "rice_white"
    assert store.resolve("Semola rimacinata")["id"] == "durum_rimacinata"


def test_resolves_bare_national_type_codes():
    store = InMemoryFlourCatalogStore()
    assert store.resolve("00")["id"] == "soft_wheat_00"
    assert store.resolve("T45")["id"] == "soft_wheat_00"
    assert store.resolve("405")["id"] == "soft_wheat_00"
    assert store.resolve("0")["id"] == "soft_wheat_0"
    assert store.resolve("integrale")["id"] == "whole_wheat"


def test_unrecognized_flour_does_not_resolve():
    store = InMemoryFlourCatalogStore()
    assert store.resolve("moon dust") is None
    assert store.resolve("") is None


def test_wheat_refinement_grades_carry_ash_content():
    store = InMemoryFlourCatalogStore()
    assert store.resolve("00")["ash_max_pct"] == 0.55
    assert store.resolve("integrale")["ash_min_pct"] == 1.20
    assert store.resolve("rye")["ash_max_pct"] == 2.00


def test_flours_without_a_tracked_ash_grade_have_none():
    store = InMemoryFlourCatalogStore()
    assert store.resolve("rice_white").get("ash_min_pct") is None
    assert store.resolve("durum_rimacinata").get("ash_min_pct") is None


def test_ash_pct_disambiguates_when_description_alone_would_be_ambiguous():
    store = InMemoryFlourCatalogStore()
    ambiguous = [
        {**flour, "names": {"en": "Ambiguous wheat"}}
        for flour in FLOUR_CATALOG if flour["id"] in ("soft_wheat_00", "soft_wheat_0")
    ]

    class _FixtureStore(InMemoryFlourCatalogStore):
        def list(self):
            return ambiguous

    fixture = _FixtureStore()
    assert fixture.resolve("Ambiguous wheat", 0.30)["id"] == "soft_wheat_00"
    assert fixture.resolve("Ambiguous wheat", 0.60)["id"] == "soft_wheat_0"


def test_every_alias_maps_to_exactly_one_flour():
    # A bare code like "00" or "1" must not be ambiguous between two catalogue entries.
    store = InMemoryFlourCatalogStore()
    seen: dict[str, str] = {}
    for flour in FLOUR_CATALOG:
        for key in [flour["id"], *flour.get("names", {}).values()]:
            if not key:
                continue
            key = key.strip().lower()
            resolved = store.resolve(key)
            assert resolved is not None, f"{key!r} should resolve"
            seen.setdefault(key, resolved["id"])
            assert seen[key] == resolved["id"], f"{key!r} resolves inconsistently"


def test_build_flour_catalog_store_defaults_to_in_memory_for_non_cosmos_backends():
    for backend in ("sqlite", "postgres"):
        store = build_flour_catalog_store(Settings(db_backend=backend))
        assert isinstance(store, InMemoryFlourCatalogStore)
