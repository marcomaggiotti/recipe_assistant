import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.pre_ferments import build_pre_ferment_type_store

client = TestClient(app)


def _has_local_postgres() -> bool:
    try:
        from sqlalchemy import create_engine

        create_engine(Settings().postgres_url).connect().close()
        return True
    except Exception:
        return False


# pre_ferment_types always connects via settings.postgres_url, independent of
# DB_BACKEND (see app/pre_ferments.py) - so these tests just need a reachable local
# Postgres, not the whole suite run with DB_BACKEND=postgres.
requires_postgres = pytest.mark.skipif(not _has_local_postgres(), reason="no local postgres available")


def _unreachable_settings() -> Settings:
    return Settings(postgres_url="postgresql+psycopg2://nope:nope@localhost:1/nope")


def test_store_raises_a_clear_error_when_postgres_is_unreachable():
    # There is deliberately no local-storage fallback (Render's free tier has no
    # persistent disk to fall back onto) - an unreachable Postgres must fail loudly
    # rather than silently writing to storage that won't survive a restart.
    store = build_pre_ferment_type_store(_unreachable_settings())
    with pytest.raises(ValueError, match="pre_ferment types require a reachable Postgres database"):
        store.list()


def test_store_never_raises_or_blocks_on_construction_even_with_unreachable_postgres_url():
    # main.py's lifespan builds this eagerly on every boot - the actual connection
    # attempt happens lazily on first use, never at construction.
    build_pre_ferment_type_store(_unreachable_settings())


@requires_postgres
def test_postgres_store_create_get_list_delete_roundtrip():
    store = build_pre_ferment_type_store(Settings())
    type_id = f"test_{uuid.uuid4().hex[:8]}"
    try:
        created = store.create(type_id, [{"name": "biga", "percentage": 100}])
        assert created == {"type_id": type_id, "preferments": [{"name": "biga", "percentage": 100}]}

        fetched = store.get(type_id)
        assert fetched == created

        assert any(item["type_id"] == type_id for item in store.list())
    finally:
        assert store.delete(type_id) is True
    assert store.get(type_id) is None


@requires_postgres
def test_api_create_and_get_pre_ferment_type():
    type_id = f"test_{uuid.uuid4().hex[:8]}"
    try:
        create = client.post(
            "/pre-ferment-types",
            json={"type_id": type_id, "preferments": [{"name": "biga", "percentage": 80}, {"name": "sourdough", "percentage": 20}]},
        )
        assert create.status_code == 201

        get = client.get(f"/pre-ferment-types/{type_id}")
        assert get.status_code == 200
        assert get.json()["preferments"] == [{"name": "biga", "percentage": 80}, {"name": "sourdough", "percentage": 20}]

        listing = client.get("/pre-ferment-types")
        assert any(item["type_id"] == type_id for item in listing.json()["items"])
    finally:
        client.delete(f"/pre-ferment-types/{type_id}")


@requires_postgres
def test_api_rejects_percentages_not_summing_to_100():
    response = client.post(
        "/pre-ferment-types",
        json={"type_id": f"test_{uuid.uuid4().hex[:8]}", "preferments": [{"name": "biga", "percentage": 60}]},
    )
    assert response.status_code == 422


@requires_postgres
def test_api_rejects_duplicate_id():
    type_id = f"test_{uuid.uuid4().hex[:8]}"
    try:
        first = client.post("/pre-ferment-types", json={"type_id": type_id, "preferments": [{"name": "poolish", "percentage": 100}]})
        assert first.status_code == 201
        second = client.post("/pre-ferment-types", json={"type_id": type_id, "preferments": [{"name": "biga", "percentage": 100}]})
        assert second.status_code == 400
    finally:
        client.delete(f"/pre-ferment-types/{type_id}")


@requires_postgres
def test_api_get_and_delete_unknown_type_id_returns_404():
    assert client.get("/pre-ferment-types/does_not_exist").status_code == 404
    assert client.delete("/pre-ferment-types/does_not_exist").status_code == 404


@requires_postgres
def test_recipe_generate_resolves_pre_ferment_by_type_id():
    type_id = f"test_{uuid.uuid4().hex[:8]}"
    try:
        client.post(
            "/pre-ferment-types",
            json={"type_id": type_id, "preferments": [{"name": "biga", "percentage": 60}, {"name": "poolish", "percentage": 40}]},
        )
        response = client.post(
            "/recipes/generate",
            json={
                "ingredients": {"flours": [{"pizza_flours_id": "soft_wheat_00", "percent": 100}]},
                "pre_ferment": {"type_id": type_id, "percentage": 35},
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["pre_ferment"]["components"] == [{"name": "biga", "percentage": 60}, {"name": "poolish", "percentage": 40}]
        assert body["leavening"]["percent_of_flour"] == 35
    finally:
        client.delete(f"/pre-ferment-types/{type_id}")
