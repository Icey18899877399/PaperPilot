from pathlib import Path

from fastapi.testclient import TestClient

from app.api.routes import papers as papers_route
from app.main import app
from app.models.schemas import BilingualBlock, PaperChunk, PaperRecord, PaperStatus
from app.services.knowledge_base import KnowledgeBase
from app.services.runtime import runtime
from app.services.storage import PaperStore


class FakeTranslationCoordinator:
    def __init__(self) -> None:
        self.calls = 0

    @staticmethod
    def new_trace_id() -> str:
        return "bilingual-test-trace"

    async def run(self, task: str, **payload):
        assert task == "translate-page"
        self.calls += 1
        return [
            BilingualBlock(
                chunk_id=chunk.chunk_id,
                page=chunk.page,
                kind=chunk.kind,
                source_text=chunk.content,
                translated_text=f"中文：{chunk.content}",
                resource_url=chunk.resource_url,
                bbox=chunk.bbox,
                metadata=chunk.metadata,
            )
            for chunk in payload["chunks"]
        ]


def test_bilingual_page_is_generated_and_cached(tmp_path: Path, monkeypatch) -> None:
    paper = PaperRecord(
        id="paper-bilingual",
        filename="paper.pdf",
        file_url="/media/papers/paper.pdf",
        status=PaperStatus.ready,
        page_count=1,
    )
    chunk = PaperChunk(
        chunk_id="paper-bilingual-p1-c1",
        paper_id=paper.id,
        page=1,
        kind="text",
        content="A translated paragraph.",
        bbox=[80, 100, 500, 180],
    )
    kb = KnowledgeBase()
    kb.index(paper.id, [chunk])
    coordinator = FakeTranslationCoordinator()
    monkeypatch.setattr(runtime, "papers", {paper.id: paper})
    monkeypatch.setattr(runtime, "kb", kb)
    monkeypatch.setattr(runtime, "store", PaperStore(tmp_path))
    monkeypatch.setattr(runtime, "coordinator", coordinator)

    with TestClient(app) as client:
        missing = client.get(f"/api/papers/{paper.id}/bilingual/1")
        assert missing.status_code == 404

        generated = client.post(f"/api/papers/{paper.id}/bilingual/1")
        assert generated.status_code == 200
        assert generated.json()["blocks"][0]["translated_text"].startswith("中文：")

        cached = client.post(f"/api/papers/{paper.id}/bilingual/1")
        assert cached.status_code == 200
        assert coordinator.calls == 1


def test_placeholder_table_uses_pdf_layout_text(monkeypatch) -> None:
    paper = PaperRecord(
        id="paper-table",
        filename="table.pdf",
        file_url="/media/papers/table.pdf",
        status=PaperStatus.ready,
        page_count=1,
    )
    chunk = PaperChunk(
        chunk_id="paper-table-p1-table",
        paper_id=paper.id,
        page=1,
        kind="table",
        content="[表格] 该页包含一张表格",
        metadata={"table_text": ""},
    )
    monkeypatch.setattr(
        papers_route,
        "_extract_page_layout_text",
        lambda current_paper, page: "Method | Accuracy\nOurs | 92.5",
    )

    enriched = papers_route._enrich_table_chunks(paper, [chunk])[0]

    assert "Method | Accuracy" in enriched.content
    assert enriched.metadata["table_text_source"] == "pypdf-page-layout-fallback"
    assert chunk.content == "[表格] 该页包含一张表格"
