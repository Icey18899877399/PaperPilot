from __future__ import annotations

import asyncio
import hashlib
import re
from typing import Any
from urllib.parse import quote_plus
from uuid import uuid4

import httpx

from app.core.config import Settings
from app.models.schemas import (
    AgentLog,
    LearningProviderStatus,
    LearningResource,
    LearningResourceType,
    LearningSearchRequest,
    LearningSearchResponse,
    PaperRecord,
)
from app.services.knowledge_base import KnowledgeBase
from app.services.llm import LLMClient, LLMServiceError
from app.services.video_catalog import VideoCatalog


class LearningService:
    """Paper-aware discovery with grounded provider results and local fallback."""

    def __init__(
        self,
        settings: Settings,
        kb: KnowledgeBase,
        llm: LLMClient,
        videos: VideoCatalog,
        logs: list[AgentLog],
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.kb = kb
        self.llm = llm
        self.videos = videos
        self.logs = logs
        self.transport = transport

    async def search(
        self,
        request: LearningSearchRequest,
        paper: PaperRecord | None,
    ) -> LearningSearchResponse:
        trace_id = uuid4().hex
        context = self._paper_context(request, paper)
        plan = await self._plan_query(request.query, context)
        interpreted_query = str(plan.get("search_query") or request.query).strip()
        concepts = self._strings(plan.get("concepts"))[:8]
        requested = set(request.resource_types)

        local_resources = self._local_resources(
            interpreted_query,
            context,
            requested,
        )
        tasks = [
            self._openalex(interpreted_query, requested),
            self._crossref(interpreted_query, requested),
            self._wikipedia(interpreted_query, requested),
            self._youtube(interpreted_query, requested),
        ]
        provider_results = await asyncio.gather(*tasks)
        resources = list(local_resources)
        statuses: list[LearningProviderStatus] = []
        for items, status in provider_results:
            resources.extend(items)
            statuses.append(status)
        resources = self._dedupe(resources)
        resources = self._apply_relevance(resources, concepts, request.query)

        narrative = await self._explain(
            request.query,
            interpreted_query,
            context,
            concepts,
            resources,
        )
        summary = str(narrative.get("summary") or "").strip()
        if not summary:
            summary = self._fallback_summary(resources, paper)
        learning_path = self._strings(narrative.get("learning_path"))[:6]
        if not learning_path:
            learning_path = concepts[:4] or ["概念背景", "方法对照", "实践或复现"]

        self.logs.append(
            AgentLog(
                trace_id=trace_id,
                agent="ExpansionLearningAgent",
                action="search-learning-resources",
                detail=(
                    f"查询“{request.query[:60]}”，整合{len(resources)}项资源；"
                    + "，".join(
                        f"{status.provider}:{'成功' if status.success else '降级'}"
                        for status in statuses
                    )
                ),
            )
        )
        return LearningSearchResponse(
            query=request.query,
            interpreted_query=interpreted_query,
            summary=summary,
            learning_path=learning_path,
            resources=resources,
            providers=statuses,
            agent_trace_id=trace_id,
        )

    def _paper_context(
        self,
        request: LearningSearchRequest,
        paper: PaperRecord | None,
    ) -> str:
        if not paper:
            return ""
        chunks = self.kb.search(paper.id, request.query, limit=4)
        body = "\n".join(
            f"第{chunk.page}页：{chunk.content[:700]}" for chunk in chunks
        )
        return f"论文文件：{paper.filename}\n{body}"[:3500]

    async def _plan_query(self, query: str, context: str) -> dict[str, Any]:
        if not self.llm.enabled:
            return {"search_query": query, "concepts": self._terms(query)[:6]}
        try:
            result = await self.llm.complete_json(
                "你是学术学习资源检索规划Agent。只输出JSON，不得编造资源或链接。",
                (
                    "根据用户问题与论文片段，生成适合学术搜索引擎的检索计划。"
                    "JSON字段：search_query（精炼的中英文检索词）、concepts（核心概念数组）、"
                    "learning_goal（学习目标）。\n"
                    f"用户问题：{query}\n论文上下文：{context or '未选择论文'}"
                ),
                max_tokens=700,
            )
            return result or {"search_query": query}
        except LLMServiceError:
            return {"search_query": query, "concepts": self._terms(query)[:6]}

    async def _explain(
        self,
        query: str,
        interpreted_query: str,
        context: str,
        concepts: list[str],
        resources: list[LearningResource],
    ) -> dict[str, Any]:
        if not self.llm.enabled:
            return {}
        candidates = [
            {
                "title": item.title,
                "type": item.resource_type,
                "source": item.source,
                "year": item.published_year,
            }
            for item in resources[:12]
        ]
        try:
            result = await self.llm.complete_json(
                (
                    "你是图书馆检索员。只能依据给定候选资源和论文上下文整理摘要，"
                    "不得补充不存在的资源或URL。语言直接、克制，避免宣传语、套话和反复使用“建议”。"
                ),
                (
                    "输出JSON：summary（80-140字中文检索摘要，说明结果覆盖什么和缺什么），"
                    "learning_path（2-4个阅读顺序数组，每项不超过20字，使用名词短语）。\n"
                    f"原问题：{query}\n检索词：{interpreted_query}\n概念：{concepts}\n"
                    f"论文上下文：{context[:1800]}\n候选资源：{candidates}"
                ),
                max_tokens=900,
            )
            return result or {}
        except LLMServiceError:
            return {}

    def _local_resources(
        self,
        query: str,
        context: str,
        requested: set[LearningResourceType],
    ) -> list[LearningResource]:
        if requested and not ({LearningResourceType.video, LearningResourceType.local} & requested):
            return []
        return [
            LearningResource(
                id=f"local-video:{video.id}",
                resource_type=LearningResourceType.video,
                title=video.title,
                description=video.description,
                source=video.source,
                url=video.file_url,
                thumbnail_url=video.cover_url,
                tags=[*video.knowledge_points, *video.keywords, *video.tags][:10],
                relevance_reason=video.recommendation_reason or "本地资源与当前问题相关",
                local=True,
            )
            for video in self.videos.recommend(query, context=context, limit=3)
        ]

    async def _openalex(
        self,
        query: str,
        requested: set[LearningResourceType],
    ) -> tuple[list[LearningResource], LearningProviderStatus]:
        if requested and LearningResourceType.paper not in requested:
            return [], LearningProviderStatus(provider="OpenAlex", enabled=False, message="未选择论文类型")
        params: dict[str, Any] = {"search": query, "per-page": 6}
        if self.settings.openalex_api_key:
            params["api_key"] = self.settings.openalex_api_key
        try:
            payload = await self._get_json("https://api.openalex.org/works", params)
            items = [self._openalex_item(item) for item in payload.get("results", [])]
            return [item for item in items if item], LearningProviderStatus(provider="OpenAlex")
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            return [], self._failed_status("OpenAlex", exc)

    async def _crossref(
        self,
        query: str,
        requested: set[LearningResourceType],
    ) -> tuple[list[LearningResource], LearningProviderStatus]:
        if requested and LearningResourceType.paper not in requested:
            return [], LearningProviderStatus(provider="Crossref", enabled=False, message="未选择论文类型")
        params: dict[str, Any] = {"query.bibliographic": query, "rows": 6}
        if self.settings.crossref_mailto:
            params["mailto"] = self.settings.crossref_mailto
        try:
            payload = await self._get_json("https://api.crossref.org/works", params)
            raw_items = payload.get("message", {}).get("items", [])
            items = [self._crossref_item(item) for item in raw_items]
            return [item for item in items if item], LearningProviderStatus(provider="Crossref")
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            return [], self._failed_status("Crossref", exc)

    async def _youtube(
        self,
        query: str,
        requested: set[LearningResourceType],
    ) -> tuple[list[LearningResource], LearningProviderStatus]:
        if requested and not ({LearningResourceType.video, LearningResourceType.course} & requested):
            return [], LearningProviderStatus(provider="YouTube", enabled=False, message="未选择视频类型")
        if not self.settings.youtube_api_key:
            resource = LearningResource(
                id=f"youtube-search:{self._digest(query)}",
                resource_type=LearningResourceType.video,
                title=f"在 YouTube 中继续检索：{query}",
                description="未配置 YouTube Data API Key，当前提供可追溯的站内搜索入口。",
                source="YouTube",
                url=f"https://www.youtube.com/results?search_query={quote_plus(query)}",
                relevance_reason="视频检索入口与当前拓展学习主题一致",
            )
            return [resource], LearningProviderStatus(
                provider="YouTube",
                enabled=False,
                success=True,
                message="未配置API Key，已提供搜索入口",
            )
        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": 6,
            "key": self.settings.youtube_api_key,
        }
        try:
            payload = await self._get_json("https://www.googleapis.com/youtube/v3/search", params)
            items = [self._youtube_item(item) for item in payload.get("items", [])]
            return [item for item in items if item], LearningProviderStatus(provider="YouTube")
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            return [], self._failed_status("YouTube", exc)

    async def _wikipedia(
        self,
        query: str,
        requested: set[LearningResourceType],
    ) -> tuple[list[LearningResource], LearningProviderStatus]:
        text_types = {
            LearningResourceType.article,
            LearningResourceType.documentation,
        }
        if requested and not (text_types & requested):
            return [], LearningProviderStatus(
                provider="Wikipedia",
                enabled=False,
                message="未选择文字资料类型",
            )
        latin = len(re.findall(r"[A-Za-z]", query))
        chinese = len(re.findall(r"[\u4e00-\u9fff]", query))
        language = "en" if latin > chinese * 2 else "zh"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": 5,
            "format": "json",
            "utf8": 1,
            "origin": "*",
        }
        try:
            payload = await self._get_json(
                f"https://{language}.wikipedia.org/w/api.php",
                params,
            )
            items = [
                self._wikipedia_item(item, language)
                for item in (payload.get("query") or {}).get("search", [])
            ]
            valid_items = [item for item in items if item]
            if valid_items:
                return valid_items, LearningProviderStatus(provider="Wikipedia")
            return [self._wikipedia_search_resource(query, language)], LearningProviderStatus(
                provider="Wikipedia",
                message="未返回直接条目，已提供站内搜索入口",
            )
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            fallback = self._wikipedia_search_resource(query, language)
            status = self._failed_status("Wikipedia", exc)
            status.message = "接口暂不可用，已提供站内搜索入口"
            return [fallback], status

    async def _get_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        headers = {"User-Agent": "PaperPilot/0.1 (expansion-learning)"}
        timeout = httpx.Timeout(self.settings.learning_search_timeout_seconds, connect=10)
        async with httpx.AsyncClient(timeout=timeout, transport=self.transport) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("provider response is not an object")
        return payload

    def _openalex_item(self, item: dict[str, Any]) -> LearningResource | None:
        title = str(item.get("display_name") or "").strip()
        if not title:
            return None
        authors = [
            str(value.get("author", {}).get("display_name"))
            for value in item.get("authorships", [])[:6]
            if value.get("author", {}).get("display_name")
        ]
        location = item.get("primary_location") or {}
        source = (location.get("source") or {}).get("display_name") or "OpenAlex"
        url = item.get("doi") or location.get("landing_page_url") or item.get("id")
        return LearningResource(
            id=f"openalex:{self._digest(str(item.get('id') or title))}",
            resource_type=LearningResourceType.paper,
            title=title,
            description=self._abstract(item.get("abstract_inverted_index")),
            source=str(source),
            url=str(url),
            authors=authors,
            published_year=item.get("publication_year"),
            tags=[str(item.get("type") or "paper")],
            relevance_reason="标题、摘要或主题词与检索内容匹配",
        )

    def _crossref_item(self, item: dict[str, Any]) -> LearningResource | None:
        raw_title = item.get("title") or []
        title = str(raw_title[0] if isinstance(raw_title, list) and raw_title else raw_title).strip()
        if not title:
            return None
        authors = [
            " ".join(filter(None, [author.get("given"), author.get("family")])).strip()
            for author in item.get("author", [])[:6]
        ]
        year = self._crossref_year(item)
        doi = str(item.get("DOI") or "").strip()
        url = f"https://doi.org/{doi}" if doi else str(item.get("URL") or "")
        return LearningResource(
            id=f"crossref:{self._digest(doi or title)}",
            resource_type=LearningResourceType.paper,
            title=title,
            description=self._strip_html(str(item.get("abstract") or "")),
            source="Crossref",
            url=url,
            authors=[author for author in authors if author],
            published_year=year,
            tags=[str(value) for value in item.get("subject", [])[:5]],
            relevance_reason="出版信息与检索内容匹配，可用于核对DOI",
        )

    def _youtube_item(self, item: dict[str, Any]) -> LearningResource | None:
        video_id = (item.get("id") or {}).get("videoId")
        snippet = item.get("snippet") or {}
        title = str(snippet.get("title") or "").strip()
        if not video_id or not title:
            return None
        thumbnails = snippet.get("thumbnails") or {}
        thumbnail = (thumbnails.get("medium") or thumbnails.get("default") or {}).get("url")
        return LearningResource(
            id=f"youtube:{video_id}",
            resource_type=LearningResourceType.video,
            title=self._strip_html(title),
            description=self._strip_html(str(snippet.get("description") or "")),
            source=str(snippet.get("channelTitle") or "YouTube"),
            url=f"https://www.youtube.com/watch?v={video_id}",
            thumbnail_url=thumbnail,
            relevance_reason="视频标题或简介与当前检索词匹配",
        )

    def _wikipedia_item(
        self,
        item: dict[str, Any],
        language: str,
    ) -> LearningResource | None:
        title = str(item.get("title") or "").strip()
        page_id = item.get("pageid")
        if not title or page_id is None:
            return None
        return LearningResource(
            id=f"wikipedia:{language}:{page_id}",
            resource_type=LearningResourceType.article,
            title=title,
            description=self._strip_html(str(item.get("snippet") or "")),
            source=f"Wikipedia ({language})",
            url=f"https://{language}.wikipedia.org/?curid={page_id}",
            relevance_reason="用于补充术语定义与基础背景，需与论文交叉核对",
        )

    def _wikipedia_search_resource(
        self,
        query: str,
        language: str,
    ) -> LearningResource:
        return LearningResource(
            id=f"wikipedia-search:{language}:{self._digest(query)}",
            resource_type=LearningResourceType.article,
            title=f"在 Wikipedia 中查找：{query}",
            description="文字资料接口暂未返回条目，可通过站内搜索继续查找概念定义和背景说明。",
            source=f"Wikipedia ({language})",
            url=(
                f"https://{language}.wikipedia.org/w/index.php?"
                f"search={quote_plus(query)}"
            ),
            relevance_reason="站内搜索词来自当前论文和问题",
        )

    def _apply_relevance(
        self,
        resources: list[LearningResource],
        concepts: list[str],
        query: str,
    ) -> list[LearningResource]:
        terms = {value.lower() for value in [*concepts, *self._terms(query)] if len(value) > 1}
        scored: list[tuple[int, LearningResource]] = []
        for resource in resources:
            haystack = f"{resource.title} {resource.description} {' '.join(resource.tags)}".lower()
            score = sum(2 for term in terms if term in haystack)
            if resource.local:
                score += 1
            scored.append((score, resource))
        scored.sort(key=lambda value: (-value[0], value[1].title.lower()))
        return [resource for _, resource in scored[:24]]

    def _dedupe(self, resources: list[LearningResource]) -> list[LearningResource]:
        seen: set[str] = set()
        result: list[LearningResource] = []
        for item in resources:
            key = self._canonical_key(item)
            if key in seen or not item.url:
                continue
            seen.add(key)
            result.append(item)
        return result

    def _canonical_key(self, item: LearningResource) -> str:
        doi_match = re.search(r"10\.\d{4,9}/\S+", item.url, re.I)
        if doi_match:
            return "doi:" + doi_match.group(0).rstrip(".,").lower()
        return re.sub(r"\W+", "", item.title).lower() or item.url.lower()

    def _failed_status(self, provider: str, exc: Exception) -> LearningProviderStatus:
        message = str(exc).strip().replace("\n", " ")[:120] or "暂时不可用"
        return LearningProviderStatus(provider=provider, success=False, message=message)

    def _fallback_summary(
        self,
        resources: list[LearningResource],
        paper: PaperRecord | None,
    ) -> str:
        prefix = f"已结合《{paper.filename}》" if paper else "已根据当前问题"
        if resources:
            return f"{prefix}整理出{len(resources)}项可追溯的拓展资料。建议先阅读高相关论文，再用视频或本地资源巩固概念。"
        return f"{prefix}完成检索，但外部来源暂未返回可用结果；可以调整关键词后重试。"

    @staticmethod
    def _crossref_year(item: dict[str, Any]) -> int | None:
        for key in ("published-print", "published-online", "issued", "created"):
            parts = (item.get(key) or {}).get("date-parts") or []
            if parts and parts[0]:
                try:
                    return int(parts[0][0])
                except (TypeError, ValueError):
                    continue
        return None

    @staticmethod
    def _abstract(index: Any) -> str:
        if not isinstance(index, dict):
            return ""
        words: list[tuple[int, str]] = []
        for word, positions in index.items():
            for position in positions if isinstance(positions, list) else []:
                if isinstance(position, int):
                    words.append((position, str(word)))
        words.sort()
        return " ".join(word for _, word in words)[:800]

    @staticmethod
    def _strip_html(value: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip()[:900]

    @staticmethod
    def _strings(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    @staticmethod
    def _terms(value: str) -> list[str]:
        return list(dict.fromkeys(re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,}|[\u4e00-\u9fff]{2,}", value)))

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
