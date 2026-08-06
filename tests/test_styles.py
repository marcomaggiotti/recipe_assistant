from app.config import Settings
from app.recipe import STYLE_LIBRARY
from app.styles import InMemoryStyleStore, build_style_store


def test_in_memory_store_serves_seed_data():
    store = InMemoryStyleStore()
    assert store.get("neapolitan_avpn") == STYLE_LIBRARY["neapolitan_avpn"]
    assert store.get("does_not_exist") is None
    assert store.list() == STYLE_LIBRARY


def test_build_style_store_defaults_to_in_memory_for_non_cosmos_backends():
    for backend in ("sqlite", "postgres"):
        store = build_style_store(Settings(db_backend=backend))
        assert isinstance(store, InMemoryStyleStore)
