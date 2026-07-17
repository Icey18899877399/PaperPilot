from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import VideoUpdateRequest
from app.services.runtime import runtime
from app.services.video_catalog import DuplicateVideoError, InvalidVideoError, VideoCatalog


def test_video_catalog_manages_bilibili_links_and_search_recommendations(tmp_path) -> None:
    catalog = VideoCatalog(tmp_path / "catalog.json")
    video = catalog.create(
        title="Transformer基础讲解",
        description="介绍自注意力和编码器结构",
        source="B站搜索",
        keywords=["Transformer", "attention", "attention"],
        tags=["NLP"],
        knowledge_points=["自注意力"],
        file_url="Transformer 自注意力 教程",
    )

    assert video.local_path == ""
    assert video.file_sha256 is None
    assert video.cover_url == "/media/videos/default-video-cover.svg"
    assert video.file_url.startswith("https://search.bilibili.com/all?keyword=")
    assert video.keywords == ["Transformer", "attention"]

    recommendations = catalog.recommend("推荐相关学习视频", context="论文方法基于Transformer自注意力")
    assert recommendations[0].id == video.id
    assert recommendations[0].recommendation_reason
    assert all("bilibili.com" in item.file_url for item in recommendations)

    updated = catalog.update(
        video.id,
        VideoUpdateRequest(
            tags=["深度学习"],
            file_url="https://www.bilibili.com/video/BV1xx411c7mD/",
        ),
    )
    assert updated.tags == ["深度学习"]
    assert updated.file_url.startswith("https://www.bilibili.com/video/")

    with pytest.raises(DuplicateVideoError):
        catalog.create(
            title="Transformer基础讲解",
            source="  B站搜索  ",
            file_url="Transformer attention",
        )

    with pytest.raises(InvalidVideoError):
        catalog.create(title="外站视频", file_url="https://www.youtube.com/watch?v=demo")

    deleted = catalog.delete(video.id, delete_file=True)
    assert deleted.id == video.id
    assert catalog.list() == []


def test_video_api_crud_bilibili_link_update_and_delete(tmp_path) -> None:
    catalog = VideoCatalog(tmp_path / "catalog.json")
    with patch.object(runtime, "videos", catalog):
        client = TestClient(app)
        created = client.post(
            "/api/videos",
            data={
                "title": "注意力机制讲解",
                "description": "B站学习入口",
                "source": "B站搜索",
                "file_url": "attention Transformer",
                "keywords": "attention，Transformer",
                "tags": "NLP",
                "knowledge_points": "注意力机制",
            },
        )

        assert created.status_code == 201
        payload = created.json()
        assert payload["title"] == "注意力机制讲解"
        assert payload["keywords"] == ["attention", "Transformer"]
        assert payload["knowledge_points"] == ["注意力机制"]
        assert payload["local_path"] == ""
        assert "search.bilibili.com" in payload["file_url"]

        listed = client.get("/api/videos")
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        updated = client.put(
            f"/api/videos/{payload['id']}",
            json={
                "title": "Transformer注意力机制",
                "tags": ["深度学习"],
                "file_url": "https://www.bilibili.com/video/BV1xx411c7mD/",
            },
        )
        assert updated.status_code == 200
        assert updated.json()["title"] == "Transformer注意力机制"
        assert updated.json()["tags"] == ["深度学习"]
        assert updated.json()["file_url"].startswith("https://www.bilibili.com/video/")

        duplicate = client.post(
            "/api/videos",
            data={
                "title": "重复入口",
                "source": "B站搜索",
                "file_url": "https://www.bilibili.com/video/BV1xx411c7mD/",
            },
        )
        assert duplicate.status_code == 409

        invalid = client.post(
            "/api/videos",
            data={"title": "外站视频", "file_url": "https://www.youtube.com/watch?v=demo"},
        )
        assert invalid.status_code == 400

        deleted = client.delete(f"/api/videos/{payload['id']}")
        assert deleted.status_code == 200
        assert client.get("/api/videos").json() == []
        client.close()


@pytest.mark.asyncio
async def test_video_catalog_searches_public_bilibili_results(tmp_path) -> None:
    catalog = VideoCatalog(tmp_path / "catalog.json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.bilibili.com"
        return httpx.Response(
            200,
            json={
                "data": {
                    "result": [
                        {
                            "bvid": "BV1PublicDemo",
                            "title": "<em class=\"keyword\">Transformer</em> 论文精读",
                            "description": "公开课讲解",
                            "author": "PaperReader",
                            "duration": "18:20",
                            "pic": "//i0.hdslb.com/bfs/archive/public.jpg",
                            "tag": "Transformer,论文精读",
                        }
                    ]
                }
            },
        )

    results = await catalog.search_public(
        "Transformer 论文精读",
        limit=3,
        transport=httpx.MockTransport(handler),
    )

    assert len(results) == 1
    assert results[0].title == "Transformer 论文精读"
    assert results[0].file_url == "https://www.bilibili.com/video/BV1PublicDemo"
    assert results[0].cover_url == "https://i0.hdslb.com/bfs/archive/public.jpg"
    assert results[0].source == "B站 / PaperReader"
