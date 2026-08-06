from fastapi import APIRouter

from ..config import get_settings

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok", "service": get_settings().service_name}
