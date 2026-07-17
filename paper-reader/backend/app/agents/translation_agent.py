from __future__ import annotations

from app.agents.base import BaseAgent
from app.models.schemas import TranslationResponse
from app.services.llm import LLMClient


class TranslationAgent(BaseAgent):
    name = "translation-agent"

    def __init__(self, llm: LLMClient, log_sink):
        super().__init__(log_sink)
        self.llm = llm

    async def run(
        self, text: str, target_language: str, trace_id: str
    ) -> TranslationResponse:
        translated = await self.llm.complete(
            f"你是学术翻译Agent。忠实翻译为{target_language}，保留术语、公式和引用编号。",
            text,
        )
        if not translated:
            translated = f"[开发模式：待接入翻译模型]\n{text}"
        self.log(trace_id, "translate", f"翻译为{target_language}")
        return TranslationResponse(
            translated_text=translated,
            target_language=target_language,
            agent_trace_id=trace_id,
        )

