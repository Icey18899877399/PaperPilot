from __future__ import annotations

import json

from app.agents.base import BaseAgent
from app.models.schemas import BilingualBlock, PaperChunk, TranslationResponse
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

    async def run_page(
        self,
        chunks: list[PaperChunk],
        target_language: str,
        trace_id: str,
    ) -> list[BilingualBlock]:
        translatable = [
            chunk
            for chunk in chunks
            if chunk.content.strip() and chunk.kind not in {"equation", "code"}
        ]
        payload = [
            {"chunk_id": chunk.chunk_id, "text": chunk.content}
            for chunk in translatable
        ]
        generated = await self.llm.complete_json(
            (
                f"你是学术论文排版翻译Agent。把每个段落忠实翻译为{target_language}，"
                "保留人名、术语、公式、引用编号和列表结构。只输出JSON对象，格式为"
                '{"translations":[{"chunk_id":"原ID","translated_text":"译文"}]}。'
                "不得遗漏或合并段落，也不要输出解释。"
            ),
            json.dumps(payload, ensure_ascii=False),
            max_tokens=4000,
        )
        translations: dict[str, str] = {}
        if generated and isinstance(generated.get("translations"), list):
            for item in generated["translations"]:
                if not isinstance(item, dict):
                    continue
                chunk_id = str(item.get("chunk_id", ""))
                translated_text = str(item.get("translated_text", "")).strip()
                if chunk_id and translated_text:
                    translations[chunk_id] = translated_text

        blocks = []
        for chunk in chunks:
            translated = translations.get(chunk.chunk_id)
            if not translated:
                translated = (
                    chunk.content
                    if chunk.kind in {"equation", "code"}
                    else f"[待配置翻译模型] {chunk.content}"
                )
            blocks.append(
                BilingualBlock(
                    chunk_id=chunk.chunk_id,
                    page=chunk.page,
                    kind=chunk.kind,
                    source_text=chunk.content,
                    translated_text=translated,
                    resource_url=chunk.resource_url,
                    bbox=chunk.bbox,
                    metadata=chunk.metadata,
                )
            )
        self.log(trace_id, "translate-page", f"翻译{len(translatable)}个页面内容块")
        return blocks
