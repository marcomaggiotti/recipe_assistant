import httpx
import pytest

from app.config import Settings
from app.flours import HttpFlourCatalogStore, build_flour_catalog_store

SOFT_WHEAT_00 = {
    "id": "soft_wheat_00", "pizza_flours_id": "soft_wheat_00", "category": "wheat",
    "ash_min_pct": 0.00, "ash_max_pct": 0.55,
    "names": {"en": "Soft wheat flour type 00", "it": "Farina 00", "fr": "Farine T45", "de": "Weizenmehl 405"},
}


def _fake_response(status_code, json=None, url="http://flour-service.test/flours"):
    return httpx.Response(status_code, json=json, request=httpx.Request("GET", url))


def test_list_returns_items_from_flour_service(monkeypatch):
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["url"] = url
        return _fake_response(200, {"items": [SOFT_WHEAT_00], "count": 1})

    monkeypatch.setattr(httpx, "get", fake_get)
    store = HttpFlourCatalogStore(Settings())
    items = store.list()
    assert items == [SOFT_WHEAT_00]
    assert captured["url"] == "https://flour-service.onrender.com/flours"


def test_resolve_calls_by_name_endpoint_with_name_and_ash(monkeypatch):
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        return _fake_response(200, SOFT_WHEAT_00)

    monkeypatch.setattr(httpx, "get", fake_get)
    store = HttpFlourCatalogStore(Settings())
    result = store.resolve("Farina 00", 0.50)
    assert result == SOFT_WHEAT_00
    assert captured["url"] == "https://flour-service.onrender.com/flours/by-name"
    assert captured["params"] == {"name": "Farina 00", "ash%": 0.50}


def test_resolve_omits_ash_param_when_unset(monkeypatch):
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["params"] = params
        return _fake_response(200, SOFT_WHEAT_00)

    monkeypatch.setattr(httpx, "get", fake_get)
    store = HttpFlourCatalogStore(Settings())
    store.resolve("soft_wheat_00")
    assert captured["params"] == {"name": "soft_wheat_00"}


def test_resolve_returns_none_on_404(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _fake_response(404, {"detail": "no flour matches"}))
    store = HttpFlourCatalogStore(Settings())
    assert store.resolve("moon dust") is None


def test_raises_clear_error_when_flour_service_unreachable(monkeypatch):
    def fake_get(*a, **k):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "get", fake_get)
    store = HttpFlourCatalogStore(Settings())
    with pytest.raises(ValueError, match="flour-service"):
        store.list()


def test_raises_clear_error_on_server_error(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _fake_response(500, {"detail": "boom"}))
    store = HttpFlourCatalogStore(Settings())
    with pytest.raises(ValueError, match="flour-service"):
        store.list()


def test_sends_api_key_header_when_configured(monkeypatch):
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["headers"] = headers
        return _fake_response(200, {"items": []})

    monkeypatch.setattr(httpx, "get", fake_get)
    store = HttpFlourCatalogStore(Settings(flour_service_api_key="secret"))
    store.list()
    assert captured["headers"] == {"X-API-Key": "secret"}


def test_omits_api_key_header_when_unset(monkeypatch):
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["headers"] = headers
        return _fake_response(200, {"items": []})

    monkeypatch.setattr(httpx, "get", fake_get)
    store = HttpFlourCatalogStore(Settings())
    store.list()
    assert captured["headers"] == {}


def test_build_flour_catalog_store_always_returns_http_store():
    for backend in ("sqlite", "postgres", "cosmos"):
        store = build_flour_catalog_store(Settings(db_backend=backend))
        assert isinstance(store, HttpFlourCatalogStore)
