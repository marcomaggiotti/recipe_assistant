from fastapi import APIRouter, Depends

from ..agent import run_agent
from ..auth import require_api_key
from ..config import get_settings
from ..schemas import AgentChatRequest, AgentChatResponse
from .pizza import get_repo, get_style_store

router = APIRouter(prefix="/agent", tags=["agent"], dependencies=[Depends(require_api_key)])


@router.post("/chat", response_model=AgentChatResponse)
def chat(request: AgentChatRequest):
    reply, tool_calls = run_agent(
        get_settings(), get_repo(), get_style_store(), request.message, request.history
    )
    return AgentChatResponse(reply=reply, tool_calls=tool_calls)
