from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.agents.visual_agent import VisualAnalysisAgent
from app.core.config import get_settings
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    ConversationRecord,
    MessageRecord,
    PaperStatus,
)
from app.services.conversation_store import ConversationStore
from app.services.prompt_templates import CHAT_FORMATTING_INSTRUCTION
from app.services.runtime import runtime
from app.services.visual_prompts import is_visual_query

router = APIRouter()
_store = ConversationStore(get_settings().data_dir / "conversations")

# ── evidence check ───────────────────────────────────────────────

INSUFFICIENT_MARKER = "INSUFFICIENT_EVIDENCE"

INSUFFICIENT_RESPONSE = (
    "当前论文证据不足，无法回答该问题。论文中未包含与您问题直接相关的信息。\n"
    "建议尝试以下方式：\n"
    "1. 换一种更具体的提问方式\n"
    "2. 查阅论文其他章节\n"
    "3. 确认问题涉及的概念是否在论文中出现"
)


def _build_history_prompt(messages: list[MessageRecord]) -> str:
    """Build a concise history prefix from recent conversation turns."""
    if not messages:
        return ""
    recent = messages[-6:]
    parts = []
    for msg in recent:
        role_label = "用户" if msg.role == "user" else "AI"
        parts.append(f"【{role_label}】{msg.text}")
    return "对话历史：\n" + "\n".join(parts) + "\n\n"


def _check_evidence(answer: str) -> tuple[str, bool]:
    """Check if the LLM declared insufficient evidence."""
    if not answer:
        return INSUFFICIENT_RESPONSE, False
    if INSUFFICIENT_MARKER in answer.upper():
        return INSUFFICIENT_RESPONSE, False
    return answer, True


# ── endpoint ──────────────────────────────────────────────────────

@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    paper = runtime.papers.get(request.paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")
    if paper.status != PaperStatus.ready:
        raise HTTPException(status_code=409, detail="论文尚未解析完成")

    # ── 1. load or create conversation ───────────────────────────
    conversation_id = request.conversation_id
    conversation = None
    if conversation_id:
        conversation = _store.load_one(conversation_id)
        if not conversation or conversation.paper_id != request.paper_id:
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

    # ── 2. build enhanced question with formatting + history ─────
    history_prompt = _build_history_prompt(conversation.messages)
    enhanced_question = (
        CHAT_FORMATTING_INSTRUCTION
        + history_prompt
        + f"问题：{request.question}"
    )

    # ── 3. route: visual → VisualAnalysisAgent, else → ChatAgent ─
    trace_id = uuid4().hex
    if is_visual_query(request.question):
        agent = VisualAnalysisAgent(runtime.kb, runtime.llm)
        response = await agent.run(
            paper_id=request.paper_id,
            question=request.question,
            trace_id=trace_id,
        )
    else:
        response = await runtime.coordinator.run(
            "chat",
            paper_id=request.paper_id,
            question=enhanced_question,
            trace_id=trace_id,
        )

    # ── 4. evidence check ────────────────────────────────────────
    checked_answer, evidence_ok = _check_evidence(response.answer)
    response.answer = checked_answer
    response.evidence_sufficient = response.evidence_sufficient and evidence_ok
    response.conversation_id = conversation_id

    # ── 5. persist messages ──────────────────────────────────────
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
            evidence_sufficient=evidence_ok,
            created_at=now,
        )
    )
    if not conversation.title:
        conversation.title = request.question[:60]
    conversation.updated_at = now
    _store.save(conversation)

    return response