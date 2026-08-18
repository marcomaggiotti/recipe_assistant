from fastapi import APIRouter, Depends

from ..agent import run_agent
from ..auth import require_api_key
from ..config import get_settings
from ..schemas import AgentChatRequest, AgentChatResponse
from .pizza import get_flour_catalog_store, get_repo
from .pre_ferment_types import get_pre_ferment_type_store

router = APIRouter(prefix="/agent", tags=["agent"], dependencies=[Depends(require_api_key)])


@router.post("/chat", response_model=AgentChatResponse)
def chat(request: AgentChatRequest):
    reply, tool_calls = run_agent(
        get_settings(), get_repo(), get_pre_ferment_type_store(), get_flour_catalog_store(),
        request.message, request.history,
    )
    return AgentChatResponse(reply=reply, tool_calls=tool_calls)
