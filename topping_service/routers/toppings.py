from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import require_api_key
from ..config import get_settings
from ..schemas import Topping, ToppingCreate, ToppingList
from ..toppings import build_repository

router = APIRouter(prefix="/toppings", tags=["toppings"], dependencies=[Depends(require_api_key)])

_repo = None


def get_repo():
    global _repo
    if _repo is None:
        _repo = build_repository(get_settings())
    return _repo


@router.post("", response_model=Topping, status_code=201)
def create_topping(body: ToppingCreate):
    return get_repo().create(body.model_dump())


@router.get("", response_model=ToppingList)
def list_toppings(limit: int = Query(20, le=200), offset: int = Query(0, ge=0)):
    items, total = get_repo().list(limit, offset)
    return {"items": items, "count": total}


@router.get("/{item_id}", response_model=Topping)
def get_topping(item_id: str):
    item = get_repo().get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="not found")
    return item


@router.delete("/{item_id}")
def delete_topping(item_id: str):
    if not get_repo().delete(item_id):
        raise HTTPException(status_code=404, detail="not found")
    return {"deleted": True}
