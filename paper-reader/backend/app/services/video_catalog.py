from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import quote, unquote
from uuid import uuid4

from app.models.schemas import VideoResource, VideoUpdateRequest


class VideoCatalogError(RuntimeError):
    """Base error for local video catalogue operations."""


class DuplicateVideoError(VideoCatalogError):
    """Raised when a duplicated file or resource record is detected."""


class VideoNotFoundError(VideoCatalogError):
    """Raised when the requested video record does not exist."""


class InvalidVideoError(VideoCatalogError):
    """Raised when an uploaded or registered video is invalid."""


class VideoCatalog:
    """Manage local MP4 metadata and perform metadata-only recommendation.

    The service deliberately does not analyse video frames, audio, subtitles or
    timestamps. Recommendation is based only on maintained metadata.
    """

    DEFAULT_COVER_NAME = "default-video-cover.svg"
    VIDEO_SUFFIXES = {".mp4"}
    COVER_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".svg"}

    def __init__(self, catalog_path: Path):
        self.catalog_path = catalog_path
        self.videos_dir = catalog_path.parent
        self.videos_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_default_cover()

    def list(self) -> list[VideoResource]:
        return [self._validate_record(item) for item in self._read_raw()]

    def get(self, video_id: str) -> VideoResource:
        for video in self.list():
            if video.id == video_id:
                return video
        raise VideoNotFoundError("视频资源不存在")

    def create(
        self,
        *,
        title: str,
        description: str = "",
        source: str = "本地维护",
        keywords: list[str] | None = None,
        tags: list[str] | None = None,
        knowledge_points: list[str] | None = None,
        video_bytes: bytes | None = None,
        original_filename: str | None = None,
        local_path: str | None = None,
        cover_bytes: bytes | None = None,
        cover_filename: str | None = None,
    ) -> VideoResource:
        title = title.strip()
        if not title:
            raise InvalidVideoError("视频标题不能为空")

        records = self.list()
        source = source.strip() or "本地维护"
        normalized_title = self._normalize_text(title)
        normalized_source = self._normalize_text(source)
        if any(
            self._normalize_text(item.title) == normalized_title
            and self._normalize_text(item.source) == normalized_source
            for item in records
        ):
            raise DuplicateVideoError("已存在标题和来源相同的视频资源记录")

        resource_id = uuid4().hex
        video_filename, file_sha256, created_file = self._prepare_video_file(
            resource_id=resource_id,
            video_bytes=video_bytes,
            original_filename=original_filename,
            local_path=local_path,
        )
        if file_sha256 and any(item.file_sha256 == file_sha256 for item in records if item.file_sha256):
            if created_file:
                self._delete_path_if_managed(video_filename)
            raise DuplicateVideoError("检测到重复MP4文件，已取消新增")

        try:
            cover_name = self._prepare_cover_file(
                resource_id=resource_id,
                cover_bytes=cover_bytes,
                cover_filename=cover_filename,
            )
        except Exception:
            if created_file:
                self._delete_path_if_managed(video_filename)
            raise
        video = VideoResource(
            id=resource_id,
            title=title,
            description=description.strip(),
            cover_url=self._media_url(cover_name),
            source=source,
            keywords=self._dedupe(keywords or []),
            tags=self._dedupe(tags or []),
            knowledge_points=self._dedupe(knowledge_points or []),
            file_url=self._media_url(video_filename),
            local_path=video_filename,
            file_sha256=file_sha256,
        )
        raw = [item.model_dump(exclude_none=True) for item in records]
        raw.append(video.model_dump(exclude_none=True))
        self._write_raw(raw)
        return video

    def update(self, video_id: str, payload: VideoUpdateRequest) -> VideoResource:
        records = self.list()
        index = next((i for i, item in enumerate(records) if item.id == video_id), None)
        if index is None:
            raise VideoNotFoundError("视频资源不存在")

        current = records[index]
        changes = {
            key: value
            for key, value in payload.model_dump(exclude_unset=True).items()
            if value is not None
        }
        if "title" in changes:
            changes["title"] = changes["title"].strip()
            if not changes["title"]:
                raise InvalidVideoError("视频标题不能为空")
        if "description" in changes:
            changes["description"] = changes["description"].strip()
        if "source" in changes:
            changes["source"] = changes["source"].strip() or "本地维护"
        for field in ("keywords", "tags", "knowledge_points"):
            if field in changes:
                changes[field] = self._dedupe(changes[field])

        candidate = current.model_copy(update=changes)
        normalized_title = self._normalize_text(candidate.title)
        normalized_source = self._normalize_text(candidate.source)
        if any(
            item.id != video_id
            and self._normalize_text(item.title) == normalized_title
            and self._normalize_text(item.source) == normalized_source
            for item in records
        ):
            raise DuplicateVideoError("已存在标题和来源相同的视频资源记录")

        records[index] = candidate
        self._write_raw([item.model_dump(exclude_none=True) for item in records])
        return candidate

    def delete(self, video_id: str, *, delete_file: bool = False) -> VideoResource:
        records = self.list()
        target = next((item for item in records if item.id == video_id), None)
        if not target:
            raise VideoNotFoundError("视频资源不存在")

        self._write_raw(
            [item.model_dump(exclude_none=True) for item in records if item.id != video_id]
        )
        if delete_file:
            self._delete_path_if_managed(target.local_path)
            cover_name = self._filename_from_media_url(target.cover_url)
            if cover_name and cover_name != self.DEFAULT_COVER_NAME:
                self._delete_path_if_managed(cover_name)
        return target

    def recommend(
        self,
        question: str,
        *,
        context: str = "",
        limit: int = 3,
    ) -> list[VideoResource]:
        haystack = self._normalize_text(f"{question} {context}")
        if not haystack:
            return []

        scored: list[tuple[int, VideoResource, list[str]]] = []
        for video in self.list():
            score = 0
            matched: list[str] = []
            fields = [
                (video.knowledge_points, 6),
                (video.keywords, 5),
                (video.tags, 4),
                ([video.title], 4),
                ([video.description], 1),
            ]
            for values, weight in fields:
                for value in values:
                    term = self._normalize_text(value)
                    if term and term in haystack:
                        score += weight
                        if len(matched) < 4 and value not in matched:
                            matched.append(value)
            if score > 0:
                scored.append((score, video, matched))

        scored.sort(key=lambda item: (-item[0], item[1].title.lower()))
        results: list[VideoResource] = []
        for _, video, matched in scored[: max(0, min(limit, 3))]:
            reason = "匹配知识点：" + "、".join(matched[:3]) if matched else "元数据与当前问题相关"
            results.append(video.model_copy(update={"recommendation_reason": reason}))
        return results

    def _prepare_video_file(
        self,
        *,
        resource_id: str,
        video_bytes: bytes | None,
        original_filename: str | None,
        local_path: str | None,
    ) -> tuple[str, str, bool]:
        if video_bytes is not None:
            if not video_bytes:
                raise InvalidVideoError("上传的MP4文件为空")
            suffix = Path(original_filename or "video.mp4").suffix.lower()
            if suffix not in self.VIDEO_SUFFIXES:
                raise InvalidVideoError("仅支持MP4视频文件")
            filename = f"{resource_id}{suffix}"
            target = self.videos_dir / filename
            target.write_bytes(video_bytes)
            return filename, hashlib.sha256(video_bytes).hexdigest(), True

        if local_path:
            source = Path(local_path).expanduser()
            if source.is_absolute() and source.exists():
                suffix = source.suffix.lower()
                if suffix not in self.VIDEO_SUFFIXES:
                    raise InvalidVideoError("仅支持MP4视频文件")
                content = source.read_bytes()
                filename = f"{resource_id}{suffix}"
                (self.videos_dir / filename).write_bytes(content)
                return filename, hashlib.sha256(content).hexdigest(), True

            candidate = self.videos_dir / Path(local_path).name
            if candidate.exists() and candidate.suffix.lower() in self.VIDEO_SUFFIXES:
                return candidate.name, self._hash_file(candidate), False
            raise InvalidVideoError("登记的本地MP4文件不存在")

        raise InvalidVideoError("请上传MP4文件，或登记后端视频目录中已有的本地MP4")

    def _prepare_cover_file(
        self,
        *,
        resource_id: str,
        cover_bytes: bytes | None,
        cover_filename: str | None,
    ) -> str:
        if not cover_bytes:
            return self.DEFAULT_COVER_NAME
        suffix = Path(cover_filename or "cover.jpg").suffix.lower()
        if suffix not in self.COVER_SUFFIXES:
            raise InvalidVideoError("封面仅支持PNG、JPG、WEBP或SVG")
        filename = f"{resource_id}-cover{suffix}"
        (self.videos_dir / filename).write_bytes(cover_bytes)
        return filename

    def _read_raw(self) -> list[dict]:
        if not self.catalog_path.exists():
            return []
        try:
            data = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise VideoCatalogError(f"视频目录读取失败：{exc}") from exc
        if not isinstance(data, list):
            raise VideoCatalogError("视频目录格式错误：根节点必须是数组")
        return data

    def _write_raw(self, data: list[dict]) -> None:
        self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
        handle, temp_name = tempfile.mkstemp(
            prefix="catalog-",
            suffix=".json.tmp",
            dir=self.catalog_path.parent,
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            Path(temp_name).replace(self.catalog_path)
        finally:
            temp = Path(temp_name)
            if temp.exists():
                temp.unlink(missing_ok=True)

    def _validate_record(self, item: dict) -> VideoResource:
        migrated = dict(item)
        migrated.setdefault("cover_url", self._media_url(self.DEFAULT_COVER_NAME))
        migrated.setdefault("source", "本地维护")
        migrated.setdefault("tags", [])
        migrated.setdefault("knowledge_points", migrated.get("keywords", []))
        migrated.setdefault("local_path", self._filename_from_media_url(migrated.get("file_url", "")))
        migrated.setdefault("file_sha256", None)
        if not migrated["file_sha256"] and migrated["local_path"]:
            candidate = self.videos_dir / Path(migrated["local_path"]).name
            if candidate.is_file():
                migrated["file_sha256"] = self._hash_file(candidate)
        return VideoResource.model_validate(migrated)

    def _ensure_default_cover(self) -> None:
        target = self.videos_dir / self.DEFAULT_COVER_NAME
        if target.exists():
            return
        target.write_text(
            """<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#0f766e"/><stop offset="1" stop-color="#1d4ed8"/></linearGradient></defs>
<rect width="640" height="360" rx="28" fill="url(#g)"/><circle cx="320" cy="180" r="70" fill="white" fill-opacity=".18"/>
<path d="M300 135l90 45-90 45z" fill="white"/><text x="32" y="326" fill="white" font-family="Arial,sans-serif" font-size="28" font-weight="700">PaperPilot Learning Video</text>
</svg>""",
            encoding="utf-8",
        )

    def _delete_path_if_managed(self, filename: str | None) -> None:
        if not filename:
            return
        safe_name = Path(filename).name
        target = self.videos_dir / safe_name
        try:
            target.resolve().relative_to(self.videos_dir.resolve())
        except ValueError:
            return
        target.unlink(missing_ok=True)

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"[\s,，;；:：\-_/()（）]+", "", value.lower())

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            clean = value.strip()
            key = clean.lower()
            if clean and key not in seen:
                seen.add(key)
                result.append(clean)
        return result

    @staticmethod
    def _media_url(filename: str) -> str:
        return f"/media/videos/{quote(filename)}"

    @staticmethod
    def _filename_from_media_url(url: str) -> str:
        return unquote(url.rsplit("/", 1)[-1]) if url else ""
