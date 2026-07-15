from __future__ import annotations

import re

from app.agents.base import BaseAgent
from app.models.schemas import ChatResponse, Citation
from app.services.knowledge_base import KnowledgeBase
from app.services.llm import LLMClient
from app.services.video_catalog import VideoCatalog


class ChatAgent(BaseAgent):
    name = "chat-agent"

    # ── page detection ────────────────────────────────────────────
    _PAGE_RE = re.compile(
        r"第\s*(\d+)\s*页|page\s+(\d+)",
        re.IGNORECASE,
    )

    # ── broad / overview question keywords ─────────────────────────
    _BROAD_KEYWORDS = [
        # Chinese
        "核心方法", "主要方法", "用什么方法", "用了什么方法",
        "总结", "概括", "概述", "总结一下", "归纳",
        "主要内容", "讲了什么", "研究什么", "做了什么",
        "主要贡献", "创新点", "贡献", "亮点",
        "介绍", "背景", "相关工作",
        "结论", "结果", "实验设计", "实验",
        "框架", "架构", "模型架构", "系统架构",
        "整体", "总体", "大致", "大概",
        "论文内容", "文章内容", "这篇论文",
        # English
        "summary", "summarize", "overview",
        "main idea", "contribution", "method", "methodology",
        "framework", "architecture", "approach",
    ]

    # ── AC-05-02 evidence check helpers ────────────────────────────
    INSUFFICIENT_MARKER = "INSUFFICIENT_EVIDENCE"

    _SYSTEM_PROMPT = (
        "你是论文多模态聊天问答Agent。严格遵循以下规则：\n"
        "1. 你只能依据下方提供的「论文片段」来回答用户问题。\n"
        "2. 对于概括性、总结性问题（如方法、贡献、内容概述），"
        "你必须综合分析所有片段进行归纳总结，而非逐条罗列。\n"
        "3. 当用户问及特定页码时，综合该页所有片段给出完整回答，"
        "包括该页的文字、图表、公式等所有内容。\n"
        "4. 只有当所有片段与问题主题完全无关（例如问「比特币」但论文是NLP方向），"
        "你才回复一行：" + INSUFFICIENT_MARKER + "\n"
        "5. 严禁编造论文中不存在的具体数据、数值或实验结论。"
        "不确定的细节请标注「论文原文未明确说明」。\n"
        "6. 回答图表或公式问题时说明其类型与含义。\n"
        "7. 每条结论必须标注来源页码，格式为【第X页】。"
    )

    _INSUFFICIENT_RESPONSE = (
        "当前论文证据不足，无法回答该问题。论文中未包含与您问题直接相关的信息。\n"
        "建议尝试以下方式：\n"
        "1. 换一种更具体的提问方式\n"
        "2. 查阅论文其他章节\n"
        "3. 确认问题涉及的概念是否在论文中出现"
    )

    def __init__(
        self,
        kb: KnowledgeBase,
        llm: LLMClient,
        videos: VideoCatalog,
        log_sink,
    ):
        super().__init__(log_sink)
        self.kb = kb
        self.llm = llm
        self.videos = videos

    # ── helpers ───────────────────────────────────────────────────

    @classmethod
    def _is_broad_question(cls, question: str) -> bool:
        """Detect overview / summary / methodology questions."""
        lowered = question.lower()
        return any(keyword in lowered for keyword in cls._BROAD_KEYWORDS)

    @classmethod
    def _extract_page(cls, question: str) -> int | None:
        m = cls._PAGE_RE.search(question)
        if not m:
            return None
        return int(m.group(1) or m.group(2))

    # ── main entry ────────────────────────────────────────────────

    async def run(
        self,
        paper_id: str,
        question: str,
        trace_id: str,
        history: list[dict[str, str]] | None = None,
    ) -> ChatResponse:
        target_page = self._extract_page(question)
        is_broad = self._is_broad_question(question)

        # ── retrieval strategy ────────────────────────────────────
        if target_page is not None:
            # page-level query → grab everything from that page
            all_chunks = self.kb.all_chunks(paper_id)
            chunks = [c for c in all_chunks if c.page == target_page]
            limit = 30
            chunks = chunks[:limit]
            self.log(
                trace_id,
                "retrieve",
                f"页面查询：第{target_page}页，共{len(chunks)}个片段",
            )
        elif is_broad:
            # broad overview → wider retrieval
            chunks = self.kb.search(paper_id, question, limit=15)
            self.log(
                trace_id,
                "retrieve",
                f"宽泛查询：检索{len(chunks)}个片段（上限15）",
            )
        else:
            chunks = self.kb.search(paper_id, question, limit=6)
            self.log(trace_id, "retrieve", f"标准查询：检索{len(chunks)}个片段")

        # ── pre-check: truly empty paper ──────────────────────────
        if not chunks and not self.kb.all_chunks(paper_id):
            self.log(trace_id, "no-evidence", "论文无可检索文本内容")
            return ChatResponse(
                answer="当前论文没有可检索的文本内容，请检查PDF解析结果。",
                citations=[],
                videos=[],
                agent_trace_id=trace_id,
                evidence_sufficient=False,
            )

        # fallback: if search returned nothing but paper has content,
        # grab some chunks from across the paper
        if not chunks:
            all_chunks = self.kb.all_chunks(paper_id)
            if all_chunks:
                # sample from beginning / middle / end
                n = len(all_chunks)
                indices = {0, n // 2, n - 1}
                chunks = []
                for i in sorted(indices):
                    if 0 <= i < n:
                        chunks.append(all_chunks[i])
                self.log(
                    trace_id,
                    "retrieve-fallback",
                    f"关键词无命中，取{len(chunks)}个采样片段",
                )

        # still nothing → truly empty
        if not chunks:
            self.log(trace_id, "no-evidence", "论文无可检索文本内容")
            return ChatResponse(
                answer="当前论文没有可检索的文本内容，请检查PDF解析结果。",
                citations=[],
                videos=[],
                agent_trace_id=trace_id,
                evidence_sufficient=False,
            )

        # ── build citations ───────────────────────────────────────
        citations = [
            Citation(
                chunk_id=chunk.chunk_id,
                page=chunk.page,
                quote=chunk.content[:180],
                kind=chunk.kind,
                resource_url=chunk.resource_url,
                bbox=chunk.bbox,
            )
            for chunk in chunks
        ]

        # ── build context ─────────────────────────────────────────
        context_lines = []
        for chunk in chunks:
            label = self._kind_label(chunk.kind)
            context_lines.append(
                f"[{label}，第{chunk.page}页] {chunk.content}"
            )
        context = "\n\n".join(context_lines)

        # ── build user prompt with history ────────────────────────
        user_prompt = f"论文片段：\n{context}\n\n"
        if target_page is not None:
            user_prompt = (
                f"用户正在询问第{target_page}页的内容。"
                f"以下是该页的所有片段，请综合后给出完整回答。\n\n"
                + user_prompt
            )
        if history:
            user_prompt += "对话历史：\n"
            for turn in history[-6:]:
                role_label = "用户" if turn["role"] == "user" else "AI"
                user_prompt += f"【{role_label}】{turn['text']}\n"
            user_prompt += "\n"
        user_prompt += f"问题：{question}"

        # ── LLM call ──────────────────────────────────────────────
        answer = await self.llm.complete(self._SYSTEM_PROMPT, user_prompt)

        # ── post-check: LLM declared insufficient evidence ────────
        if answer and self.INSUFFICIENT_MARKER in answer.upper():
            self.log(trace_id, "insufficient", "LLM判定证据不足")
            return ChatResponse(
                answer=self._INSUFFICIENT_RESPONSE,
                citations=citations,
                videos=[],
                agent_trace_id=trace_id,
                evidence_sufficient=False,
            )

        # ── fallback when LLM is unavailable ──────────────────────
        if not answer:
            if chunks:
                evidence = "\n\n".join(
                    f"第{chunk.page}页：{chunk.content[:320]}"
                    for chunk in chunks[:3]
                )
                answer = (
                    "根据当前检索到的论文内容，可以先得到以下依据：\n\n"
                    f"{evidence}\n\n"
                    "以上是无模型模式下的提取式回答；配置LLM后会进一步归纳并保持页码引用。"
                )
            else:
                answer = "当前论文没有可检索的文本内容，请检查PDF解析结果。"

        # ── post-check: answer without citations ──────────────────
        if answer and not citations:
            answer += (
                "\n\n（注：当前回答未能定位到具体原文片段，"
                "建议尝试更具体的问题。）"
            )

        videos = self.videos.recommend(question)
        self.log(
            trace_id,
            "answer",
            f"检索{len(chunks)}个片段，推荐{len(videos)}个本地视频",
        )
        return ChatResponse(
            answer=answer,
            citations=citations,
            videos=videos,
            agent_trace_id=trace_id,
            evidence_sufficient=True,
        )

    @staticmethod
    def _kind_label(kind: str) -> str:
        return {
            "image": "图片",
            "chart": "图表",
            "table": "表格",
            "equation": "公式",
            "code": "代码",
            "list": "列表",
        }.get(kind, "正文")