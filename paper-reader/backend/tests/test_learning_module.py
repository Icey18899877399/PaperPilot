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
    settings = Settings(backend_dir=tmp_path)
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
    video_dir = tmp_path / "data" / "videos"
    video_dir.mkdir(parents=True)
    videos = VideoCatalog(video_dir / "catalog.json")
    videos.create(
        title="Attention入门",
        description="讲解Transformer注意力机制",
        knowledge_points=["attention"],
        file_url="attention Transformer 教程",
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
        if request.url.host == "api.bilibili.com":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "result": [
                            {
                                "bvid": "BV1attention",
                                "title": "<em class=\"keyword\">Attention</em> retrieval 视频讲解",
                                "description": "Transformer attention tutorial",
                                "author": "AI课程",
                                "duration": "12:30",
                                "pic": "//i0.hdslb.com/bfs/archive/demo.jpg",
                                "tag": "Transformer,attention",
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

    assert any(item.id.startswith("bilibili-curated:") for item in result.resources)
    assert any(item.id.startswith("bilibili:") for item in result.resources)
    assert sum(item.resource_type == LearningResourceType.paper for item in result.resources) == 1
    assert any(item.resource_type == LearningResourceType.article for item in result.resources)
    assert any(item.source.startswith("B站") for item in result.resources)
    assert any("bilibili.com/video/BV1attention" in item.url for item in result.resources)
    assert any(item.source == "YouTube" for item in result.resources)
    assert any(item.source == "MIT OpenCourseWare" for item in result.resources)
    assert {status.provider for status in result.providers} == {
        "OpenAlex",
        "Crossref",
        "Wikipedia",
        "B站",
        "公开视频",
    }
    assert result.learning_path


@pytest.mark.asyncio
async def test_learning_service_uses_paper_context_for_video_queries(tmp_path) -> None:
    settings = Settings(backend_dir=tmp_path)
    kb = KnowledgeBase()
    paper = PaperRecord(
        id="paper-video",
        filename="context-paper.pdf",
        file_url="/media/papers/context-paper.pdf",
        status=PaperStatus.ready,
        page_count=3,
    )
    kb.index(
        paper.id,
        [
            PaperChunk(
                chunk_id="chunk-video",
                paper_id=paper.id,
                page=1,
                content=(
                    "This paper studies retrieval augmented generation with contrastive "
                    "decoding. Retrieval improves grounding, and contrastive decoding "
                    "reduces hallucination in large language models."
                ),
            )
        ],
    )
    captured_keywords: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.bilibili.com":
            captured_keywords.append(str(request.url.params.get("keyword") or ""))
            return httpx.Response(
                200,
                json={
                    "data": {
                        "result": [
                            {
                                "result_type": "video",
                                "data": [
                                    {
                                        "bvid": "BV1ContextDemo",
                                        "title": "Retrieval augmented generation 论文精读",
                                        "description": "RAG and contrastive decoding tutorial",
                                        "author": "AI课程",
                                        "duration": "20:00",
                                        "pic": "//i0.hdslb.com/bfs/archive/context.jpg",
                                        "tag": "retrieval,RAG,contrastive decoding",
                                    }
                                ],
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
        VideoCatalog(tmp_path / "videos" / "catalog.json"),
        [],
        transport=httpx.MockTransport(handler),
    )
    result = await service.search(
        LearningSearchRequest(
            query="推荐和这篇论文相关的学习视频",
            paper_id=paper.id,
            resource_types=[LearningResourceType.video, LearningResourceType.course],
        ),
        paper,
    )

    assert captured_keywords
    assert "retrieval" in captured_keywords[0].lower()
    assert "contrastive" in captured_keywords[0].lower()
    assert "教程" in captured_keywords[0]
    assert any(item.url.endswith("BV1ContextDemo") for item in result.resources)
    assert any(item.source == "YouTube" for item in result.resources)
    assert any(item.source == "Coursera" for item in result.resources)


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


@pytest.mark.asyncio
async def test_learning_service_routes_paper_intent_even_when_video_scope_selected(tmp_path) -> None:
    settings = Settings(backend_dir=tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.openalex.org":
            return httpx.Response(
                200,
                json={"results": [{"id": "W1", "display_name": "A Survey of Attention"}]},
            )
        if request.url.host == "api.crossref.org":
            return httpx.Response(200, json={"message": {"items": []}})
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
            query="查找与这篇论文相关的综述和近期工作",
            resource_types=[LearningResourceType.video, LearningResourceType.course],
        ),
        None,
    )

    assert any(item.resource_type == LearningResourceType.paper for item in result.resources)
    bilibili = next(status for status in result.providers if status.provider == "B站")
    assert bilibili.enabled is False
    assert "未选择视频类型" in bilibili.message


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
