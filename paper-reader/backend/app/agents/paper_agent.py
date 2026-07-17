from __future__ import annotations

import re
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from typing import Any

from app.agents.base import BaseAgent
from app.models.schemas import (
    ChunkExplanationResponse,
    GuideCitation,
    GuideResponse,
    GuideSection,
    MindMapBranch,
    MindMapResponse,
    MindMapSubBranch,
    PaperChunk,
)
from pathlib import Path

from app.prompts.explanation import get_explanation_prompt, get_vision_prompt
from app.prompts.guide import get_guide_prompt
from app.services.knowledge_base import KnowledgeBase
from app.services.llm import LLMClient, LLMServiceError
from app.services.vision import VisionClient, VisionServiceError


class PaperUnderstandingAgent(BaseAgent):
    name = "paper-understanding-agent"

    # US-02九项结构化导读的字段与中文名对照
    GUIDE_SECTION_FIELDS = (
        ("background", "研究背景"),
        ("research_question", "研究问题"),
        ("method", "核心方法"),
        ("experiment", "实验设计"),
        ("results", "主要结果"),
        ("innovations", "创新点"),
        ("limitations", "局限性"),
    )

    # 承载 limitations/结论字段证据的章节关键词。这些章节通常在论文靠后，
    # 采样与上下文截断都会偏向丢弃，因此单独识别并优先保护（US-02 局限性字段）
    LIMITATION_SECTION_KEYWORDS = (
        "limitation",
        "discussion",
        "future work",
        "future direction",
        "conclusion",
        "concluding",
        "局限",
        "不足",
        "讨论",
        "结论",
        "未来工作",
        "展望",
    )

    def __init__(
        self,
        kb: KnowledgeBase,
        llm: LLMClient,
        log_sink,
        vision: VisionClient | None = None,
        assets_dir: Path | None = None,
    ):
        super().__init__(log_sink)
        self.kb = kb
        self.llm = llm
        # 视觉模型与图片资源目录：图片/图表切片走多模态时使用（US-07）
        self.vision = vision
        self.assets_dir = assets_dir

    async def run(
        self,
        paper_id: str,
        filename: str,
        trace_id: str,
        prompt_key: str | None = None,
        on_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> GuideResponse:
        started = time.perf_counter()
        chunks = self.kb.retrieval_chunks(paper_id)
        # 基于US-02优化：上下文从"论文开头8个切片"改为全篇分节采样，
        # 保证结果、创新点、局限性等靠后章节也进入模型上下文
        sampled = self._sample_guide_chunks(chunks)
        max_page = max((chunk.page for chunk in chunks), default=1)
        limitation_hits = sum(
            1 for chunk in sampled if self._is_limitation_section(chunk)
        )
        self.log(
            trace_id,
            "read-paper",
            f"读取{len(chunks)}个检索切片，采样{len(sampled)}个"
            f"（含{limitation_hits}个局限/结论切片）用于导读",
        )
        # 预算上调到26000：采样上限26个切片、每个截断到900字符，需足够容纳全部
        # 靠后章节，避免拼接后的字符串截断再次把局限/结论切片丢在末尾（US-02修复）
        context = "\n\n".join(
            f"[{self._chunk_section(chunk)}·第{chunk.page}页] {chunk.content[:900]}"
            for chunk in sampled
        )[:26000]

        # 基于US-02优化：提示词由app/prompts/guide.py集中管理，支持按论文
        # 领域与受众切换版本；日志记录版本号（对齐US-12提示词版本要求）
        prompt = get_guide_prompt(prompt_key)
        self.log(trace_id, "select-prompt", f"使用导读提示词版本：{prompt.key}")
        generated: dict[str, Any] | None = None
        # 基于US-02异常兜底：输出被截断或JSON格式异常时重试1次，仍失败才进入
        # 提取式降级；模型服务异常不应让导读接口500
        for attempt in range(2):
            try:
                user_prompt = (
                    f"论文文件名：{filename}\n\n"
                    f"论文片段（[章节·页码] 内容）：\n{context}"
                )
                # US-02流式体验：严格JSON不向页面暴露半成品；模型token仅用于
                # SSE进度反馈，最终仍校验完整JSON，避免字段残缺或引用错位。
                if on_delta is not None and self.llm.enabled:
                    generated = await self.llm.complete_json_stream(
                        prompt.system_prompt,
                        user_prompt,
                        max_tokens=4096,
                        on_delta=on_delta,
                    )
                else:
                    generated = await self.llm.complete_json(
                        prompt.system_prompt,
                        user_prompt,
                        max_tokens=4096,
                    )
                break
            except LLMServiceError as exc:
                self.log(trace_id, "llm-error", f"模型调用失败（第{attempt + 1}次）：{exc}")
                generated = None

        guide = (
            self._guide_from_llm(generated, paper_id, filename, trace_id, max_page)
            if generated
            else None
        )
        if guide is None:
            guide = self._fallback_guide(chunks, context, paper_id, filename, trace_id)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        self.log(
            trace_id,
            "generate-guide",
            f"生成论文智能导读（{guide.generator}模式，耗时{elapsed_ms}ms）",
        )
        return guide

    def _guide_from_llm(
        self,
        generated: dict[str, Any],
        paper_id: str,
        filename: str,
        trace_id: str,
        max_page: int,
    ) -> GuideResponse | None:
        overview = str(generated.get("overview", "")).strip()
        one_liner = str(generated.get("one_liner", "")).strip()[:120]
        key_points = [
            str(item).strip()
            for item in generated.get("key_points", [])
            if str(item).strip()
        ][:3]
        questions = [
            str(item).strip()
            for item in generated.get("reading_questions", [])
            if str(item).strip()
        ][:3]
        keywords = [
            str(item).strip()
            for item in generated.get("keywords", [])
            if str(item).strip()
        ][:8]
        # 概述或一句话概括缺失说明输出不完整，整体走降级，避免半成品导读
        if not overview or not one_liner or not key_points or not questions:
            return None
        sections = {
            field: self._coerce_section(generated.get(field), max_page)
            for field, _ in self.GUIDE_SECTION_FIELDS
        }
        return GuideResponse(
            paper_id=paper_id,
            title=filename.removesuffix(".pdf"),
            overview=overview,
            key_points=key_points,
            reading_questions=questions,
            one_liner=one_liner,
            keywords=keywords,
            generator="llm",
            agent_trace_id=trace_id,
            **sections,
        )

    @staticmethod
    def _coerce_section(payload: Any, max_page: int) -> GuideSection:
        """把模型输出规整为GuideSection，页码越界或格式异常时丢弃引用。"""
        if not isinstance(payload, dict):
            return GuideSection()
        content = str(payload.get("content", "")).strip() or "原文未说明"
        citations: list[GuideCitation] = []
        raw_citations = payload.get("citations", [])
        if isinstance(raw_citations, list) and content != "原文未说明":
            for item in raw_citations[:4]:
                if not isinstance(item, dict):
                    continue
                # 只保留最末级章节名，防止模型把"论文标题 > 章节"整条路径塞进来
                section = str(item.get("section", "")).split(">")[-1].strip()[:60]
                page: int | None
                try:
                    page = int(item.get("page"))
                except (TypeError, ValueError):
                    page = None
                # 基于US-02"不得虚构"要求：页码超出论文实际页数的引用视为幻觉，丢弃
                if page is not None and not 1 <= page <= max_page:
                    page = None
                if section or page is not None:
                    citations.append(GuideCitation(section=section, page=page))
        return GuideSection(content=content[:1200], citations=citations)

    def _fallback_guide(
        self,
        chunks: list[PaperChunk],
        context: str,
        paper_id: str,
        filename: str,
        trace_id: str,
    ) -> GuideResponse:
        """无模型或模型失败时的提取式降级导读（不虚构，明确标注降级）。"""
        sentences = self._sentences(context)
        overview_text = " ".join(sentences[:3])
        overview = (
            f"《{filename.removesuffix('.pdf')}》共提取{len(chunks)}个内容切片。"
            f"{overview_text[:700]}"
        )
        key_points = [sentence[:180] for sentence in sentences[3:6]]
        if not key_points:
            key_points = [chunk.content[:180] for chunk in chunks[:3]]
        questions = ["研究问题是什么？", "论文采用了什么方法？", "主要实验结论是什么？"]
        degraded = GuideSection(
            content="当前未配置可用模型或模型调用失败，暂无法生成该部分。",
            citations=[],
        )
        return GuideResponse(
            paper_id=paper_id,
            title=filename.removesuffix(".pdf"),
            overview=overview,
            key_points=key_points,
            reading_questions=questions,
            one_liner=overview_text[:100] or f"{filename.removesuffix('.pdf')}导读",
            keywords=self._fallback_keywords(chunks),
            generator="fallback",
            background=degraded.model_copy(),
            research_question=degraded.model_copy(),
            method=degraded.model_copy(),
            experiment=degraded.model_copy(),
            results=degraded.model_copy(),
            innovations=degraded.model_copy(),
            limitations=degraded.model_copy(),
            agent_trace_id=trace_id,
        )

    def _sample_guide_chunks(self, chunks: list[PaperChunk]) -> list[PaperChunk]:
        """全篇分节采样：优先保护局限/结论章节 + 正文首/中/尾 + 各章节代表切片。

        关键改动（US-02 局限性字段常年"原文未说明"的修复）：
        局限/讨论/结论/未来工作等章节多在论文靠后，旧实现先按页码排序再截断到24，
        又在拼接后对字符串做整体截断，两处都会丢掉这些靠后章节。现在先单独挑出这些
        章节的切片并放在候选队首受保护，再按"先占位、后排序"的顺序合并，确保它们不被
        名额或字符预算挤掉；论文本就没有这些章节时 priority 为空，局限性仍如实留空。
        """
        if not chunks:
            return []
        text_chunks = [
            chunk
            for chunk in chunks
            if chunk.kind in {"text", "list"} and not chunk.metadata.get("is_reference")
        ] or list(chunks)

        # 1) 优先章节：局限/讨论/结论/未来工作，每个这类章节最多取前2个切片
        priority: list[PaperChunk] = []
        priority_count: dict[tuple[str, ...], int] = {}
        for chunk in text_chunks:
            if not self._is_limitation_section(chunk):
                continue
            key = tuple(chunk.metadata.get("section_path", []) or [])
            if priority_count.get(key, 0) >= 2:
                continue
            priority.append(chunk)
            priority_count[key] = priority_count.get(key, 0) + 1

        # 2) 常规分节采样：每章节首个切片 + 正文首/中/尾
        per_section: dict[tuple[str, ...], PaperChunk] = {}
        for chunk in text_chunks:
            key = tuple(chunk.metadata.get("section_path", []) or [])
            per_section.setdefault(key, chunk)
        third = max(1, len(text_chunks) // 3)
        general = [
            *text_chunks[:4],
            *per_section.values(),
            *text_chunks[third : third + 3],
            *text_chunks[2 * third : 2 * third + 3],
            *text_chunks[-4:],
        ]

        # 3) 合并：优先章节先占位（受保护），常规采样补足到上限后再按页码排序
        limit = 26
        sampled: list[PaperChunk] = []
        seen: set[str] = set()
        for chunk in (*priority, *general):
            if chunk.chunk_id in seen:
                continue
            sampled.append(chunk)
            seen.add(chunk.chunk_id)
            if len(sampled) >= limit:
                break
        sampled.sort(key=lambda chunk: (chunk.page, chunk.chunk_id))
        return sampled

    @classmethod
    def _is_limitation_section(cls, chunk: PaperChunk) -> bool:
        section = " ".join(
            str(value) for value in (chunk.metadata.get("section_path") or [])
        ).lower()
        return any(keyword in section for keyword in cls.LIMITATION_SECTION_KEYWORDS)

    @staticmethod
    def _chunk_section(chunk: PaperChunk) -> str:
        # 上限放宽到90字符：40会把"5 LLM-based Retrieval-Augmented Evaluation"
        # 这类正常章节名截断，导致模型把残缺名（…Evaluati）写进引用标签
        path = chunk.metadata.get("section_path") or []
        return str(path[-1])[:90] if path else "正文"

    @staticmethod
    def _fallback_keywords(chunks: list[PaperChunk]) -> list[str]:
        counter: Counter[str] = Counter()
        for chunk in chunks[:60]:
            counter.update(
                term
                for term in re.findall(r"[A-Za-z][A-Za-z-]{3,}", chunk.content)
                if term.lower() not in {"this", "that", "with", "from", "were", "have"}
            )
        return [term for term, _ in counter.most_common(5)]

    async def run_mind_map(
        self,
        paper_id: str,
        filename: str,
        trace_id: str,
    ) -> MindMapResponse:
        chunks = self.kb.all_chunks(paper_id)
        text_chunks = [chunk for chunk in chunks if chunk.kind in {"text", "list"}]
        heading_chunks = [
            chunk for chunk in text_chunks if chunk.metadata.get("text_level") is not None
        ]
        sample_candidates = [
            *heading_chunks[:12],
            *text_chunks[:6],
            *text_chunks[len(text_chunks) // 3 : len(text_chunks) // 3 + 4],
            *text_chunks[(len(text_chunks) * 2) // 3 : (len(text_chunks) * 2) // 3 + 4],
            *text_chunks[-4:],
        ]
        sampled = []
        seen_ids: set[str] = set()
        for chunk in sample_candidates:
            if chunk.chunk_id not in seen_ids:
                sampled.append(chunk)
                seen_ids.add(chunk.chunk_id)
        context = "\n\n".join(
            f"[第{chunk.page}页] {chunk.content}" for chunk in sampled
        )[:14000]
        generated = await self.llm.complete_json(
            (
                "你是论文理解Agent。请根据论文内容生成中文思维导图，只输出JSON对象。"
                "字段必须为center和branches；branches包含4到6个对象，每个对象字段为"
                "label、summary、children、subbranches。label必须简短，summary为一句概括，"
                "children为0到3个直接要点；subbranches包含1到3个对象，每个对象只有label"
                "和children，children包含1到4个更细要点。必须形成至少3层结构，并覆盖"
                "研究目的、核心方法、系统组成、实验设计、主要结果与结论。所有节点文字简洁。"
            ),
            f"论文文件名：{filename}\n\n论文内容：\n{context}",
        )
        branches: list[MindMapBranch] = []
        center = filename.removesuffix(".pdf")
        if generated:
            center = str(generated.get("center") or center).strip()[:80]
            payload = generated.get("branches", [])
            if isinstance(payload, list):
                for item in payload[:6]:
                    if not isinstance(item, dict):
                        continue
                    label = str(item.get("label", "")).strip()[:30]
                    summary = str(item.get("summary", "")).strip()[:240]
                    raw_children = item.get("children", [])
                    children = (
                        [str(value).strip()[:100] for value in raw_children if str(value).strip()][:3]
                        if isinstance(raw_children, list)
                        else []
                    )
                    raw_subbranches = item.get("subbranches", [])
                    subbranches: list[MindMapSubBranch] = []
                    if isinstance(raw_subbranches, list):
                        for raw_subbranch in raw_subbranches[:3]:
                            if not isinstance(raw_subbranch, dict):
                                continue
                            sub_label = str(raw_subbranch.get("label", "")).strip()[:36]
                            raw_subchildren = raw_subbranch.get("children", [])
                            subchildren = (
                                [
                                    str(value).strip()[:90]
                                    for value in raw_subchildren
                                    if str(value).strip()
                                ][:4]
                                if isinstance(raw_subchildren, list)
                                else []
                            )
                            if sub_label:
                                subbranches.append(
                                    MindMapSubBranch(
                                        label=sub_label,
                                        children=subchildren,
                                    )
                                )
                    if label and summary:
                        branches.append(
                            MindMapBranch(
                                label=label,
                                summary=summary,
                                children=children,
                                subbranches=subbranches,
                            )
                        )
        if len(branches) < 3:
            sentences = self._sentences(context)
            labels = [
                (
                    "研究问题",
                    [
                        MindMapSubBranch(label="研究背景", children=["研究动机", "现有不足"]),
                        MindMapSubBranch(label="核心目标", children=["待解决问题", "预期贡献"]),
                    ],
                ),
                (
                    "核心方法",
                    [
                        MindMapSubBranch(label="整体框架", children=["输入与输出", "处理流程"]),
                        MindMapSubBranch(label="关键机制", children=["模型设计", "实现要点"]),
                    ],
                ),
                (
                    "实验设计",
                    [
                        MindMapSubBranch(label="实验设置", children=["数据集", "评价指标"]),
                        MindMapSubBranch(label="验证方式", children=["对比实验", "消融实验"]),
                    ],
                ),
                (
                    "主要结论",
                    [
                        MindMapSubBranch(label="实验发现", children=["主要结果", "性能变化"]),
                        MindMapSubBranch(label="后续工作", children=["局限性", "研究方向"]),
                    ],
                ),
            ]
            branches = [
                MindMapBranch(
                    label=label,
                    summary=(
                        sentences[min(index * 2, len(sentences) - 1)][:220]
                        if sentences
                        else "请结合论文原文与页码引用进一步阅读。"
                    ),
                    children=[],
                    subbranches=subbranches,
                )
                for index, (label, subbranches) in enumerate(labels)
            ]
        self.log(trace_id, "generate-mind-map", f"生成{len(branches)}个思维导图分支")
        return MindMapResponse(
            paper_id=paper_id,
            title=f"{filename.removesuffix('.pdf')} · 论文思维导图",
            center=center,
            branches=branches,
            agent_trace_id=trace_id,
        )

    async def explain_chunk(
        self,
        paper_id: str,
        filename: str,
        chunk: PaperChunk,
        trace_id: str,
    ) -> ChunkExplanationResponse:
        # 基于US-05/06/07优化：按切片类型分派不同提示词（见app/prompts/explanation.py），
        # 图片/图表/表格/公式各有专属解读要点与防虚构约束
        spec = get_explanation_prompt(chunk.kind)
        kind_label = spec.label
        # 不再孤立解释切片，补上所在章节、相邻正文与引用它的段落
        context = self._build_chunk_context(paper_id, chunk)
        user_prompt = (
            f"论文：{filename}\n"
            f"位置：第{chunk.page}页，类型：{kind_label}\n\n"
            f"【待解释的{kind_label}切片】\n{chunk.content[:8000]}"
        )
        if context:
            user_prompt += f"\n\n【论文中的相关上下文（辅助理解，不要直接照抄）】\n{context}"

        explanation = ""
        # 图片/图表且配置了视觉模型：走多模态，把真实图像发给视觉模型（US-07）
        vision_spec = get_vision_prompt(chunk.kind)
        if vision_spec is not None and self.vision is not None and self.vision.enabled:
            image = self._load_chunk_image(chunk)
            if image is not None:
                image_bytes, mime = image
                try:
                    explanation = await self.vision.describe(
                        vision_spec.system_prompt, user_prompt, image_bytes, mime
                    )
                    if explanation:
                        self.log(
                            trace_id,
                            "explain-chunk-vision",
                            f"第{chunk.page}页{kind_label}走视觉模型解释",
                        )
                except VisionServiceError as exc:
                    # 视觉服务异常回退纯文本解释，保证功能不中断
                    self.log(trace_id, "vision-error", f"视觉解释失败，回退文本：{exc}")

        # 非图片/图表，或视觉未启用/失败 → 纯文本模型解释
        if not explanation:
            explanation = await self.llm.complete(
                spec.system_prompt,
                user_prompt,
                max_tokens=800,
            )
        if not explanation:
            content = chunk.content.replace("\n", " ").strip()
            explanation = (
                f"这是第{chunk.page}页的{kind_label}切片。"
                f"当前未配置可用模型，可先依据原始内容阅读：{content[:420]}"
            )
        self.log(trace_id, "explain-chunk", f"解释第{chunk.page}页{kind_label}切片")
        return ChunkExplanationResponse(
            paper_id=paper_id,
            chunk_id=chunk.chunk_id,
            page=chunk.page,
            explanation=explanation,
            agent_trace_id=trace_id,
        )

    def _build_chunk_context(self, paper_id: str, chunk: PaperChunk) -> str:
        """为待解释切片汇集上下文：RAG检索的相关正文（含章节）+ 同页其它正文。

        对图/表/公式，用其图题/内容做检索能召回"引用它的段落"与所在章节，
        让解释结合上下文而非孤立看图说话（US-07 验收：需带图题、章节、相邻正文）。
        """
        parts: list[str] = []
        query = (self._caption_text(chunk) or chunk.content).strip()[:200]
        if query:
            snippets: list[str] = []
            for related in self.kb.search(paper_id, query, limit=5):
                if related.chunk_id == chunk.chunk_id or related.kind not in {"text", "list"}:
                    continue
                section = " > ".join(
                    str(value) for value in related.metadata.get("section_path", [])
                )
                head = f"[{section}·第{related.page}页] " if section else f"[第{related.page}页] "
                snippets.append(head + related.content[:320])
                if len(snippets) >= 3:
                    break
            if snippets:
                parts.append("相关正文与章节：\n" + "\n\n".join(snippets))

        same_page = [
            other.content[:220]
            for other in self.kb.all_chunks(paper_id)
            if other.page == chunk.page
            and other.chunk_id != chunk.chunk_id
            and other.kind in {"text", "list"}
        ]
        if same_page:
            parts.append("本页其它正文：\n" + "\n".join(same_page[:2]))

        return "\n\n".join(parts)[:6000]

    def _load_chunk_image(self, chunk: PaperChunk) -> tuple[bytes, str] | None:
        """把切片的 resource_url 映射回 assets 目录下的图片文件并读取字节。"""
        url = chunk.resource_url
        prefix = "/media/assets/"
        if not url or not url.startswith(prefix) or self.assets_dir is None:
            return None
        relative = url[len(prefix):]
        assets_root = self.assets_dir.resolve()
        target = (assets_root / relative).resolve()
        # 防越界：目标必须位于 assets 目录内
        if assets_root not in target.parents or not target.is_file():
            return None
        suffix = target.suffix.lower()
        mime = "image/png" if suffix == ".png" else "image/jpeg"
        try:
            return target.read_bytes(), mime
        except OSError:
            return None

    @staticmethod
    def _caption_text(chunk: PaperChunk) -> str:
        """取切片的图题/表题，作为检索"引用它的段落"的查询种子。"""
        for key in ("caption", "table_caption", "image_caption"):
            value = chunk.metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, list) and value:
                joined = " ".join(str(item).strip() for item in value if str(item).strip())
                if joined:
                    return joined
        return ""

    @staticmethod
    def _sentences(text: str) -> list[str]:
        candidates = re.split(r"(?<=[。！？.!?])\s+|\n+", text)
        return [
            sentence.strip()
            for sentence in candidates
            if 45 <= len(sentence.strip()) <= 500
        ]
