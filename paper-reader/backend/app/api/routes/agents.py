from fastapi import APIRouter, Query

from app.models.schemas import AgentLog
from app.services.runtime import runtime

router = APIRouter()


@router.get("/logs", response_model=list[AgentLog])
def list_agent_logs(limit: int = Query(default=100, ge=1, le=500)) -> list[AgentLog]:
    return runtime.logs[-limit:]

