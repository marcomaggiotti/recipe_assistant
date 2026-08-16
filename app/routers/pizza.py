from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import require_api_key
from ..config import get_settings
from ..db import build_repository
from ..flours import build_flour_catalog_store
from ..recipe import compute_recipe as _compute_recipe
from ..recipe import scale_recipe
from ..schemas import GeneratedRecipe, RecipeGenerateRequest, StyleAttribution, StyleInfo
from ..styles import build_style_store

router = APIRouter(prefix="/recipes", tags=["recipes"], dependencies=[Depends(require_api_key)])

_repo = None
_style_store = None
_flour_catalog_store = None


def get_repo():
    global _repo
    if _repo is None:
        _repo = build_repository(get_settings())
    return _repo


def get_style_store():
    global _style_store
    if _style_store is None:
        _style_store = build_style_store(get_settings())
    return _style_store


def get_flour_catalog_store():
    global _flour_catalog_store
    if _flour_catalog_store is None:
        _flour_catalog_store = build_flour_catalog_store(get_settings())
    return _flour_catalog_store


def compute_recipe(request: RecipeGenerateRequest) -> dict:
    """Computes the single-ball formula (baseline, num_balls=1 equivalent). Callers
    apply scale_recipe() themselves for the batch size they actually want."""
    style_defaults = get_style_store().get(request.style)
    if style_defaults is None:
        raise HTTPException(status_code=400, detail=f"unknown style '{request.style}'")

    catalog = get_flour_catalog_store()
    resolved = [(f, catalog.resolve(f.description, f.ash_pct)) for f in request.flours]
    unknown = [f.description for f, flour in resolved if flour is None]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"unknown flour type(s): {', '.join(unknown)} - see GET /recipes/flours for the allowed catalogue",
        )

    ash_warnings = [
        f"ash% {f.ash_pct} for '{f.description}' is outside {flour['id']}'s typical "
        f"{flour['ash_min_pct']}-{flour['ash_max_pct']}% range"
        for f, flour in resolved
        if f.ash_pct is not None and flour.get("ash_min_pct") is not None and not (
            flour["ash_min_pct"] <= f.ash_pct <= flour["ash_max_pct"]
        )
    ]

    try:
        result = _compute_recipe(
            flours=[f.model_dump(by_alias=True) for f in request.flours],
            technique=request.technique,
            style=request.style,
            style_defaults=style_defaults,
            hydration_pct=request.hydration_pct,
            salt_pct=request.salt_pct,
            oil_pct=request.oil_pct,
            yeast_pct=request.yeast_pct,
            ball_weight_g=request.ball_weight_g,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    result["warnings"] = ash_warnings + result["warnings"]
    return result


@router.get("/styles", response_model=list[StyleInfo])
def list_styles():
    return [
        StyleInfo(
            style=key,
            technique=s["technique"],
            hydration_pct=s["hydration_pct"],
            salt_pct=s["salt_pct"],
            oil_pct=s["oil_pct"],
            ball_weight_g=s["ball_weight_g"],
            style_attribution=StyleAttribution(
                label=s["label"],
                author=s["author"],
                book=s["book"],
                suggested_flours=s["suggested_flours"],
                notes=s["notes"],
            ),
        )
        for key, s in get_style_store().list().items()
    ]


@router.get("/flours")
def list_flours():
    """The international flour catalogue - every flours[].description in a recipe
    request must match one of these entries' id or one of its localized names/codes.
    Entries covering milled wheat refinement grades (soft wheat, rye, spelt) also carry
    ash_min_pct/ash_max_pct, the ash content (% per 100g) that grade corresponds to."""
    return {"items": get_flour_catalog_store().list()}


@router.post("/generate", response_model=GeneratedRecipe)
def generate(request: RecipeGenerateRequest, num_balls: int = Query(1, ge=1, le=200)):
    """Compute a dough formula, scaled to num_balls balls, without persisting it."""
    return scale_recipe(compute_recipe(request), num_balls)


@router.post("")
def create_recipe(request: RecipeGenerateRequest):
    """Compute the single-ball dough formula and save it - a saved recipe is always
    one ball's worth; pass ?num_balls=N to GET /recipes/{id} to scale it to a batch."""
    result = compute_recipe(request)
    name = request.name or f"{result['style_attribution']['label']} ({result['technique']})"
    record = get_repo().create(name, result)
    return scale_recipe(record, 1)


@router.get("")
def list_recipes(limit: int = Query(20, le=200), offset: int = Query(0, ge=0)):
    items, total = get_repo().list(limit, offset)
    return {"items": [scale_recipe(item, 1) for item in items], "count": total}


@router.get("/{item_id}")
def get_recipe(item_id: str, num_balls: int = Query(1, ge=1, le=200)):
    record = get_repo().get(item_id)
    if not record:
        raise HTTPException(status_code=404, detail="not found")
    return scale_recipe(record, num_balls)


@router.delete("/{item_id}")
def delete_recipe(item_id: str):
    if not get_repo().delete(item_id):
        raise HTTPException(status_code=404, detail="not found")
    return {"deleted": True}
