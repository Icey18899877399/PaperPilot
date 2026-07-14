from __future__ import annotations

from app.agents.base import BaseAgent
from app.models.schemas import ChatResponse, Citation
from app.services.knowledge_base import KnowledgeBase
from app.services.llm import LLMClient
from app.services.video_catalog import VideoCatalog


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
        chunks = self.kb.search(paper_id, question, limit=6)
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
        context = "\n\n".join(
            f"[{self._kind_label(chunk.kind)}，第{chunk.page}页] {chunk.content}"
            for chunk in chunks
        )
        answer = await self.llm.complete(
            "你是论文多模态聊天问答Agent。只能依据给定的文字、图片说明、表格内容和公式回答；"
            "回答图表或公式问题时说明其类型与含义，结论后标注页码，不确定时明确说明。",
            f"问题：{question}\n\n论文片段：\n{context}",
        )
        if not answer:
            if chunks:
                evidence = "\n\n".join(
                    f"第{chunk.page}页：{chunk.content[:320]}"
                    for chunk in chunks[:2]
                )
                answer = (
                    "根据当前检索到的论文内容，可以先得到以下依据：\n\n"
                    f"{evidence}\n\n"
                    "以上是无模型模式下的提取式回答；配置LLM后会进一步归纳并保持页码引用。"
                )
            else:
                answer = "当前论文没有可检索的文本内容，请检查PDF解析结果。"
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
