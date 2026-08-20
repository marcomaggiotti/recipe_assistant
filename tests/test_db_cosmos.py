"""CosmosPizzaRepository against a fake in-memory Cosmos SDK, focused on get()/delete()
staying correct even when the container's actual partition key path isn't "/id" - the
scenario that silently 404s a real, listable recipe (see class docstring in app/db.py)."""
import azure.cosmos as azure_cosmos_module
import pytest

from app.config import Settings
from app.db import CosmosPizzaRepository


class _FakeContainer:
    def __init__(self, partition_key_path="/id"):
        self._pk_path = partition_key_path
        self.items: dict[str, dict] = {}
        self.delete_calls: list[tuple[str, object]] = []

    def read(self):
        return {"partitionKey": {"paths": [self._pk_path]}}

    def create_item(self, body):
        self.items[body["id"]] = body
        return body

    def query_items(self, query, parameters=None, enable_cross_partition_query=None):
        if "WHERE c.id = @id" in query:
            target = parameters[0]["value"]
            return [v for k, v in self.items.items() if k == target]
        return sorted(self.items.values(), key=lambda r: r["created_at"], reverse=True)

    def delete_item(self, item, partition_key):
        self.delete_calls.append((item["id"], partition_key))
        del self.items[item["id"]]


class _FakeDatabase:
    def __init__(self, container):
        self._container = container

    def create_container_if_not_exists(self, id, partition_key):
        return self._container


class _FakeCosmosClient:
    def __init__(self, container, *a, **k):
        self._container = container

    def create_database_if_not_exists(self, id):
        return _FakeDatabase(self._container)


def _build_repo(monkeypatch, container) -> CosmosPizzaRepository:
    monkeypatch.setattr(azure_cosmos_module, "CosmosClient", lambda *a, **k: _FakeCosmosClient(container))
    return CosmosPizzaRepository(Settings(cosmos_endpoint="https://fake.example", cosmos_key="fake"))


def test_get_finds_a_record_when_partition_key_path_is_id(monkeypatch):
    container = _FakeContainer(partition_key_path="/id")
    repo = _build_repo(monkeypatch, container)
    created = repo.create("Friday pizza", {"technique": "direct"})
    assert repo.get(created["id"]) == created


def test_get_finds_a_record_even_when_partition_key_path_is_not_id(monkeypatch):
    # Simulates a container created out-of-band (Portal, or an earlier code version)
    # with a different partition key - the exact scenario that made a point read
    # (read_item(item=id, partition_key=id)) silently 404 a real, listable recipe.
    container = _FakeContainer(partition_key_path="/name")
    repo = _build_repo(monkeypatch, container)
    created = repo.create("Friday pizza", {"technique": "direct"})
    assert repo.get(created["id"]) == created


def test_get_returns_none_for_unknown_id(monkeypatch):
    repo = _build_repo(monkeypatch, _FakeContainer())
    assert repo.get("does-not-exist") is None


def test_delete_uses_the_record_s_actual_partition_key_value(monkeypatch):
    container = _FakeContainer(partition_key_path="/name")
    repo = _build_repo(monkeypatch, container)
    created = repo.create("Friday pizza", {"technique": "direct"})

    assert repo.delete(created["id"]) is True
    assert container.delete_calls == [(created["id"], "Friday pizza")]
    assert repo.get(created["id"]) is None


def test_delete_returns_false_for_unknown_id(monkeypatch):
    repo = _build_repo(monkeypatch, _FakeContainer())
    assert repo.delete("does-not-exist") is False


def test_list_returns_items_sorted_and_paginated(monkeypatch):
    container = _FakeContainer()
    repo = _build_repo(monkeypatch, container)
    for i in range(3):
        repo.create(f"pizza {i}", {"technique": "direct"})
    items, total = repo.list(limit=2, offset=0)
    assert total == 3
    assert len(items) == 2
