from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app
from app.models.schemas import (
    LearningProviderStatus,
    LearningResource,
    LearningResourceType,
    LearningSearchRequest,
    LearningSearchResponse,
    PaperChunk,
    PaperRecord,
    PaperStatus,
)
from app.services.knowledge_base import KnowledgeBase
from app.services.learning import LearningService
from app.services.runtime import runtime
from app.services.video_catalog import VideoCatalog


class DisabledLLM:
    enabled = False


@pytest.mark.asyncio
async def test_learning_service_combines_and_deduplicates_grounded_resources(tmp_path) -> None:
    settings = Settings(backend_dir=tmp_path, youtube_api_key="")
    kb = KnowledgeBase()
    paper = PaperRecord(
        id="paper-1",
        filename="attention-paper.pdf",
        file_url="/media/papers/attention-paper.pdf",
        status=PaperStatus.ready,
        page_count=2,
    )
    kb.index(
        paper.id,
        [
            PaperChunk(
                chunk_id="chunk-1",
                paper_id=paper.id,
                page=1,
                content="The method uses Transformer attention for retrieval.",
            )
        ],
    )
    video_path = tmp_path / "data" / "videos" / "attention.mp4"
    video_path.parent.mkdir(parents=True)
    video_path.write_bytes(b"video")
    videos = VideoCatalog(video_path.parent / "catalog.json")
    videos.create(
        title="Attention入门",
        description="讲解Transformer注意力机制",
        knowledge_points=["attention"],
        local_path=video_path.name,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.openalex.org":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": "https://openalex.org/W1",
                            "doi": "https://doi.org/10.1000/attention",
                            "display_name": "Attention for Retrieval",
                            "publication_year": 2024,
                            "authorships": [{"author": {"display_name": "Ada Author"}}],
                            "primary_location": {
                                "landing_page_url": "https://example.test/openalex",
                                "source": {"display_name": "Example Journal"},
                            },
                            "type": "article",
                        }
                    ]
                },
            )
        if request.url.host == "api.crossref.org":
            return httpx.Response(
                200,
                json={
                    "message": {
                        "items": [
                            {
                                "DOI": "10.1000/attention",
                                "title": ["Attention for Retrieval"],
                                "author": [{"given": "Ada", "family": "Author"}],
                                "published-online": {"date-parts": [[2024]]},
                            }
                        ]
                    }
                },
            )
        if request.url.host in {"zh.wikipedia.org", "en.wikipedia.org"}:
            return httpx.Response(
                200,
                json={
                    "query": {
                        "search": [
                            {
                                "pageid": 42,
                                "title": "Attention (machine learning)",
                                "snippet": "An <b>attention</b> mechanism for neural networks.",
                            }
                        ]
                    }
                },
            )
        raise AssertionError(f"unexpected provider request: {request.url}")

    service = LearningService(
        settings,
        kb,
        DisabledLLM(),  # type: ignore[arg-type]
        videos,
        [],
        transport=httpx.MockTransport(handler),
    )
    result = await service.search(
        LearningSearchRequest(
            query="attention retrieval",
            paper_id=paper.id,
            resource_types=[
                LearningResourceType.paper,
                LearningResourceType.video,
                LearningResourceType.article,
            ],
        ),
        paper,
    )

    assert any(item.local for item in result.resources)
    assert sum(item.resource_type == LearningResourceType.paper for item in result.resources) == 1
    assert any(item.resource_type == LearningResourceType.article for item in result.resources)
    assert any(item.source == "YouTube" for item in result.resources)
    assert {status.provider for status in result.providers} == {
        "OpenAlex",
        "Crossref",
        "Wikipedia",
        "YouTube",
    }
    assert result.learning_path


@pytest.mark.asyncio
async def test_learning_service_keeps_text_search_available_when_wikipedia_fails(tmp_path) -> None:
    settings = Settings(backend_dir=tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host in {"zh.wikipedia.org", "en.wikipedia.org"}:
            return httpx.Response(503, text="temporarily unavailable")
        raise AssertionError(f"unexpected provider request: {request.url}")

    service = LearningService(
        settings,
        KnowledgeBase(),
        DisabledLLM(),  # type: ignore[arg-type]
        VideoCatalog(tmp_path / "videos" / "catalog.json"),
        [],
        transport=httpx.MockTransport(handler),
    )
    result = await service.search(
        LearningSearchRequest(
            query="注意力机制基础",
            resource_types=[LearningResourceType.article],
        ),
        None,
    )

    assert len(result.resources) == 1
    assert result.resources[0].resource_type == LearningResourceType.article
    assert "wikipedia.org/w/index.php" in result.resources[0].url
    wikipedia = next(status for status in result.providers if status.provider == "Wikipedia")
    assert wikipedia.success is False
    assert "搜索入口" in wikipedia.message


def test_learning_api_accepts_paper_aware_query() -> None:
    paper = PaperRecord(
        id="paper-ready",
        filename="ready.pdf",
        file_url="/media/papers/ready.pdf",
        status=PaperStatus.ready,
    )

    class StubLearning:
        async def search(self, request, selected_paper):  # noqa: ANN001
            assert request.paper_id == paper.id
            assert selected_paper.id == paper.id
            return LearningSearchResponse(
                query=request.query,
                interpreted_query="retrieval augmented generation",
                summary="先理解检索，再阅读相关工作。",
                learning_path=["检索基础", "RAG方法"],
                resources=[
                    LearningResource(
                        id="paper:1",
                        resource_type=LearningResourceType.paper,
                        title="Grounded Paper",
                        source="OpenAlex",
                        url="https://doi.org/10.1000/grounded",
                    )
                ],
                providers=[LearningProviderStatus(provider="OpenAlex")],
                agent_trace_id="trace-learning",
            )

    with (
        patch.object(runtime, "papers", {paper.id: paper}),
        patch.object(runtime, "learning", StubLearning()),
    ):
        with TestClient(app) as client:
            response = client.post(
                "/api/learning/search",
                json={
                    "query": "推荐相关学习资料",
                    "paper_id": paper.id,
                    "resource_types": ["paper", "video"],
                },
            )

    assert response.status_code == 200
    payload = response.json()
    assert payload["interpreted_query"] == "retrieval augmented generation"
    assert payload["resources"][0]["url"].startswith("https://doi.org/")
