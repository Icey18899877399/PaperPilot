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
    # US-05：证据标签把章节与摘录分离，避免前端从“章节：...”正文中猜测结构。
    section: str = ""
    resource_url: str | None = None
    bbox: list[float] | None = None


class PaperContentsResponse(BaseModel):
    paper_id: str
    total: int
    counts: dict[str, int]
    items: list[PaperChunk]
    # 默认视图下被隐藏的作者区/参考文献/附录切片数（include_all=true 时为0）
    hidden: int = 0


class ChunkExplanationResponse(BaseModel):
    paper_id: str
    chunk_id: str
    page: int
    explanation: str
    agent_trace_id: str


class GuideCitation(BaseModel):
    """导读结论的原文出处（US-02：主要结论附带章节名称或页码并支持跳转）。"""

    section: str = ""
    page: int | None = None


class GuideSection(BaseModel):
    """导读单项内容；论文未提及时content为"原文未说明"（US-02验收标准）。"""

    content: str = "原文未说明"
    citations: list[GuideCitation] = Field(default_factory=list)


class GuideResponse(BaseModel):
    paper_id: str
    title: str
    overview: str
    key_points: list[str]
    reading_questions: list[str]
    # US-02九项结构化导读；带默认值以兼容历史缓存的旧版导读JSON
    one_liner: str = ""
    background: GuideSection = Field(default_factory=GuideSection)
    research_question: GuideSection = Field(default_factory=GuideSection)
    method: GuideSection = Field(default_factory=GuideSection)
    experiment: GuideSection = Field(default_factory=GuideSection)
    results: GuideSection = Field(default_factory=GuideSection)
    innovations: GuideSection = Field(default_factory=GuideSection)
    limitations: GuideSection = Field(default_factory=GuideSection)
    keywords: list[str] = Field(default_factory=list)
    # 生成方式：llm（模型生成）或 fallback（无模型/失败时的提取式降级）
    generator: str = "llm"
    agent_trace_id: str


class GuidePromptInfo(BaseModel):
    """导读提示词版本信息（供前端"导读风格"下拉框展示）。"""

    key: str
    name: str
    domain: str
    audience: str
    description: str
    is_default: bool = False


class RetrievalHit(BaseModel):
    """检索调试接口的召回条目（US-04：检索测试展示召回片段及相关度）。"""

    chunk_id: str
    page: int
    kind: str
    score: float
    section_path: list[str] = Field(default_factory=list)
    excerpt: str


class RetrievalDebugResponse(BaseModel):
    paper_id: str
    query: str
    vector_backend: str
    total_indexed: int
    items: list[RetrievalHit]


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
    cover_url: str = "/media/videos/default-video-cover.svg"
    source: str = "B站搜索"
    keywords: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    knowledge_points: list[str] = Field(default_factory=list)
    file_url: str
    local_path: str = ""
    file_sha256: str | None = None
    recommendation_reason: str | None = None


class VideoUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    source: str | None = None
    file_url: str | None = None
    keywords: list[str] | None = None
    tags: list[str] | None = None
    knowledge_points: list[str] | None = None


class LearningResourceType(StrEnum):
    paper = "paper"
    video = "video"
    article = "article"
    course = "course"
    documentation = "documentation"
    local = "local"


class LearningSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    paper_id: str | None = None
    resource_types: list[LearningResourceType] = Field(default_factory=list)


class LearningResource(BaseModel):
    id: str
    resource_type: LearningResourceType
    title: str
    description: str = ""
    source: str
    url: str
    authors: list[str] = Field(default_factory=list)
    published_year: int | None = None
    thumbnail_url: str | None = None
    tags: list[str] = Field(default_factory=list)
    relevance_reason: str = ""
    local: bool = False


class LearningProviderStatus(BaseModel):
    provider: str
    enabled: bool = True
    success: bool = True
    message: str = ""


class LearningSearchResponse(BaseModel):
    query: str
    interpreted_query: str
    summary: str
    learning_path: list[str] = Field(default_factory=list)
    resources: list[LearningResource] = Field(default_factory=list)
    providers: list[LearningProviderStatus] = Field(default_factory=list)
    agent_trace_id: str


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
