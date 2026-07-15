from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    ConversationRecord,
    MessageRecord,
    PaperStatus,
)
from app.services.runtime import runtime

router = APIRouter()


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    paper = runtime.papers.get(request.paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")
    if paper.status != PaperStatus.ready:
        raise HTTPException(status_code=409, detail="论文尚未解析完成")

    # ── load or create conversation ────────────────────────────────
    conversation_id = request.conversation_id
    conversation = None
    if conversation_id:
        conversation = runtime.store.load_conversation(conversation_id)
        if not conversation or conversation.paper_id != request.paper_id:
            # stale or mismatched conversation_id → start fresh
            conversation_id = None
            conversation = None

    if conversation is None:
        conversation_id = uuid4().hex
        conversation = ConversationRecord(
            id=conversation_id,
            paper_id=request.paper_id,
            title="",
            messages=[],
        )

    # ── build history for LLM context ──────────────────────────────
    history = [
        {"role": msg.role, "text": msg.text}
        for msg in conversation.messages
    ]

    # ── delegate to agent ──────────────────────────────────────────
    trace_id = uuid4().hex
    response = await runtime.coordinator.run(
        "chat",
        paper_id=request.paper_id,
        question=request.question,
        trace_id=trace_id,
        history=history,
    )
    response.conversation_id = conversation_id

    # ── persist the new turn ───────────────────────────────────────
    now = datetime.now(timezone.utc)
    conversation.messages.append(
        MessageRecord(
            id=uuid4().hex,
            role="user",
            text=request.question,
            created_at=now,
        )
    )
    conversation.messages.append(
        MessageRecord(
            id=uuid4().hex,
            role="assistant",
            text=response.answer,
            citations=response.citations,
            videos=response.videos,
            evidence_sufficient=response.evidence_sufficient,
            created_at=now,
        )
    )

    # auto-title from first user question
    if not conversation.title:
        conversation.title = request.question[:60]

    conversation.updated_at = now
    runtime.store.save_conversation(conversation)

    return response

