import pytest

from app.agents.chat_agent import ChatAgent
from app.models.schemas import PaperChunk


class StubKnowledgeBase:
    chunk = PaperChunk(
        chunk_id="rag-1",
        paper_id="paper-1",
        page=6,
        kind="text",
        content="章节：3.3 Results\n模型在测试集上取得了更高的F1分数。",
        metadata={"section_path": ["3 Experiments", "3.3 Results"]},
    )

    def search(self, paper_id: str, question: str, limit: int = 6):
        del paper_id, question, limit
        return [self.chunk]

    def retrieval_chunks(self, paper_id: str):
        del paper_id
        return [self.chunk]


class StubLLM:
    async def complete(self, system: str, user: str):
        del system, user
        return "模型取得了**更高的F1分数**（第6页）。"

    async def complete_stream(self, system: str, user: str):
        del system, user
        for item in ("模型取得了", "**更高的F1分数**", "（第6页）。"):
            yield item


class StubVideos:
    def recommend(self, question: str, *, context: str = ""):
        del question, context
        return []


@pytest.mark.asyncio
async def test_chat_stream_returns_deltas_then_structured_evidence():
    agent = ChatAgent(StubKnowledgeBase(), StubLLM(), StubVideos(), [])
    events = [
        event
        async for event in agent.stream(
            paper_id="paper-1",
            question="主要结果是什么？",
            trace_id="trace-1",
        )
    ]

    assert [name for name, _ in events].count("delta") == 3
    name, payload = events[-1]
    assert name == "complete"
    assert payload["answer"].startswith("模型取得了")
    citation = payload["citations"][0]
    assert citation["section"] == "3 Experiments > 3.3 Results"
    assert citation["quote"].startswith("模型在测试集")
    assert "章节：" not in citation["quote"]
