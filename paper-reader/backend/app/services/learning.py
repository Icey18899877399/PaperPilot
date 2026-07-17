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
        if not concepts:
            concepts = self._concepts_from_context(interpreted_query, context)[:8]
        video_query = self._video_search_query(interpreted_query, concepts, context)
        requested = self._normalize_requested_types(set(request.resource_types), request.query)

        local_resources = self._local_resources(
            video_query,
            context,
            requested,
        )
        tasks = [
            self._openalex(interpreted_query, requested),
            self._crossref(interpreted_query, requested),
            self._wikipedia(interpreted_query, requested),
            self._bilibili(video_query, concepts, requested),
            self._video_web(video_query, concepts, requested),
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
            return self._fallback_query_plan(query, context)
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
            return self._fallback_query_plan(query, context)

    def _fallback_query_plan(self, query: str, context: str) -> dict[str, Any]:
        query_terms = self._terms(query)
        if context and self._is_generic_learning_query(query):
            context_terms = self._ranked_context_terms(context)
            if context_terms:
                return {
                    "search_query": " ".join(context_terms[:6]),
                    "concepts": context_terms[:8],
                }
        return {"search_query": query, "concepts": query_terms[:6]}

    def _concepts_from_context(self, query: str, context: str) -> list[str]:
        ranked = self._ranked_context_terms(context) if context else []
        return self._dedupe_terms([*ranked, *self._terms(query)])[:12]

    def _video_search_query(self, query: str, concepts: list[str], context: str) -> str:
        ranked_context = self._ranked_context_terms(context) if context else []
        terms = self._dedupe_terms([*concepts, *ranked_context, *self._terms(query)])
        focused = " ".join(terms[:5]).strip() or query.strip()
        if not focused:
            return "论文方法 教程 讲解"
        if re.search(r"视频|课程|教程|讲解|精读|lecture|tutorial|course", focused, re.I):
            return focused[:120]
        return f"{focused} 教程 讲解 论文精读"[:120]

    def _english_video_query(self, query: str, concepts: list[str]) -> str:
        english_terms = [
            term
            for term in self._dedupe_terms([*concepts, *self._terms(query)])
            if re.search(r"[A-Za-z]", term)
        ]
        focused = " ".join(english_terms[:6]).strip() or query.strip()
        if re.search(r"lecture|tutorial|course|explained|seminar", focused, re.I):
            return focused[:140]
        return f"{focused} lecture tutorial course"[:140]

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
        if requested and not ({LearningResourceType.video, LearningResourceType.course} & requested):
            return []
        return [
            LearningResource(
                id=f"bilibili-curated:{video.id}",
                resource_type=LearningResourceType.video,
                title=video.title,
                description=video.description,
                source=video.source,
                url=video.file_url,
                thumbnail_url=video.cover_url,
                tags=[*video.knowledge_points, *video.keywords, *video.tags][:10],
                relevance_reason=video.recommendation_reason or "已维护的B站视频与当前问题相关",
            )
            for video in self.videos.recommend(query, context=context, limit=3)
        ]

    @staticmethod
    def _normalize_requested_types(
        requested: set[LearningResourceType],
        query: str,
    ) -> set[LearningResourceType]:
        normalized = set(requested)
        if LearningResourceType.local in normalized:
            normalized.update({LearningResourceType.video, LearningResourceType.course})
        has_video_intent = bool(re.search(r"b站|bilibili|视频|课程|教程", query, re.I))
        has_paper_intent = bool(re.search(r"论文|综述|近期工作|相关工作|survey|paper|related work", query, re.I))
        if has_paper_intent and not has_video_intent:
            normalized = {LearningResourceType.paper}
        elif has_video_intent:
            normalized.update({LearningResourceType.video, LearningResourceType.course})
        return normalized

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
            valid_items = [item for item in items if item]
            if valid_items:
                return valid_items, LearningProviderStatus(provider="OpenAlex")
            return [self._provider_search_resource("OpenAlex", query)], LearningProviderStatus(
                provider="OpenAlex",
                message="未返回直接论文，已提供搜索入口",
            )
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            status = self._failed_status("OpenAlex", exc)
            status.message = f"{status.message}；已提供搜索入口"
            return [self._provider_search_resource("OpenAlex", query)], status

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
            valid_items = [item for item in items if item]
            if valid_items:
                return valid_items, LearningProviderStatus(provider="Crossref")
            return [self._provider_search_resource("Crossref", query)], LearningProviderStatus(
                provider="Crossref",
                message="未返回直接论文，已提供搜索入口",
            )
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            status = self._failed_status("Crossref", exc)
            status.message = f"{status.message}；已提供搜索入口"
            return [self._provider_search_resource("Crossref", query)], status

    async def _bilibili(
        self,
        query: str,
        concepts: list[str],
        requested: set[LearningResourceType],
    ) -> tuple[list[LearningResource], LearningProviderStatus]:
        if requested and not ({LearningResourceType.video, LearningResourceType.course} & requested):
            return [], LearningProviderStatus(provider="B站", enabled=False, message="未选择视频类型")
        try:
            videos = await self.videos.search_public(
                query,
                limit=8,
                timeout_seconds=self.settings.learning_search_timeout_seconds,
                transport=self.transport,
            )
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            resources = self._bilibili_search_fallback(query, concepts)
            status = self._failed_status("B站", exc)
            status.message = "B站公开视频搜索暂不可用，已提供站内搜索入口"
            return resources, status

        videos = self._filter_bilibili_videos(videos, query, concepts)
        if not videos:
            return self._bilibili_search_fallback(query, concepts), LearningProviderStatus(
                provider="B站",
                message="未返回高相关具体视频，已提供站内搜索入口",
            )
        return [
            LearningResource(
                id=video.id,
                resource_type=LearningResourceType.video,
                title=video.title,
                description=video.description,
                source=video.source,
                url=video.file_url,
                thumbnail_url=video.cover_url,
                tags=[*video.knowledge_points, *video.keywords, *video.tags][:10],
                relevance_reason="根据论文内容和问题从B站公开视频搜索中匹配",
            )
            for video in videos
        ], LearningProviderStatus(provider="B站", message="已搜索B站公开视频")

    async def _video_web(
        self,
        query: str,
        concepts: list[str],
        requested: set[LearningResourceType],
    ) -> tuple[list[LearningResource], LearningProviderStatus]:
        if requested and not ({LearningResourceType.video, LearningResourceType.course} & requested):
            return [], LearningProviderStatus(provider="公开视频", enabled=False, message="未选择视频类型")
        return self._external_video_resources(query, concepts), LearningProviderStatus(
            provider="公开视频",
            message="已提供其他公开视频和课程搜索入口",
        )

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

    def _provider_search_resource(self, provider: str, query: str) -> LearningResource:
        if provider == "OpenAlex":
            url = f"https://openalex.org/works?search={quote_plus(query)}"
        elif provider == "Crossref":
            url = f"https://search.crossref.org/?q={quote_plus(query)}"
        else:
            url = f"https://www.google.com/search?q={quote_plus(query)}"
        return LearningResource(
            id=f"{provider.lower()}-search:{self._digest(query)}",
            resource_type=LearningResourceType.paper,
            title=f"在 {provider} 中继续检索：{query}",
            description="外部论文接口暂未返回可直接展示的记录，可打开来源站点继续检索相关论文、综述和近期工作。",
            source=provider,
            url=url,
            relevance_reason="搜索词来自当前论文内容和用户问题",
        )

    def _external_video_resources(
        self,
        query: str,
        concepts: list[str],
    ) -> list[LearningResource]:
        display_query = re.sub(r"\s+", " ", query).strip()[:90] or "论文方法"
        english_query = self._english_video_query(query, concepts)
        course_query = " ".join(
            self._dedupe_terms(
                [term for term in [*concepts, *self._terms(query)] if re.search(r"[A-Za-z]", term)]
            )[:6]
        ) or display_query
        shared_tags = self._dedupe_terms([*concepts[:6], "视频", "课程"])
        return [
            LearningResource(
                id=f"youtube-search:{self._digest(english_query)}",
                resource_type=LearningResourceType.video,
                title=f"在 YouTube 搜索：{display_query}",
                description="打开YouTube检索与论文核心概念相关的lecture、tutorial、paper reading或seminar视频。",
                source="YouTube",
                url=f"https://www.youtube.com/results?search_query={quote_plus(english_query)}",
                tags=shared_tags,
                relevance_reason="根据论文片段提炼的关键词生成公开视频检索入口",
            ),
            LearningResource(
                id=f"mit-ocw-search:{self._digest(course_query)}",
                resource_type=LearningResourceType.course,
                title=f"在 MIT OpenCourseWare 搜索：{course_query[:90]}",
                description="适合查找系统课程、课堂讲义和公开视频课程，用来补齐论文涉及的基础知识。",
                source="MIT OpenCourseWare",
                url=f"https://ocw.mit.edu/search/?q={quote_plus(course_query)}",
                tags=shared_tags,
                relevance_reason="课程站点检索词来自论文核心概念",
            ),
            LearningResource(
                id=f"coursera-search:{self._digest(course_query)}",
                resource_type=LearningResourceType.course,
                title=f"在 Coursera 搜索：{course_query[:90]}",
                description="可继续筛选机器学习、NLP、数据科学等方向的公开视频课程和专项课程。",
                source="Coursera",
                url=f"https://www.coursera.org/search?query={quote_plus(course_query)}",
                tags=shared_tags,
                relevance_reason="课程搜索词根据论文主题自动生成",
            ),
            LearningResource(
                id=f"stanford-online-search:{self._digest(course_query)}",
                resource_type=LearningResourceType.course,
                title=f"在 Stanford Online 搜索：{course_query[:90]}",
                description="用于补充高校公开课、短课程和专题学习资源，适合先建立背景再读论文细节。",
                source="Stanford Online",
                url=f"https://online.stanford.edu/search-catalog?type=All&keywords={quote_plus(course_query)}",
                tags=shared_tags,
                relevance_reason="外部课程入口围绕论文关键词生成",
            ),
        ]

    def _filter_bilibili_videos(
        self,
        videos: list[Any],
        query: str,
        concepts: list[str],
    ) -> list[Any]:
        terms = self._relevance_terms(query, concepts)
        if not terms:
            return videos[:6]
        scored: list[tuple[int, Any]] = []
        for video in videos:
            title = str(getattr(video, "title", "") or "").lower()
            haystack = " ".join(
                [
                    title,
                    str(getattr(video, "description", "") or "").lower(),
                    " ".join(str(value).lower() for value in getattr(video, "tags", []) or []),
                ]
            )
            score = 0
            for term in terms:
                if term in title:
                    score += 3
                elif term in haystack:
                    score += 1
            if score > 0:
                scored.append((score, video))
        scored.sort(key=lambda item: (-item[0], str(getattr(item[1], "title", "")).lower()))
        return [video for _, video in scored[:8]]

    def _bilibili_search_fallback(
        self,
        query: str,
        concepts: list[str],
    ) -> list[LearningResource]:
        variants = self._expanded_bilibili_queries(query, concepts)
        return [
            LearningResource(
                id=f"bilibili-search:{self._digest(value)}",
                resource_type=LearningResourceType.video,
                title=f"在 B 站搜索：{value}",
                description="打开B站搜索结果后可按课程讲解、论文精读、可视化推导继续筛选。",
                source="B站",
                url=f"https://search.bilibili.com/all?keyword={quote_plus(value)}",
                tags=["B站", "视频", "课程"],
                relevance_reason="B站搜索词来自当前论文和拓展学习问题",
            )
            for value in variants[:3]
        ]

    def _expanded_bilibili_queries(self, query: str, concepts: list[str]) -> list[str]:
        terms = self._relevance_terms(query, concepts)
        translated = self._translated_learning_terms(terms)
        variants = [query]
        if translated:
            variants.append(f"{' '.join(translated[:6])} 教程 讲解")
        if terms:
            variants.append(f"{' '.join(terms[:5])} tutorial lecture")
        variants.append(f"{query} 论文精读")
        return self._dedupe_terms(variants)

    @staticmethod
    def _translated_learning_terms(terms: list[str]) -> list[str]:
        translations = {
            "forecast": "预测",
            "forecasting": "预测",
            "event": "事件",
            "events": "事件",
            "retrieval": "检索",
            "augmented": "增强",
            "generation": "生成",
            "contrastive": "对比",
            "decoding": "解码",
            "transformer": "Transformer",
            "attention": "注意力",
            "language": "语言模型",
            "graph": "图",
            "knowledge": "知识图谱",
            "neural": "神经网络",
            "network": "网络",
            "classification": "分类",
            "detection": "检测",
            "segmentation": "分割",
            "diffusion": "扩散",
            "reinforcement": "强化学习",
            "series": "时间序列",
            "prediction": "预测",
        }
        values: list[str] = []
        lowered = [term.lower() for term in terms]
        if "time" in lowered and "series" in lowered:
            values.append("时间序列")
        for term in lowered:
            if term in translations:
                values.append(translations[term])
        return list(dict.fromkeys(values))

    def _apply_relevance(
        self,
        resources: list[LearningResource],
        concepts: list[str],
        query: str,
    ) -> list[LearningResource]:
        terms = set(self._relevance_terms(query, concepts))
        scored: list[tuple[int, LearningResource]] = []
        for resource in resources:
            haystack = f"{resource.title} {resource.description} {' '.join(resource.tags)}".lower()
            score = sum(2 for term in terms if term in haystack)
            if resource.local:
                score += 1
            if resource.id.startswith("bilibili:"):
                score += 4
            scored.append((score, resource))
        scored.sort(key=lambda value: (-value[0], value[1].title.lower()))
        return [resource for _, resource in scored[:24]]

    @staticmethod
    def _relevance_terms(query: str, concepts: list[str]) -> list[str]:
        stopwords = {
            "abstract",
            "paper",
            "method",
            "methods",
            "model",
            "models",
            "data",
            "task",
            "tasks",
            "result",
            "results",
            "using",
            "based",
            "from",
            "with",
            "without",
            "into",
            "onto",
            "over",
            "under",
            "this",
            "that",
            "these",
            "those",
            "their",
            "there",
            "where",
            "which",
            "whose",
            "when",
            "then",
            "than",
            "also",
            "have",
            "has",
            "had",
            "been",
            "were",
            "will",
            "would",
            "could",
            "should",
            "教程",
            "讲解",
            "视频",
            "课程",
            "论文",
            "精读",
            "相关",
            "推荐",
            "学习",
        }
        terms: list[str] = []
        for term in LearningService._dedupe_terms([*concepts, *LearningService._terms(query)]):
            normalized = term.strip("-_").lower()
            if not normalized or normalized in stopwords:
                continue
            if re.search(r"[A-Za-z]", normalized) and len(normalized) < 4:
                continue
            terms.append(normalized)
        return terms[:12]

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
            return f"{prefix}整理出{len(resources)}项可追溯的拓展资料。建议先阅读高相关论文，再用公开视频或课程巩固概念。"
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
    def _is_generic_learning_query(value: str) -> bool:
        return bool(
            re.search(
                r"这篇论文|当前论文|相关|综述|近期工作|前置知识|学习视频|视频|课程|教程|related|survey|recent work",
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
            "from",
            "with",
            "without",
            "into",
            "onto",
            "over",
            "under",
            "this",
            "that",
            "these",
            "those",
            "their",
            "there",
            "where",
            "which",
            "whose",
            "when",
            "then",
            "than",
            "also",
            "have",
            "has",
            "had",
            "been",
            "were",
            "will",
            "would",
            "could",
            "should",
        }
        counts: dict[str, int] = {}
        for term in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", value):
            normalized = term.strip("-_").lower()
            if len(normalized) < 4 or normalized in stopwords:
                continue
            counts[normalized] = counts.get(normalized, 0) + 1
        ranked = sorted(
            counts,
            key=lambda item: (-counts[item], -len(item), item),
        )
        return ranked[:12]

    @staticmethod
    def _dedupe_terms(values: list[str]) -> list[str]:
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
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
