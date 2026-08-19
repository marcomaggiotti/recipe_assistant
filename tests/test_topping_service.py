from fastapi.testclient import TestClient

from topping_service.catalog import TOPPING_CATALOG
from topping_service.config import Settings
from topping_service.main import app
from topping_service.toppings import build_repository

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "topping-service"


def test_create_list_get_delete_roundtrip():
    create = client.post(
        "/toppings",
        json={"name": "Pepperoni", "category": "meat", "vegetarian": False, "vegan": False},
    )
    assert create.status_code == 201
    body = create.json()
    assert body["name"] == "Pepperoni"
    assert body["category"] == "meat"
    item_id = body["id"]

    listing = client.get("/toppings")
    assert listing.status_code == 200
    assert listing.json()["count"] >= 1
    assert any(item["id"] == item_id for item in listing.json()["items"])

    fetched = client.get(f"/toppings/{item_id}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Pepperoni"

    deleted = client.delete(f"/toppings/{item_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True

    missing = client.get(f"/toppings/{item_id}")
    assert missing.status_code == 404


def test_create_topping_with_optional_fields():
    create = client.post(
        "/toppings",
        json={"name": "Mushrooms", "category": "vegetable", "vegetarian": True, "vegan": True, "description": "Cremini, sliced"},
    )
    assert create.status_code == 201
    body = create.json()
    assert body["vegetarian"] is True
    assert body["vegan"] is True
    assert body["description"] == "Cremini, sliced"
    client.delete(f"/toppings/{body['id']}")


def test_create_topping_defaults_vegetarian_vegan_to_false():
    create = client.post("/toppings", json={"name": "Anchovies", "category": "meat"})
    assert create.status_code == 201
    body = create.json()
    assert body["vegetarian"] is False
    assert body["vegan"] is False
    assert body["description"] is None
    client.delete(f"/toppings/{body['id']}")


def test_rejects_unknown_category():
    response = client.post("/toppings", json={"name": "Mystery meat", "category": "not_a_category"})
    assert response.status_code == 422


def test_get_and_delete_unknown_id_returns_404():
    assert client.get("/toppings/does-not-exist").status_code == 404
    assert client.delete("/toppings/does-not-exist").status_code == 404


def test_list_pagination():
    ids = []
    for i in range(3):
        response = client.post("/toppings", json={"name": f"Topping {i}", "category": "other"})
        ids.append(response.json()["id"])
    try:
        page = client.get("/toppings", params={"limit": 2, "offset": 0})
        assert page.status_code == 200
        assert len(page.json()["items"]) == 2
        assert page.json()["count"] >= 3
    finally:
        for item_id in ids:
            client.delete(f"/toppings/{item_id}")


def test_create_composite_topping_with_components():
    create = client.post(
        "/toppings",
        json={
            "name": "Pesto", "category": "sauce", "vegetarian": True, "vegan": False,
            "components": [{"name": "basil"}, {"name": "pine nuts"}, {"name": "olive oil", "amount": "2 tbsp"}],
        },
    )
    assert create.status_code == 201
    body = create.json()
    assert body["components"] == [
        {"name": "basil", "amount": None},
        {"name": "pine nuts", "amount": None},
        {"name": "olive oil", "amount": "2 tbsp"},
    ]
    fetched = client.get(f"/toppings/{body['id']}")
    assert fetched.json()["components"][2]["amount"] == "2 tbsp"
    client.delete(f"/toppings/{body['id']}")


def test_simple_topping_has_no_components():
    create = client.post("/toppings", json={"name": "Plain cheese", "category": "cheese"})
    assert create.status_code == 201
    assert create.json()["components"] is None
    client.delete(f"/toppings/{create.json()['id']}")


def test_repository_seeds_the_topping_catalog_when_empty(tmp_path):
    settings = Settings(sqlite_path=str(tmp_path / "seed_test.db"))
    repo = build_repository(settings)
    items, total = repo.list(200, 0)
    assert total == len(TOPPING_CATALOG)
    names = {item["name"] for item in items}
    assert "Mozzarella" in names
    assert "Pesto" in names
    pesto = next(item for item in items if item["name"] == "Pesto")
    assert pesto["components"] == TOPPING_CATALOG[[t["name"] for t in TOPPING_CATALOG].index("Pesto")]["components"]


def test_repository_does_not_reseed_once_populated(tmp_path):
    settings = Settings(sqlite_path=str(tmp_path / "reseed_test.db"))
    build_repository(settings)  # first boot: seeds
    repo = build_repository(settings)  # second boot: table already has data
    _, total = repo.list(1, 0)
    assert total == len(TOPPING_CATALOG)
