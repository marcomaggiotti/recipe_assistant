from fastapi import APIRouter

from ..config import get_settings

router = APIRouter()


@router.get("/health")
def health():
    settings = get_settings()
    payload = {"status": "ok", "service": settings.service_name, "db_backend": settings.db_backend}
    if settings.db_backend == "cosmos":
        payload["cosmos_database"] = settings.cosmos_database
        payload["cosmos_container"] = settings.cosmos_container
        payload["cosmos_styles_container"] = settings.cosmos_styles_container
        payload["cosmos_endpoint_configured"] = bool(settings.cosmos_endpoint)
        payload["cosmos_key_configured"] = bool(settings.cosmos_key)
    return payload
