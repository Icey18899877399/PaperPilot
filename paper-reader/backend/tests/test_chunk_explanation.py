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
