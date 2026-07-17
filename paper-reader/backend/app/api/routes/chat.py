from fastapi import APIRouter, HTTPException

from app.models.schemas import ChatRequest, ChatResponse, PaperStatus
from app.services.runtime import runtime

router = APIRouter()


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    paper = runtime.papers.get(request.paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")
    if paper.status != PaperStatus.ready:
        raise HTTPException(status_code=409, detail="论文尚未解析完成")
    return await runtime.coordinator.run(
        "chat",
        paper_id=request.paper_id,
        question=request.question,
    )

