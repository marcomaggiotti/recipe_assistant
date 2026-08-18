"""Serves the browser pages (index, flour explorer, add-product, new-recipe,
pre-ferment types, saved recipes). Static HTML/CSS/JS, no build step, no templating
engine - just a __FLOUR_SERVICE_URL__ placeholder swapped in at request time.
flour-explorer/add-flour-product's JS calls flour-service
(github.com/marcomaggiotti/flour_service) directly from the browser; new-recipe,
pre-ferment-types-page, and saved-recipes call this service's own /recipes* and
/pre-ferment-types.

Route paths deliberately avoid nesting under an existing API prefix - /recipes/new
would collide with pizza.py's GET /recipes/{item_id} ("new" would be swallowed as an
item_id), and likewise /pre-ferment-types/<anything> would collide with
pre_ferment_types.py's GET /pre-ferment-types/{type_id}. So the browser pages live at
their own sibling paths instead: /new-recipe, /pre-ferments, /saved-recipes.
"""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from ..config import get_settings

router = APIRouter(include_in_schema=False)

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def _render(template_name: str) -> str:
    html = (_TEMPLATES_DIR / template_name).read_text()
    return html.replace("__FLOUR_SERVICE_URL__", get_settings().flour_service_url)


@router.get("/", response_class=HTMLResponse)
def index() -> str:
    return _render("index.html")


@router.get("/flour-explorer", response_class=HTMLResponse)
def flour_explorer() -> str:
    return _render("flour_explorer.html")


@router.get("/flour-products/new", response_class=HTMLResponse)
def add_flour_product() -> str:
    return _render("add_flour_product.html")


@router.get("/new-recipe", response_class=HTMLResponse)
def new_recipe() -> str:
    return _render("new_recipe.html")


@router.get("/pre-ferments", response_class=HTMLResponse)
def pre_ferment_types_page() -> str:
    return _render("pre_ferment_types.html")


@router.get("/saved-recipes", response_class=HTMLResponse)
def saved_recipes() -> str:
    return _render("saved_recipes.html")
