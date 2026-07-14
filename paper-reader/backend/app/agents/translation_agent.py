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
            (
                f"你是学术翻译Agent。忠实翻译为{target_language}，保留术语、公式和引用编号。"
                "只输出译文纯文本，不要添加解释、Markdown星号或标题标记。"
            ),
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
        payload = []
        for chunk in translatable:
            item = {
                "chunk_id": chunk.chunk_id,
                "kind": chunk.kind,
                "text": chunk.content,
            }
            table_html = str(chunk.metadata.get("table_html") or "").strip()
            if chunk.kind == "table" and table_html:
                item["table_html"] = table_html
            payload.append(item)
        output_budget = min(
            12000,
            max(6000, sum(len(chunk.content) for chunk in translatable) * 2),
        )
        generated = await self.llm.complete_json(
            (
                f"你是学术论文排版翻译Agent。把每个段落忠实翻译为{target_language}，"
                "保留人名、术语、公式、引用编号和列表结构。对于表格块，必须翻译表头、"
                "行名和每个文字单元格；如果提供table_html，必须按其中的tr/td顺序还原全部"
                "单元格，并在译文中每行使用换行、单元格之间使用竖线保留行列关系。"
                "不得只翻译表题，也不得省略看似重复或较长的单元格。"
                "translated_text只能是纯文本，不要使用Markdown星号或标题标记。"
                "只输出JSON对象，格式为"
                '{"translations":[{"chunk_id":"原ID","translated_text":"译文"}]}。'
                "不得遗漏或合并段落，也不要输出解释。"
            ),
            json.dumps(payload, ensure_ascii=False),
            max_tokens=output_budget,
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
