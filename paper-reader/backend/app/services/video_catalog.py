from __future__ import annotations

import hashlib
import html
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import quote_plus, urlparse
from uuid import uuid4

import httpx

from app.models.schemas import VideoResource, VideoUpdateRequest


class VideoCatalogError(RuntimeError):
    """Base error for Bilibili video catalogue operations."""


class DuplicateVideoError(VideoCatalogError):
    """Raised when a duplicated resource record is detected."""


class VideoNotFoundError(VideoCatalogError):
    """Raised when the requested video record does not exist."""


class InvalidVideoError(VideoCatalogError):
    """Raised when a submitted video link or resource record is invalid."""


class VideoCatalog:
    """Manage Bilibili video links and metadata-only recommendations.

    The service stores curated Bilibili links or generated Bilibili search
    entries. It does not upload, copy, parse, or serve local video files.
    """

    DEFAULT_COVER_NAME = "default-video-cover.svg"
    DEFAULT_SOURCE = "B站搜索"
    BILIBILI_HOSTS = {
        "bilibili.com",
        "www.bilibili.com",
        "m.bilibili.com",
        "search.bilibili.com",
        "space.bilibili.com",
    }
    STOPWORDS = {
        "please",
        "recommend",
        "learning",
        "video",
        "videos",
        "paper",
        "论文",
        "视频",
        "推荐",
        "学习",
        "相关",
        "讲解",
        "什么",
        "如何",
        "课程",
        "教程",
        "资料",
        "关键",
        "概念",
    }

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
        source: str = DEFAULT_SOURCE,
        keywords: list[str] | None = None,
        tags: list[str] | None = None,
        knowledge_points: list[str] | None = None,
        file_url: str = "",
        cover_url: str = "",
    ) -> VideoResource:
        title = title.strip()
        if not title:
            raise InvalidVideoError("视频标题不能为空")

        keywords = self._dedupe(keywords or [])
        tags = self._dedupe(tags or [])
        knowledge_points = self._dedupe(knowledge_points or [])
        source = self._clean_source(source)
        resolved_url = self._resolve_bilibili_url(
            file_url,
            title=title,
            keywords=keywords,
            knowledge_points=knowledge_points,
        )
        cover_url = self._resolve_cover_url(cover_url)

        records = self.list()
        normalized_title = self._normalize_text(title)
        normalized_source = self._normalize_text(source)
        normalized_url = self._normalize_url(resolved_url)
        if any(
            self._normalize_text(item.title) == normalized_title
            and self._normalize_text(item.source) == normalized_source
            for item in records
        ):
            raise DuplicateVideoError("已存在标题和来源相同的视频资源记录")
        if any(self._normalize_url(item.file_url) == normalized_url for item in records):
            raise DuplicateVideoError("已存在相同的B站视频或搜索入口")

        video = VideoResource(
            id=uuid4().hex,
            title=title,
            description=description.strip(),
            cover_url=cover_url,
            source=source,
            keywords=keywords,
            tags=tags,
            knowledge_points=knowledge_points,
            file_url=resolved_url,
            local_path="",
            file_sha256=None,
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
            changes["source"] = self._clean_source(changes["source"])
        for field in ("keywords", "tags", "knowledge_points"):
            if field in changes:
                changes[field] = self._dedupe(changes[field])

        candidate = current.model_copy(update=changes)
        if "file_url" in changes:
            candidate = candidate.model_copy(
                update={
                    "file_url": self._resolve_bilibili_url(
                        candidate.file_url,
                        title=candidate.title,
                        keywords=candidate.keywords,
                        knowledge_points=candidate.knowledge_points,
                    )
                }
            )
        candidate = candidate.model_copy(update={"local_path": "", "file_sha256": None})

        normalized_title = self._normalize_text(candidate.title)
        normalized_source = self._normalize_text(candidate.source)
        normalized_url = self._normalize_url(candidate.file_url)
        if any(
            item.id != video_id
            and self._normalize_text(item.title) == normalized_title
            and self._normalize_text(item.source) == normalized_source
            for item in records
        ):
            raise DuplicateVideoError("已存在标题和来源相同的视频资源记录")
        if any(
            item.id != video_id and self._normalize_url(item.file_url) == normalized_url
            for item in records
        ):
            raise DuplicateVideoError("已存在相同的B站视频或搜索入口")

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
        return target

    def recommend(
        self,
        question: str,
        *,
        context: str = "",
        limit: int = 3,
    ) -> list[VideoResource]:
        max_results = max(0, min(limit, 3))
        if max_results == 0:
            return []
        haystack = self._normalize_text(f"{question} {context}")

        scored: list[tuple[int, VideoResource, list[str]]] = []
        if haystack:
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
        for _, video, matched in scored[:max_results]:
            reason = "匹配知识点：" + "、".join(matched[:3]) if matched else "元数据与当前问题相关"
            results.append(video.model_copy(update={"recommendation_reason": reason}))

        seen_urls = {self._normalize_url(item.file_url) for item in results}
        base_query = self._recommendation_query(question, context)
        search_queries = [base_query, f"{base_query} 教程", f"{base_query} 论文精读"]
        for query in self._dedupe(search_queries):
            if len(results) >= max_results:
                break
            resource = self.search_resource(
                query,
                reason="根据当前问题自动生成B站搜索入口",
            )
            normalized_url = self._normalize_url(resource.file_url)
            if normalized_url in seen_urls:
                continue
            seen_urls.add(normalized_url)
            results.append(resource)
        return results

    async def recommend_public(
        self,
        question: str,
        *,
        context: str = "",
        limit: int = 3,
        timeout_seconds: int = 12,
    ) -> list[VideoResource]:
        query = self._recommendation_query(question, context)
        try:
            results = await self.search_public(
                query,
                limit=limit,
                timeout_seconds=timeout_seconds,
            )
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            results = []
        if results:
            return results
        return self.recommend(question, context=context, limit=limit)

    async def search_public(
        self,
        query: str,
        *,
        limit: int = 6,
        timeout_seconds: int = 20,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> list[VideoResource]:
        clean_query = query.strip()
        if not clean_query:
            return []
        params = {
            "keyword": clean_query,
            "page": 1,
        }
        timeout = httpx.Timeout(timeout_seconds, connect=10)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
            ),
            "Referer": "https://search.bilibili.com/",
        }
        async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
            response = await client.get(
                "https://api.bilibili.com/x/web-interface/search/all/v2",
                params=params,
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
        results = self._public_video_results(payload)
        videos = [
            self._public_video_item(item, clean_query)
            for item in results[: max(1, min(limit, 12))]
            if isinstance(item, dict)
        ]
        return [item for item in videos if item]

    def search_resource(self, query: str, *, reason: str = "") -> VideoResource:
        query = query.strip() or "论文方法讲解"
        terms = self._terms(query)[:6] or [query[:40]]
        return VideoResource(
            id=f"bilibili-search:{self._digest(query)}",
            title=f"在 B 站搜索：{query}",
            description="打开B站搜索结果，优先查看课程讲解、论文精读、可视化推导和评论反馈较好的视频。",
            cover_url=self._media_url(self.DEFAULT_COVER_NAME),
            source=self.DEFAULT_SOURCE,
            keywords=terms,
            tags=["B站", "在线搜索"],
            knowledge_points=terms[:4],
            file_url=self.bilibili_search_url(query),
            local_path="",
            file_sha256=None,
            recommendation_reason=reason or "B站搜索词来自当前论文和问题",
        )

    @classmethod
    def bilibili_search_url(cls, query: str) -> str:
        return f"https://search.bilibili.com/all?keyword={quote_plus(query.strip())}"

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
        migrated.setdefault("id", uuid4().hex)
        migrated.setdefault("title", "B站学习视频")
        migrated.setdefault("description", "")
        migrated.setdefault("cover_url", self._media_url(self.DEFAULT_COVER_NAME))
        migrated.setdefault("source", self.DEFAULT_SOURCE)
        if migrated.get("source") == "本地维护":
            migrated["source"] = self.DEFAULT_SOURCE
        migrated.setdefault("tags", [])
        migrated.setdefault("keywords", [])
        migrated.setdefault("knowledge_points", migrated.get("keywords", []))
        migrated["file_url"] = self._resolve_bilibili_url(
            str(migrated.get("file_url") or ""),
            title=str(migrated.get("title") or ""),
            keywords=[str(value) for value in migrated.get("keywords", [])],
            knowledge_points=[str(value) for value in migrated.get("knowledge_points", [])],
        )
        migrated["local_path"] = ""
        migrated["file_sha256"] = None
        return VideoResource.model_validate(migrated)

    def _resolve_bilibili_url(
        self,
        value: str,
        *,
        title: str,
        keywords: list[str],
        knowledge_points: list[str],
    ) -> str:
        clean = value.strip()
        if not clean or clean.startswith("/media/videos/"):
            return self.bilibili_search_url(self._resource_query(title, keywords, knowledge_points))
        parsed = urlparse(clean)
        if parsed.scheme in {"http", "https"}:
            host = parsed.netloc.lower()
            if any(host == item or host.endswith(f".{item}") for item in self.BILIBILI_HOSTS):
                return clean
            raise InvalidVideoError("仅支持B站视频链接，或填写搜索词让系统生成B站搜索入口")
        return self.bilibili_search_url(clean)

    def _resolve_cover_url(self, value: str) -> str:
        clean = value.strip()
        if not clean:
            return self._media_url(self.DEFAULT_COVER_NAME)
        parsed = urlparse(clean)
        if parsed.scheme in {"http", "https"} or clean.startswith("/"):
            return clean
        raise InvalidVideoError("封面地址必须是HTTP(S)链接或站内静态资源路径")

    def _resource_query(
        self,
        title: str,
        keywords: list[str],
        knowledge_points: list[str],
    ) -> str:
        parts = [*knowledge_points[:3], *keywords[:3], title]
        return " ".join(self._dedupe([item for item in parts if item.strip()]))[:100]

    def _recommendation_query(self, question: str, context: str) -> str:
        question_terms = self._terms(question)
        context_terms = self._ranked_context_terms(context[:1800]) if context else []
        if context_terms and (self._is_generic_video_question(question) or len(question_terms) < 3):
            terms = [*context_terms, *question_terms]
        else:
            terms = [*question_terms, *context_terms]
        filtered: list[str] = []
        for term in terms:
            key = term.lower()
            if key in self.STOPWORDS or len(key) <= 1:
                continue
            filtered.append(term[:36])
        focused = " ".join(self._dedupe(filtered)[:5]).strip()
        if not focused:
            return question.strip()[:80] or "论文方法讲解"
        if re.search(r"视频|课程|教程|讲解|精读", focused, re.I):
            return focused
        return f"{focused} 教程 论文精读"

    @staticmethod
    def _is_generic_video_question(value: str) -> bool:
        return bool(
            re.search(
                r"推荐|相关|学习|视频|课程|教程|讲解|复习|关键概念|这篇论文|当前论文",
                value,
                re.I,
            )
        )

    @staticmethod
    def _ranked_context_terms(value: str) -> list[str]:
        stopwords = {
            "abstract",
            "introduction",
            "conclusion",
            "references",
            "proceedings",
            "association",
            "copyright",
            "licensed",
            "paper",
            "method",
            "results",
            "using",
            "based",
            "model",
            "models",
            "data",
            "task",
            "tasks",
            "language",
            "learning",
            "approach",
        }
        counts: dict[str, int] = {}
        for term in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", value):
            normalized = term.strip("-_").lower()
            if len(normalized) < 4 or normalized in stopwords:
                continue
            counts[normalized] = counts.get(normalized, 0) + 1
        return sorted(counts, key=lambda item: (-counts[item], -len(item), item))[:12]

    def _public_video_item(self, item: dict, query: str) -> VideoResource | None:
        bvid = str(item.get("bvid") or "").strip()
        raw_url = str(item.get("arcurl") or "").strip()
        url = f"https://www.bilibili.com/video/{bvid}" if bvid else raw_url
        if not url:
            return None
        title = self._strip_html(str(item.get("title") or "")).strip()
        if not title:
            return None
        author = self._strip_html(str(item.get("author") or "")).strip()
        duration = str(item.get("duration") or "").strip()
        description = self._strip_html(str(item.get("description") or "")).strip()
        details = [description]
        if author:
            details.append(f"UP主：{author}")
        if duration:
            details.append(f"时长：{duration}")
        tags = [
            value.strip()
            for value in re.split(r"[,，\s]+", str(item.get("tag") or ""))
            if value.strip()
        ]
        terms = self._terms(query)[:6] or [query[:40]]
        return VideoResource(
            id=f"bilibili:{bvid or self._digest(url)}",
            title=title,
            description="；".join(details)[:500],
            cover_url=self._normalize_public_image(str(item.get("pic") or "")),
            source=f"B站 / {author}" if author else "B站",
            keywords=terms,
            tags=self._dedupe([*tags[:5], "B站公开视频"]),
            knowledge_points=terms[:4],
            file_url=url,
            local_path="",
            file_sha256=None,
            recommendation_reason="根据论文内容和问题从B站公开视频搜索中匹配",
        )

    @staticmethod
    def _public_video_results(payload: dict) -> list[dict]:
        data = payload.get("data") if isinstance(payload, dict) else {}
        raw_results = (data or {}).get("result") or []
        if not isinstance(raw_results, list):
            return []
        for group in raw_results:
            if isinstance(group, dict) and group.get("result_type") == "video":
                videos = group.get("data") or []
                return videos if isinstance(videos, list) else []
        return raw_results

    @staticmethod
    def _clean_source(value: str) -> str:
        clean = value.strip()
        if not clean or clean == "本地维护":
            return VideoCatalog.DEFAULT_SOURCE
        return clean

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"[\s,，;；:：\-_/()（）]+", "", value.lower())

    @staticmethod
    def _normalize_url(value: str) -> str:
        return value.strip().rstrip("/").lower()

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
    def _terms(value: str) -> list[str]:
        return list(dict.fromkeys(re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,}|[\u4e00-\u9fff]{2,}", value)))

    @staticmethod
    def _strip_html(value: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(value))).strip()

    def _normalize_public_image(self, value: str) -> str:
        clean = value.strip()
        if clean.startswith("//"):
            return f"https:{clean}"
        if clean.startswith("http://") or clean.startswith("https://"):
            return clean
        return self._media_url(self.DEFAULT_COVER_NAME)

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _media_url(filename: str) -> str:
        return f"/media/videos/{quote_plus(filename)}"

    def _ensure_default_cover(self) -> None:
        target = self.videos_dir / self.DEFAULT_COVER_NAME
        if target.exists():
            return
        target.write_text(
            """<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#00a1d6"/><stop offset="1" stop-color="#fb7299"/></linearGradient></defs>
<rect width="640" height="360" rx="28" fill="url(#g)"/><circle cx="320" cy="180" r="70" fill="white" fill-opacity=".18"/>
<path d="M300 135l90 45-90 45z" fill="white"/><text x="32" y="326" fill="white" font-family="Arial,sans-serif" font-size="28" font-weight="700">PaperPilot Bilibili Video</text>
</svg>""",
            encoding="utf-8",
        )
