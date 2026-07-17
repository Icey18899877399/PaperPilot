from __future__ import annotations

import json
from pathlib import Path

from app.models.schemas import VideoResource


class VideoCatalog:
    """Metadata-only matching. The system does not analyze video content."""

    def __init__(self, catalog_path: Path):
        self.catalog_path = catalog_path

    def list(self) -> list[VideoResource]:
        if not self.catalog_path.exists():
            return []
        data = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        return [VideoResource.model_validate(item) for item in data]

    def recommend(self, question: str, limit: int = 3) -> list[VideoResource]:
        question_lower = question.lower()
        all_videos = self.list()
        scored = []
        for video in all_videos:
            score = sum(
                1 for keyword in video.keywords if keyword.lower() in question_lower
            )
            scored.append((score, video))
        scored.sort(key=lambda item: item[0], reverse=True)
        matched = [video for score, video in scored if score > 0][:limit]
        if matched:
            return matched
        generic_video_request = any(
            keyword in question_lower
            for keyword in ("视频", "学习资源", "video", "recommend")
        )
        return all_videos[:limit] if generic_video_request else []
