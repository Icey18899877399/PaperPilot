"""Visual content analysis agent for US-07.

Uses MinerU-extracted structured data (captions, table text, LaTeX) with
the existing text-only LLM — no vision model required.

Called directly by chat.py when a query targets images/charts/tables/equations.
Does NOT go through Coordinator, so runtime / coordinator / schemas are untouched.
"""

from __future__ import annotations

from app.models.schemas import ChatResponse, Citation, PaperChunk
from app.services.knowledge_base import KnowledgeBase
from app.services.llm import LLMClient
from app.services.visual_prompts import (
    classify_query,
    kind_name,
    select_prompt,
)

# Patterns for matching reference numbers against chunk content
_REF_PATTERNS = {
    "image": lambda n: [
        f"图{n}", f"图 {n}", f"Figure {n}", f"Figure{n}",
        f"Fig. {n}", f"Fig.{n}", f"Fig {n}",
    ],
    "table": lambda n: [
        f"表{n}", f"表 {n}", f"Table {n}", f"Table{n}",
    ],
    "equation": lambda n: [
        f"公式{n}", f"公式({n})", f"公式（{n}）",
        f"Equation {n}", f"Equation({n})", f"Eq. {n}", f"Eq.{n}",
    ],
}


class VisualAnalysisAgent:
    """Stateless agent — instantiated per-call by chat.py.

    Uses kb + llm directly; no BaseAgent inheritance to keep it simple
    and avoid touching the agent hierarchy.
    """

    name = "visual-analysis-agent"

    def __init__(self, kb: KnowledgeBase, llm: LLMClient):
        self.kb = kb
        self.llm = llm

    async def run(
        self, paper_id: str, question: str, trace_id: str
    ) -> ChatResponse:
        # ── 1. classify ──────────────────────────────────────────
        target = classify_query(question)
        target["kind"] = self._expand_image_kind(target["kind"])

        # ── 2. retrieve ──────────────────────────────────────────
        all_chunks = self.kb.all_chunks(paper_id)
        if not all_chunks:
            return ChatResponse(
                answer="当前论文没有可检索的结构化内容，请先完成PDF解析。",
                citations=[],
                videos=[],
                agent_trace_id=trace_id,
                evidence_sufficient=False,
            )

        chunks = self._filter_chunks(all_chunks, target)
        if not chunks:
            kind_label = kind_name(target["kind"]) if target["kind"] else "视觉元素"
            ref_hint = (
                f"编号 {target['ref']} " if target["ref"] else ""
            )
            return ChatResponse(
                answer=(
                    f"未在论文中找到匹配的{kind_label}（{ref_hint}）。"
                    f"请确认编号是否正确，或尝试更宽泛的描述。"
                ),
                citations=[],
                videos=[],
                agent_trace_id=trace_id,
                evidence_sufficient=False,
            )

        # ── 3. build context ─────────────────────────────────────
        context = self._build_context(chunks[:8])
        system_prompt = select_prompt(target["kind"])

        # ── 4. LLM call ──────────────────────────────────────────
        answer = await self.llm.complete(
            system_prompt,
            f"视觉内容数据：\n{context}\n\n问题：{question}",
        )

        # ── 5. fallback ──────────────────────────────────────────
        evidence = True
        if not answer:
            answer = self._build_fallback(chunks[:5])
            evidence = False

        # ── 6. citations ─────────────────────────────────────────
        citations = [
            Citation(
                chunk_id=c.chunk_id,
                page=c.page,
                quote=c.content[:180],
                kind=c.kind,
                resource_url=c.resource_url,
                bbox=c.bbox,
            )
            for c in chunks[:10]
        ]

        return ChatResponse(
            answer=answer,
            citations=citations,
            videos=[],
            agent_trace_id=trace_id,
            evidence_sufficient=evidence,
        )

    # ── helpers ──────────────────────────────────────────────────

    @staticmethod
    def _expand_image_kind(kind: str | None) -> str | None:
        """Treat 'image' queries as also matching 'chart' chunks."""
        return kind  # keep as-is; _filter_chunks handles the mapping

    def _filter_chunks(
        self, chunks: list[PaperChunk], target: dict
    ) -> list[PaperChunk]:
        kind = target["kind"]
        ref = target["ref"]

        # filter by kind
        if kind == "image":
            filtered = [c for c in chunks if c.kind in {"image", "chart"}]
        elif kind:
            filtered = [c for c in chunks if c.kind == kind]
        else:
            filtered = [c for c in chunks if c.kind != "text"]

        # filter by reference number
        if ref and filtered:
            patterns = _REF_PATTERNS.get(kind, lambda n: [])(ref) if kind else []
            if patterns:
                matched = []
                for c in filtered:
                    search_in = c.content
                    for key in ("caption", "table_caption"):
                        if c.metadata.get(key):
                            search_in += " " + c.metadata[key]
                    if any(p in search_in for p in patterns):
                        matched.append(c)
                if matched:
                    return matched

        return filtered

    def _build_context(self, chunks: list[PaperChunk]) -> str:
        blocks = []
        for i, c in enumerate(chunks, 1):
            parts = [f"【元素{i}】{kind_name(c.kind)} · 第{c.page}页"]

            if c.kind in {"image", "chart"}:
                if c.metadata.get("caption"):
                    parts.append(f"标题：{c.metadata['caption']}")
                if c.metadata.get("footnote"):
                    parts.append(f"脚注：{c.metadata['footnote']}")
                parts.append(f"描述：{c.content}")

            elif c.kind == "table":
                cap = c.metadata.get("caption") or c.metadata.get("table_caption", "")
                if cap:
                    parts.append(f"标题：{cap}")
                if c.metadata.get("table_text"):
                    parts.append(f"数据：\n{c.metadata['table_text']}")
                fn = c.metadata.get("footnote") or c.metadata.get("table_footnote", "")
                if fn:
                    parts.append(f"脚注：{fn}")
                if not c.metadata.get("table_text"):
                    parts.append(f"描述：{c.content}")

            elif c.kind == "equation":
                latex = c.metadata.get("latex", "")
                if latex:
                    parts.append(f"LaTeX：{latex}")
                else:
                    parts.append(f"内容：{c.content}")

            else:
                parts.append(f"内容：{c.content}")

            blocks.append("\n".join(parts))

        return "\n\n---\n\n".join(blocks)

    def _build_fallback(self, chunks: list[PaperChunk]) -> str:
        lines = ["以下为检索到的视觉内容原文（无模型模式）：", ""]
        for i, c in enumerate(chunks, 1):
            lines.append(f"### {i}. 第{c.page}页 · {kind_name(c.kind)}")
            if c.metadata.get("caption"):
                lines.append(f"标题：{c.metadata['caption']}")
            if c.metadata.get("table_text"):
                lines.append(f"表格数据：{c.metadata['table_text'][:500]}")
            if c.metadata.get("latex"):
                lines.append(f"LaTeX：{c.metadata['latex']}")
            lines.append(f"内容：{c.content[:400]}")
            lines.append("")
        lines.append("---")
        lines.append("配置LLM后将自动分析以上内容。")
        return "\n".join(lines)