from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class PaperStatus(StrEnum):
    uploaded = "uploaded"
    parsing = "parsing"
    ready = "ready"
    failed = "failed"


class PaperChunk(BaseModel):
    chunk_id: str
    paper_id: str
    page: int
    kind: str = "text"
    content: str
    resource_url: str | None = None
    bbox: list[float] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PaperRecord(BaseModel):
    id: str
    filename: str
    file_url: str
    file_sha256: str | None = None
    file_size: int = Field(default=0, ge=0)
    status: PaperStatus = PaperStatus.uploaded
    page_count: int = 0
    progress: int = Field(default=0, ge=0, le=100)
    stage: str = "等待处理"
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def normalize_legacy_progress(self) -> "PaperRecord":
        if self.status == PaperStatus.ready and self.progress < 100:
            self.progress = 100
            if self.stage == "等待处理":
                self.stage = "解析完成"
        elif self.status == PaperStatus.failed and self.stage == "等待处理":
            self.progress = 100
            self.stage = "解析失败"
        return self


class Citation(BaseModel):
    chunk_id: str
    page: int
    quote: str
    kind: str = "text"
    resource_url: str | None = None
    bbox: list[float] | None = None


class PaperContentsResponse(BaseModel):
    paper_id: str
    total: int
    counts: dict[str, int]
    items: list[PaperChunk]


class GuideResponse(BaseModel):
    paper_id: str
    title: str
    overview: str
    key_points: list[str]
    reading_questions: list[str]
    agent_trace_id: str


class MindMapSubBranch(BaseModel):
    label: str
    children: list[str] = Field(default_factory=list)


class MindMapBranch(BaseModel):
    label: str
    summary: str
    children: list[str] = Field(default_factory=list)
    subbranches: list[MindMapSubBranch] = Field(default_factory=list)


class MindMapResponse(BaseModel):
    paper_id: str
    title: str
    center: str
    branches: list[MindMapBranch]
    agent_trace_id: str


class TranslationRequest(BaseModel):
    text: str = Field(min_length=1)
    target_language: str = "中文"


class TranslationResponse(BaseModel):
    translated_text: str
    target_language: str
    agent_trace_id: str


class BilingualBlock(BaseModel):
    chunk_id: str
    page: int
    kind: str
    source_text: str
    translated_text: str
    resource_url: str | None = None
    bbox: list[float] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BilingualPageResponse(BaseModel):
    paper_id: str
    page: int
    target_language: str
    blocks: list[BilingualBlock]
    agent_trace_id: str


class ChatRequest(BaseModel):
    paper_id: str
    question: str = Field(min_length=1)


class VideoResource(BaseModel):
    id: str
    title: str
    description: str = ""
    keywords: list[str] = Field(default_factory=list)
    file_url: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    videos: list[VideoResource] = Field(default_factory=list)
    agent_trace_id: str


class AgentLog(BaseModel):
    trace_id: str
    agent: str
    action: str
    detail: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LLMStatus(BaseModel):
    provider: str
    configured: bool
    base_url: str
    model: str
    thinking: bool = False
    warning: str | None = None


class LLMTestResponse(BaseModel):
    success: bool
    provider: str
    model: str
    latency_ms: int
    message: str
