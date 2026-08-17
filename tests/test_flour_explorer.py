from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

client = TestClient(app)


def test_flour_explorer_serves_html():
    response = client.get("/flour-explorer")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Flour Explorer" in response.text


def test_flour_explorer_templates_in_the_configured_flour_service_url():
    response = client.get("/flour-explorer")
    assert get_settings().flour_service_url in response.text
    assert "__FLOUR_SERVICE_URL__" not in response.text


def test_flour_explorer_is_excluded_from_the_openapi_schema():
    schema = client.get("/openapi.json").json()
    assert "/flour-explorer" not in schema["paths"]
