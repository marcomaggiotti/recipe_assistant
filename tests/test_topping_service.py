from fastapi.testclient import TestClient

from topping_service.main import app

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
