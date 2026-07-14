from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import VideoUpdateRequest
from app.services.runtime import runtime
from app.services.video_catalog import DuplicateVideoError, VideoCatalog


def test_video_catalog_manages_local_mp4_and_metadata_recommendations(tmp_path) -> None:
    source_file = tmp_path / "transformer-demo.mp4"
    source_file.write_bytes(b"demo-video")

    catalog = VideoCatalog(tmp_path / "catalog.json")
    video = catalog.create(
        title="Transformer基础讲解",
        description="介绍自注意力和编码器结构",
        source="课程视频",
        keywords=["Transformer", "attention", "attention"],
        tags=["NLP"],
        knowledge_points=["自注意力"],
        local_path=source_file.name,
    )

    assert video.local_path == source_file.name
    assert video.cover_url == "/media/videos/default-video-cover.svg"
    assert video.keywords == ["Transformer", "attention"]

    recommendations = catalog.recommend("推荐相关学习视频", context="论文方法基于Transformer自注意力")
    assert [item.id for item in recommendations] == [video.id]
    assert recommendations[0].recommendation_reason

    updated = catalog.update(video.id, VideoUpdateRequest(tags=["深度学习"]))
    assert updated.tags == ["深度学习"]

    with pytest.raises(DuplicateVideoError):
        catalog.create(title="Transformer基础讲解", source="  课程视频  ", local_path=source_file.name)

    with pytest.raises(DuplicateVideoError):
        catalog.create(title="另一个视频", source="其他来源", local_path=source_file.name)
    assert source_file.exists()

    deleted = catalog.delete(video.id, delete_file=False)
    assert deleted.id == video.id
    assert source_file.exists()


def test_video_api_crud_upload_update_and_delete(tmp_path) -> None:
    catalog = VideoCatalog(tmp_path / "catalog.json")
    with patch.object(runtime, "videos", catalog):
        client = TestClient(app)
        created = client.post(
            "/api/videos",
            data={
                "title": "注意力机制讲解",
                "description": "本地MP4演示资源",
                "source": "本地维护",
                "keywords": "attention，Transformer",
                "tags": "NLP",
                "knowledge_points": "注意力机制",
            },
            files={"file": ("attention.mp4", b"demo-mp4", "video/mp4")},
        )

        assert created.status_code == 201
        payload = created.json()
        assert payload["title"] == "注意力机制讲解"
        assert payload["keywords"] == ["attention", "Transformer"]
        assert payload["knowledge_points"] == ["注意力机制"]
        assert (tmp_path / payload["local_path"]).exists()

        listed = client.get("/api/videos")
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        updated = client.put(
            f"/api/videos/{payload['id']}",
            json={"title": "Transformer注意力机制", "tags": ["深度学习"]},
        )
        assert updated.status_code == 200
        assert updated.json()["title"] == "Transformer注意力机制"
        assert updated.json()["tags"] == ["深度学习"]

        duplicate = client.post(
            "/api/videos",
            data={"title": "重复文件", "source": "本地维护"},
            files={"file": ("duplicate.mp4", b"demo-mp4", "video/mp4")},
        )
        assert duplicate.status_code == 409

        deleted = client.delete(f"/api/videos/{payload['id']}?delete_file=true")
        assert deleted.status_code == 200
        assert not (tmp_path / payload["local_path"]).exists()
        client.close()
