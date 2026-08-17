"""Serves the flour-catalogue browser page. Static HTML/CSS/JS, no build step - the
page's JS calls flour-service (github.com/marcomaggiotti/flour_service) directly from
the browser, so this route just serves the file with its API base URL templated in."""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from ..config import get_settings

router = APIRouter()

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "static" / "flour_explorer.html"


@router.get("/flour-explorer", response_class=HTMLResponse, include_in_schema=False)
def flour_explorer() -> str:
    html = _TEMPLATE_PATH.read_text()
    return html.replace("__FLOUR_SERVICE_URL__", get_settings().flour_service_url)
