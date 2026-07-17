"""US-02结构化智能导读测试（离线假LLM，不访问真实模型服务）。"""

import json

import httpx
import pytest

from app.agents.paper_agent import PaperUnderstandingAgent
from app.core.config import Settings
from app.models.schemas import PaperChunk
from app.services.knowledge_base import KnowledgeBase
from app.services.llm import LLMClient

PAPER_ID = "paper-guide"
FAKE_KEY = "sk-test-1234567890abcdefghij"


def test_sample_guide_prioritizes_late_limitation_section():
    """靠后的局限章节必须被采样到（US-02 局限性字段修复）。"""
    agent = PaperUnderstandingAgent(kb=None, llm=None, log_sink=[])
    chunks: list[PaperChunk] = []
    # 30个前段章节切片（页1~15），旧逻辑会用它们把靠后章节挤出名额并按页码截断
    for index in range(30):
        chunks.append(
            PaperChunk(
                chunk_id=f"e{index}",
                paper_id="p",
                page=1 + index // 2,
                content=f"前段内容{index}" * 20,
                metadata={
                    "section_path": [f"{index // 3 + 1} Section"],
                    "is_reference": False,
                },
            )
        )
    # 论文靠后的 Limitations 章节（页19）
    chunks.append(
        PaperChunk(
            chunk_id="lim1",
            paper_id="p",
            page=19,
            content="本文方法在长文本上的泛化能力有限。" * 10,
            metadata={"section_path": ["7 Limitations"], "is_reference": False},
        )
    )
    sampled = agent._sample_guide_chunks(chunks)
    assert "lim1" in {chunk.chunk_id for chunk in sampled}


def test_sample_guide_without_limitation_section_stays_valid():
    """论文没有局限章节时采样照常工作，不强行编造。"""
    agent = PaperUnderstandingAgent(kb=None, llm=None, log_sink=[])
    chunks = [
        PaperChunk(
            chunk_id=f"c{index}",
            paper_id="p",
            page=1 + index,
            content=f"正文{index}" * 20,
            metadata={"section_path": [f"{index + 1} Section"], "is_reference": False},
        )
        for index in range(6)
    ]
    sampled = agent._sample_guide_chunks(chunks)
    assert 0 < len(sampled) <= 26
    assert not any(agent._is_limitation_section(chunk) for chunk in sampled)


def build_kb() -> KnowledgeBase:
    kb = KnowledgeBase()
    kb.index(
        PAPER_ID,
        [
            PaperChunk(
                chunk_id=f"s{index}",
                paper_id=PAPER_ID,
                page=index,
                content=content * 4,
                metadata={"text_level": None},
            )
            for index, content in enumerate(
                [
                    "本文研究复杂事件预测问题，提出了新的多模态框架。",
                    "方法部分采用Transformer编码器与检索增强模块。",
                    "实验在OpenForecast数据集上评估，报告准确率与F1。",
                    "结论显示所提方法优于基线，并讨论了局限性与未来工作。",
                ],
                start=1,
            )
        ],
    )
    return kb


def make_llm(handler) -> LLMClient:
    settings = Settings(
        deepseek_api_key=FAKE_KEY,
        deepseek_model="deepseek-v4-flash",
        backend_dir=None or Settings().backend_dir,
    )
    return LLMClient(settings, transport=httpx.MockTransport(handler))


def guide_payload() -> dict:
    section = {
        "content": "论文研究复杂事件预测问题。",
        "citations": [{"section": "引言", "page": 1}],
    }
    return {
        "one_liner": "一种面向复杂事件预测的多模态框架。",
        "background": section,
        "research_question": section,
        "method": {
            "content": "采用Transformer编码器与检索增强模块。",
            "citations": [{"section": "方法", "page": 2}],
        },
        "experiment": {
            "content": "在OpenForecast数据集上评估准确率与F1。",
            "citations": [{"section": "实验", "page": 3}],
        },
        "results": {
            "content": "所提方法优于基线。",
            # 页码越界，应被"不得虚构"校验丢弃
            "citations": [{"section": "实验", "page": 99}],
        },
        "innovations": section,
        "limitations": {"content": "原文未说明", "citations": []},
        "keywords": ["事件预测", "Transformer", "RAG"],
        "overview": "本文提出面向复杂事件预测的多模态框架并验证其有效性。",
        "key_points": ["要点一", "要点二", "要点三"],
        "reading_questions": ["问题一？", "问题二？", "问题三？"],
    }


@pytest.mark.asyncio
async def test_guide_contains_nine_sections_with_citations():
    def handler(request: httpx.Request) -> httpx.Response:
        body = {
            "choices": [
                {"message": {"content": json.dumps(guide_payload(), ensure_ascii=False)}}
            ]
        }
        return httpx.Response(200, json=body)

    kb = build_kb()
    agent = PaperUnderstandingAgent(kb, make_llm(handler), [])
    guide = await agent.run(PAPER_ID, "demo.pdf", trace_id="t1")

    assert guide.generator == "llm"
    assert guide.one_liner
    assert guide.method.content.startswith("采用Transformer")
    # US-02：主要结论附章节与页码
    assert guide.method.citations[0].page == 2
    assert guide.method.citations[0].section == "方法"
    # 越界页码引用应被丢弃（不得虚构）
    assert all(citation.page is None or citation.page <= 4 for citation in guide.results.citations)
    # 未说明项保持"原文未说明"且无引用
    assert guide.limitations.content == "原文未说明"
    assert guide.limitations.citations == []
    assert 3 <= len(guide.keywords) <= 8


@pytest.mark.asyncio
async def test_guide_falls_back_when_llm_fails():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "server down"}})

    kb = build_kb()
    logs = []
    agent = PaperUnderstandingAgent(kb, make_llm(handler), logs)
    # 模型服务5xx时不得抛异常，必须走提取式降级（US-02异常兜底）
    guide = await agent.run(PAPER_ID, "demo.pdf", trace_id="t2")

    assert guide.generator == "fallback"
    assert guide.overview
    assert guide.key_points
    assert "暂无法生成" in guide.background.content
    assert any(log.action == "llm-error" for log in logs)
