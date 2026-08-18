from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from ..auth import require_api_key
from ..config import get_settings
from ..pre_ferments import build_pre_ferment_type_store
from ..schemas import PreFermentComponent

router = APIRouter(prefix="/pre-ferment-types", tags=["pre-ferment-types"], dependencies=[Depends(require_api_key)])

_store = None


def get_pre_ferment_type_store():
    global _store
    if _store is None:
        _store = build_pre_ferment_type_store(get_settings())
    return _store


class PreFermentTypeCreate(BaseModel):
    type_id: str = Field(
        min_length=1,
        description="Stable slug referenced by a recipe's pre_ferment.type_id, e.g. 'biga100' or "
                    "'biga80_sourdough20'.",
    )
    preferments: list[PreFermentComponent] = Field(min_length=1)

    @model_validator(mode="after")
    def _percentages_sum_to_100(self) -> "PreFermentTypeCreate":
        total = sum(p.percentage for p in self.preferments)
        if abs(total - 100.0) > 0.5:
            raise ValueError(f"preferments percentages must sum to 100 (got {total:.1f})")
        return self


def _handle_unsupported_backend(exc: ValueError):
    raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post("", status_code=201)
def create_pre_ferment_type(body: PreFermentTypeCreate):
    store = get_pre_ferment_type_store()
    try:
        if store.get(body.type_id) is not None:
            raise HTTPException(status_code=400, detail=f"pre_ferment type '{body.type_id}' already exists")
        return store.create(body.type_id, [p.model_dump() for p in body.preferments])
    except ValueError as exc:
        _handle_unsupported_backend(exc)


@router.get("")
def list_pre_ferment_types():
    try:
        return {"items": get_pre_ferment_type_store().list()}
    except ValueError as exc:
        _handle_unsupported_backend(exc)


@router.get("/{type_id}")
def get_pre_ferment_type(type_id: str):
    try:
        item = get_pre_ferment_type_store().get(type_id)
    except ValueError as exc:
        _handle_unsupported_backend(exc)
    if item is None:
        raise HTTPException(status_code=404, detail=f"unknown pre_ferment type '{type_id}'")
    return item


@router.delete("/{type_id}")
def delete_pre_ferment_type(type_id: str):
    try:
        deleted = get_pre_ferment_type_store().delete(type_id)
    except ValueError as exc:
        _handle_unsupported_backend(exc)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"unknown pre_ferment type '{type_id}'")
    return {"deleted": True}
