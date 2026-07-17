from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import (
    ChunkExplanationResponse,
    PaperChunk,
    PaperRecord,
    PaperStatus,
)
from app.services.knowledge_base import KnowledgeBase
from app.services.runtime import runtime
from app.services.storage import PaperStore


class FakeExplanationCoordinator:
    async def run(self, task: str, **payload):
        assert task == "explain-chunk"
        chunk = payload["chunk"]
        return ChunkExplanationResponse(
            paper_id=payload["paper_id"],
            chunk_id=chunk.chunk_id,
            page=chunk.page,
            explanation="该切片解释了核心比较关系。",
            agent_trace_id="explanation-test-trace",
        )


def test_chunk_explanation_endpoint(tmp_path: Path, monkeypatch) -> None:
    paper = PaperRecord(
        id="paper-explanation",
        filename="explanation.pdf",
        file_url="/media/papers/explanation.pdf",
        status=PaperStatus.ready,
        page_count=1,
    )
    chunk = PaperChunk(
        chunk_id="paper-explanation-p1-c1",
        paper_id=paper.id,
        page=1,
        kind="text",
        content="A comparison between the proposed method and the baseline.",
    )
    kb = KnowledgeBase()
    kb.index(paper.id, [chunk])
    monkeypatch.setattr(runtime, "papers", {paper.id: paper})
    monkeypatch.setattr(runtime, "kb", kb)
    monkeypatch.setattr(runtime, "store", PaperStore(tmp_path))
    monkeypatch.setattr(runtime, "coordinator", FakeExplanationCoordinator())

    with TestClient(app) as client:
        response = client.post(
            f"/api/papers/{paper.id}/chunks/{chunk.chunk_id}/explanation"
        )

    assert response.status_code == 200
    assert response.json()["explanation"] == "该切片解释了核心比较关系。"


class CountingCoordinator:
    def __init__(self) -> None:
        self.calls = 0

    async def run(self, task: str, **payload):
        self.calls += 1
        chunk = payload["chunk"]
        return ChunkExplanationResponse(
            paper_id=payload["paper_id"],
            chunk_id=chunk.chunk_id,
            page=chunk.page,
            explanation="缓存解释文本。",
            agent_trace_id="t",
        )


class FailingCoordinator:
    async def run(self, task: str, **payload):
        from app.services.llm import LLMServiceError

        raise LLMServiceError("模型服务不可用")


def _ready_paper_and_chunk():
    paper = PaperRecord(
        id="paper-exp2",
        filename="e.pdf",
        file_url="/media/papers/e.pdf",
        status=PaperStatus.ready,
        page_count=1,
    )
    chunk = PaperChunk(
        chunk_id="paper-exp2-m1",
        paper_id=paper.id,
        page=1,
        kind="table",
        content="模型A与基线B在准确率上的对比。",
    )
    return paper, chunk


def test_chunk_explanation_persists_and_reuses(tmp_path, monkeypatch):
    paper, chunk = _ready_paper_and_chunk()
    kb = KnowledgeBase()
    kb.index(paper.id, [chunk])
    coordinator = CountingCoordinator()
    monkeypatch.setattr(runtime, "papers", {paper.id: paper})
    monkeypatch.setattr(runtime, "kb", kb)
    monkeypatch.setattr(runtime, "store", PaperStore(tmp_path))
    monkeypatch.setattr(runtime, "coordinator", coordinator)
    monkeypatch.setattr(runtime, "llm", type("_L", (), {"enabled": True})())

    url = f"/api/papers/{paper.id}/chunks/{chunk.chunk_id}/explanation"
    with TestClient(app) as client:
        first = client.post(url)
        second = client.post(url)  # 应命中缓存，不再调用协调器

    assert first.status_code == 200 and second.status_code == 200
    assert coordinator.calls == 1


def test_chunk_explanation_returns_502_on_llm_error(tmp_path, monkeypatch):
    paper, chunk = _ready_paper_and_chunk()
    kb = KnowledgeBase()
    kb.index(paper.id, [chunk])
    monkeypatch.setattr(runtime, "papers", {paper.id: paper})
    monkeypatch.setattr(runtime, "kb", kb)
    monkeypatch.setattr(runtime, "store", PaperStore(tmp_path))
    monkeypatch.setattr(runtime, "coordinator", FailingCoordinator())
    monkeypatch.setattr(runtime, "llm", type("_L", (), {"enabled": True})())

    with TestClient(app) as client:
        response = client.post(
            f"/api/papers/{paper.id}/chunks/{chunk.chunk_id}/explanation"
        )
    # 模型服务异常应为结构化502，而非裸500
    assert response.status_code == 502


def test_build_chunk_context_pulls_related_text():
    from app.agents.paper_agent import PaperUnderstandingAgent

    kb = KnowledgeBase()
    figure = PaperChunk(
        chunk_id="p-m1",
        paper_id="p",
        page=3,
        kind="image",
        content="[图片] Figure 1 system architecture",
        metadata={"caption": "Figure 1 system architecture overview"},
    )
    text = PaperChunk(
        chunk_id="p-t1",
        paper_id="p",
        page=3,
        kind="text",
        content="Figure 1 shows the overall system architecture with three core modules. " * 3,
        metadata={"text_level": None},
    )
    kb.index("p", [figure, text])
    agent = PaperUnderstandingAgent(kb, llm=None, log_sink=[])
    context = agent._build_chunk_context("p", figure)
    # 上下文应召回讨论该图的正文，而非孤立看图题
    assert "architecture" in context.lower()


def test_explanation_prompts_differ_per_kind():
    from app.prompts.explanation import get_explanation_prompt

    table = get_explanation_prompt("table")
    equation = get_explanation_prompt("equation")
    image = get_explanation_prompt("image")
    # 每种类型标签与提示词都不同
    assert (table.label, equation.label, image.label) == ("表格", "公式", "图片")
    assert table.system_prompt != equation.system_prompt != image.system_prompt
    # 类型专属要点各有侧重
    assert "行标题" in table.system_prompt and "不存在的数字" in table.system_prompt
    assert "LaTeX" in equation.system_prompt and "未定义" in equation.system_prompt
    assert "图片信息不足" in image.system_prompt
    # 共享底座（防虚构红线）所有类型都带
    assert "不得编造" in table.system_prompt and "不得编造" in equation.system_prompt


def test_explanation_prompt_defaults_to_text_for_unknown_kind():
    from app.prompts.explanation import get_explanation_prompt

    assert get_explanation_prompt("weird-kind").label == "正文"
