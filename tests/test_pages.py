from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

client = TestClient(app)

PAGE_ROUTES = {
    "/": "Pizza Service",
    "/flour-explorer": "Flour Explorer",
    "/flour-products/new": "Add Flour Product",
    "/new-recipe": "New Recipe",
    "/pre-ferments": "Pre-ferment Types",
    "/saved-recipes": "Recipes",
    "/compose-pizza": "Compose Pizza",
    "/toppings": "Toppings",
}

# Pages that actually reference flour-service (and so template in __FLOUR_SERVICE_URL__)
# - /pre-ferments, /saved-recipes, /compose-pizza, /toppings don't call flour-service.
FLOUR_SERVICE_PAGES = ["/", "/flour-explorer", "/flour-products/new", "/new-recipe"]

# Pages that reference topping-service (and so template in __TOPPING_SERVICE_URL__).
TOPPING_SERVICE_PAGES = ["/", "/compose-pizza", "/toppings"]


def test_all_pages_serve_html():
    for path, expected_text in PAGE_ROUTES.items():
        response = client.get(path)
        assert response.status_code == 200, path
        assert "text/html" in response.headers["content-type"], path
        assert expected_text in response.text, path


def test_flour_service_pages_template_in_the_configured_flour_service_url():
    for path in FLOUR_SERVICE_PAGES:
        response = client.get(path)
        assert get_settings().flour_service_url in response.text, path


def test_topping_service_pages_template_in_the_configured_topping_service_url():
    for path in TOPPING_SERVICE_PAGES:
        response = client.get(path)
        assert get_settings().topping_service_url in response.text, path


def test_no_page_leaks_the_raw_flour_service_url_placeholder():
    for path in PAGE_ROUTES:
        response = client.get(path)
        assert "__FLOUR_SERVICE_URL__" not in response.text, path


def test_no_page_leaks_the_raw_topping_service_url_placeholder():
    for path in PAGE_ROUTES:
        response = client.get(path)
        assert "__TOPPING_SERVICE_URL__" not in response.text, path


def test_all_pages_are_excluded_from_the_openapi_schema():
    schema = client.get("/openapi.json").json()
    for path in PAGE_ROUTES:
        assert path not in schema["paths"], path


def test_theme_css_is_served_as_a_static_asset():
    response = client.get("/static/theme.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
    assert "--accent" in response.text


def test_new_recipe_page_does_not_collide_with_get_recipe_by_id():
    # /new-recipe (not /recipes/new) is deliberate: GET /recipes/{item_id} would
    # otherwise swallow "new" as an item id and 404 before the page ever renders.
    response = client.get("/new-recipe")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

    missing_recipe = client.get("/recipes/new")
    assert missing_recipe.status_code == 404
    assert missing_recipe.headers["content-type"].startswith("application/json")


def test_pre_ferments_page_does_not_collide_with_get_pre_ferment_type_by_id():
    # /pre-ferments (not nested under /pre-ferment-types) is deliberate: GET
    # /pre-ferment-types/{type_id} would otherwise swallow any nested page path.
    response = client.get("/pre-ferments")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
