from __future__ import annotations

import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from app.agents.base import BaseAgent
from app.models.schemas import ChatResponse, Citation
from app.services.knowledge_base import KnowledgeBase
from app.services.llm import LLMClient, LLMServiceError
from app.services.video_catalog import VideoCatalog


@dataclass
class ChatEvidence:
    citations: list[Citation]
    context: str
    videos: list
    immediate_answer: str | None = None


class ChatAgent(BaseAgent):
    name = "chat-agent"

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

    async def run(self, paper_id: str, question: str, trace_id: str) -> ChatResponse:
        evidence = self._prepare_evidence(paper_id, question, trace_id)
        if evidence.immediate_answer:
            answer = evidence.immediate_answer
        else:
            try:
                answer = await self.llm.complete(
                    self._system_prompt(),
                    self._user_prompt(question, evidence.context),
                )
            except LLMServiceError as exc:
                self.log(trace_id, "llm-error", f"模型调用失败，切换提取式回答：{exc}")
                answer = ""
            if not answer:
                answer = self._fallback_answer(paper_id, evidence.context)
        self._log_answer(trace_id, len(evidence.citations), len(evidence.videos))
        return ChatResponse(
            answer=answer,
            citations=evidence.citations,
            videos=evidence.videos,
            agent_trace_id=trace_id,
        )

    async def stream(
        self,
        paper_id: str,
        question: str,
        trace_id: str,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """真实流式聊天：先返回检索状态，再逐token返回答案，最后返回完整证据。"""
        yield "status", {"message": "正在检索论文知识库"}
        evidence = self._prepare_evidence(paper_id, question, trace_id)
        yield "evidence", {"count": len(evidence.citations)}
        answer_parts: list[str] = []
        if evidence.immediate_answer:
            answer_parts.append(evidence.immediate_answer)
            yield "delta", {"text": evidence.immediate_answer}
        else:
            yield "status", {"message": "正在基于原文组织回答"}
            try:
                async for delta in self.llm.complete_stream(
                    self._system_prompt(),
                    self._user_prompt(question, evidence.context),
                ):
                    answer_parts.append(delta)
                    yield "delta", {"text": delta}
            except LLMServiceError as exc:
                self.log(trace_id, "llm-error", f"流式模型调用失败，切换提取式回答：{exc}")
                yield "status", {"message": "模型暂不可用，正在生成提取式回答"}
        answer = "".join(answer_parts).strip()
        if not answer:
            answer = self._fallback_answer(paper_id, evidence.context)
            yield "delta", {"text": answer}
        self._log_answer(trace_id, len(evidence.citations), len(evidence.videos))
        result = ChatResponse(
            answer=answer,
            citations=evidence.citations,
            videos=evidence.videos,
            agent_trace_id=trace_id,
        )
        yield "complete", result.model_dump(mode="json")

    def _prepare_evidence(
        self,
        paper_id: str,
        question: str,
        trace_id: str,
    ) -> ChatEvidence:
        chunks = self.kb.search(paper_id, question, limit=6)
        # 基于US-05 AC-05-02：知识库有内容但检索零命中，说明论文证据不足，
        # 直接如实告知，不得用常识补写论文中不存在的结论
        if not chunks and self.kb.retrieval_chunks(paper_id):
            self.log(trace_id, "answer", "检索零命中，返回证据不足提示")
            answer = (
                    "当前论文证据不足：没有检索到与该问题相关的论文内容，"
                    "无法基于原文作答。请尝试换一种问法，或确认问题是否属于本论文范围。"
            )
            return ChatEvidence(
                citations=[],
                context="",
                videos=self.videos.recommend(question, context=""),
                immediate_answer=answer,
            )
        citations = [
            Citation(
                chunk_id=chunk.chunk_id,
                page=chunk.page,
                quote=self._citation_quote(chunk.content)[:240],
                kind=chunk.kind,
                section=" > ".join(
                    str(item)
                    for item in chunk.metadata.get("section_path", [])
                    if str(item).strip()
                ),
                resource_url=chunk.resource_url,
                bbox=chunk.bbox,
            )
            for chunk in chunks
        ]
        context = "\n\n".join(
            f"[{self._kind_label(chunk.kind)}，第{chunk.page}页] {chunk.content}"
            for chunk in chunks
        )
        return ChatEvidence(
            citations=citations,
            context=context,
            videos=self.videos.recommend(question, context=context),
        )

    @staticmethod
    def _system_prompt() -> str:
        return (
            "你是论文多模态聊天问答Agent。只能依据给定的文字、图片说明、表格内容和公式回答；"
            "回答图表或公式问题时说明其类型与含义，结论后标注页码，不确定时明确说明。"
            "用简体中文，可对关键结论、术语或数值用 **加粗** 标注以突出重点，但不要使用"
            "其它Markdown语法（不用标题#、列表符号或代码块）。"
        )

    @staticmethod
    def _user_prompt(question: str, context: str) -> str:
        return f"问题：{question}\n\n论文片段：\n{context}"

    def _fallback_answer(self, paper_id: str, context: str) -> str:
        if context:
            evidence = "\n\n".join(context.split("\n\n")[:2])
            return (
                "根据当前检索到的论文内容，可以先得到以下依据：\n\n"
                f"{evidence[:760]}\n\n"
                "以上为提取式回答；模型恢复后可进一步归纳。"
            )
        if self.kb.retrieval_chunks(paper_id):
            return "当前论文证据不足，无法基于原文回答该问题。"
        return "当前论文没有可检索的文本内容，请检查PDF解析结果。"

    def _log_answer(self, trace_id: str, citation_count: int, video_count: int) -> None:
        self.log(
            trace_id,
            "answer",
            f"检索{citation_count}个片段，推荐{video_count}个本地视频",
        )

    @staticmethod
    def _citation_quote(content: str) -> str:
        """引用摘录不再混入RAG的“章节：...”检索前缀。"""
        return re.sub(r"^章节：[^。\n]{1,240}(?:\n|$)", "", content).strip()

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
