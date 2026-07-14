from __future__ import annotations

import re

from app.agents.base import BaseAgent
from app.models.schemas import (
    ChunkExplanationResponse,
    GuideResponse,
    MindMapBranch,
    MindMapResponse,
    MindMapSubBranch,
    PaperChunk,
)
from app.services.knowledge_base import KnowledgeBase
from app.services.llm import LLMClient


class PaperUnderstandingAgent(BaseAgent):
    name = "paper-understanding-agent"

    def __init__(self, kb: KnowledgeBase, llm: LLMClient, log_sink):
        super().__init__(log_sink)
        self.kb = kb
        self.llm = llm

    async def run(self, paper_id: str, filename: str, trace_id: str) -> GuideResponse:
        chunks = self.kb.retrieval_chunks(paper_id)
        self.log(trace_id, "read-paper", f"读取{len(chunks)}个检索切片")
        context = "\n\n".join(chunk.content for chunk in chunks[:8])[:10000]
        generated = await self.llm.complete_json(
            (
                "你是论文理解Agent。只输出JSON对象，字段必须为overview、"
                "key_points、reading_questions；overview是中文概述，"
                "后两个字段都是恰好包含3个中文字符串的数组。"
            ),
            f"论文文件名：{filename}\n\n论文内容：\n{context}",
        )
        if generated:
            overview = str(generated.get("overview", "")).strip()
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
            if not overview or not key_points or not questions:
                generated = None
        if not generated:
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
        self.log(trace_id, "generate-guide", "生成论文智能导读")
        return GuideResponse(
            paper_id=paper_id,
            title=filename.removesuffix(".pdf"),
            overview=overview,
            key_points=key_points,
            reading_questions=questions,
            agent_trace_id=trace_id,
        )

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
        kind_label = {
            "image": "图片",
            "chart": "图表",
            "table": "表格",
            "equation": "公式",
            "code": "代码",
            "list": "列表",
        }.get(chunk.kind, "正文")
        explanation = await self.llm.complete(
            (
                "你是论文精读Agent。仅依据给定切片，用中文解释它在论文中的含义。"
                "先概括切片表达的内容，再说明关键术语、数据或关系，最后给出阅读时应关注的结论。"
                "表格需要解释行列含义、主要比较和显著数据；图表需要解释趋势与结论。"
                "不要虚构切片中没有的信息，控制在220字以内。"
            ),
            (
                f"论文：{filename}\n"
                f"位置：第{chunk.page}页，类型：{kind_label}\n\n"
                f"切片内容：\n{chunk.content[:12000]}"
            ),
            max_tokens=700,
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

    @staticmethod
    def _sentences(text: str) -> list[str]:
        candidates = re.split(r"(?<=[。！？.!?])\s+|\n+", text)
        return [
            sentence.strip()
            for sentence in candidates
            if 45 <= len(sentence.strip()) <= 500
        ]
