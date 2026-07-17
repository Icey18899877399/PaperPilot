from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.sse import sse_event
from app.models.schemas import ChatRequest, ChatResponse, PaperStatus
from app.services.llm import LLMServiceError
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


@router.post("/stream")
async def chat_stream(
    payload: ChatRequest,
    request: Request,
) -> StreamingResponse:
    """US-05流式问答；保留原POST /api/chat作为兼容接口。"""
    paper = runtime.papers.get(payload.paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")
    if paper.status != PaperStatus.ready:
        raise HTTPException(status_code=409, detail="论文尚未解析完成")

    async def events():
        try:
            async for event, data in runtime.coordinator.stream_chat(
                paper_id=payload.paper_id,
                question=payload.question,
            ):
                if await request.is_disconnected():
                    return
                yield sse_event(event, data)
        except LLMServiceError as exc:
            yield sse_event("error", {"message": str(exc)})
        except Exception:
            yield sse_event("error", {"message": "论文对话生成失败，请稍后重试"})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )

