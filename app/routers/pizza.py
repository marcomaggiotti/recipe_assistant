from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import require_api_key
from ..config import get_settings
from ..db import build_repository
from ..recipe import compute_recipe as _compute_recipe
from ..schemas import GeneratedRecipe, RecipeGenerateRequest, StyleInfo
from ..styles import build_style_store

router = APIRouter(prefix="/recipes", tags=["recipes"], dependencies=[Depends(require_api_key)])

_repo = None
_style_store = None


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


def compute_recipe(request: RecipeGenerateRequest) -> dict:
    style_defaults = get_style_store().get(request.style)
    if style_defaults is None:
        raise HTTPException(status_code=400, detail=f"unknown style '{request.style}'")
    try:
        return _compute_recipe(
            flours=[f.model_dump() for f in request.flours],
            technique=request.technique,
            style=request.style,
            style_defaults=style_defaults,
            hydration_pct=request.hydration_pct,
            salt_pct=request.salt_pct,
            oil_pct=request.oil_pct,
            yeast_pct=request.yeast_pct,
            num_balls=request.num_balls,
            ball_weight_g=request.ball_weight_g,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.get("/styles", response_model=list[StyleInfo])
def list_styles():
    return [
        StyleInfo(
            key=key,
            label=s["label"],
            author=s["author"],
            book=s["book"],
            technique=s["technique"],
            hydration_pct=s["hydration_pct"],
            salt_pct=s["salt_pct"],
            oil_pct=s["oil_pct"],
            ball_weight_g=s["ball_weight_g"],
            suggested_flours=s["suggested_flours"],
            notes=s["notes"],
        )
        for key, s in get_style_store().list().items()
    ]


@router.post("/generate", response_model=GeneratedRecipe)
def generate(request: RecipeGenerateRequest):
    """Compute a dough formula without persisting it."""
    return compute_recipe(request)


@router.post("")
def create_recipe(request: RecipeGenerateRequest):
    """Compute a dough formula and save it."""
    result = compute_recipe(request)
    name = request.name or f"{result['style_attribution']['label']} ({result['technique']})"
    return get_repo().create(name, result)


@router.get("")
def list_recipes(limit: int = Query(20, le=200), offset: int = Query(0, ge=0)):
    items, total = get_repo().list(limit, offset)
    return {"items": items, "count": total}


@router.get("/{item_id}")
def get_recipe(item_id: str):
    record = get_repo().get(item_id)
    if not record:
        raise HTTPException(status_code=404, detail="not found")
    return record


@router.delete("/{item_id}")
def delete_recipe(item_id: str):
    if not get_repo().delete(item_id):
        raise HTTPException(status_code=404, detail="not found")
    return {"deleted": True}
