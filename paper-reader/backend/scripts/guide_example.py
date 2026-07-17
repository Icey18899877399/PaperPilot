"""US-02「论文智能导读」结果的规范化学术范例。

用途
====
1. **产出标准对齐**：本文件中的 ``EXAMPLE_GUIDE`` 是团队公认的"一份合格
   导读长什么样"——九项齐全、每项结论带章节页码引用、未说明项如实标注、
   措辞学术中性。评审导读质量或调试提示词时以此为参照。
2. **Schema一致性校验**：范例直接用 ``GuideResponse`` 模型构造，运行本
   脚本即可确认范例与后端数据模型始终同步（模型改字段时脚本会报错）。
3. **提示词few-shot素材**：``--format json`` 输出的JSON可直接作为
   few-shot示例拼入app/prompts/guide.py的新版本提示词。

用法（在backend目录下）::

    python scripts/guide_example.py                # 学术化Markdown渲染
    python scripts/guide_example.py --format json  # 模型输出格式的JSON
    python scripts/guide_example.py --output demo.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.schemas import GuideCitation, GuideResponse, GuideSection  # noqa: E402

# ---------------------------------------------------------------------------
# 规范化范例：取材于课程参考论文 2025.coling-main.353（OpenForecast），
# 所有内容与页码均来自论文原文，未说明项按验收标准如实标注。
# ---------------------------------------------------------------------------
EXAMPLE_GUIDE = GuideResponse(
    paper_id="example-openforecast",
    title="OpenForecast: A Large-Scale Open-Ended Event Forecasting Dataset",
    one_liner=(
        "OpenForecast构建了大规模开放式事件预测数据集，定义三项开放式任务，"
        "并提出基于LLM检索增强的自动评估方法LRAE。"
    ),
    overview=(
        "本文面向复杂事件预测的开放性需求，构建了包含43,419个复杂事件的"
        "开放式事件预测数据集OpenForecast，定义答案问答（AQA）、短期预测"
        "（STF）与长期预测（LTF）三项任务；提出全自动的数据集构建流水线"
        "（多步过滤、LLM驱动的两阶段事件时间线标注与问题生成），并设计"
        "LLM检索增强评估方法LRAE以缓解开放式答案的多对多匹配与低估问题。"
        "在多个主流大模型上的实验表明开放式任务显著难于封闭式设定，"
        "长期预测最具挑战性。"
    ),
    background=GuideSection(
        content=(
            "现有事件预测方法多为封闭式设定，受限于有限答案空间，"
            "难以刻画真实世界复杂事件的不可预见性、多面性与多步演化。"
        ),
        citations=[
            GuideCitation(section="Abstract", page=1),
            GuideCitation(section="1 Introduction", page=1),
        ],
    ),
    research_question=GuideSection(
        content=(
            "如何构建大规模开放式事件预测基准，并为开放式答案设计"
            "与人类判断一致的自动评估方法？"
        ),
        citations=[
            GuideCitation(section="1 Introduction", page=2),
            GuideCitation(section="3 Task Definition", page=3),
        ],
    ),
    method=GuideSection(
        content=(
            "从Wikipedia与WCEP收集复杂事件并多步过滤；用LLM进行两阶段"
            "事件时间线标注与问题生成，实现无人工标注的数据集构建；"
            "提出LRAE：以检索增强与LLM迭代验证完成开放式答案的语义匹配评分。"
        ),
        citations=[
            GuideCitation(section="4 Dataset Construction Pipeline", page=3),
            GuideCitation(section="5 LLM-based Retrieval-Augmented Evaluation", page=5),
        ],
    ),
    experiment=GuideSection(
        content=(
            "在OpenForecast上评估Llama2、Vicuna、Mixtral、Llama3等模型及其"
            "微调版本，与封闭式基线对比三项任务性能，并以人类评估验证"
            "LRAE与人工判断的一致性。"
        ),
        citations=[
            GuideCitation(section="6.1 Experimental Setup", page=6),
            GuideCitation(section="6.3 Experiments on LRAE", page=8),
        ],
    ),
    results=GuideSection(
        content=(
            "开放式任务显著难于封闭式任务；长期预测（LTF）最具挑战性，"
            "最佳模型F1仅50.7%；LRAE与人类评估的一致性优于既有自动指标。"
        ),
        citations=[
            GuideCitation(section="6.2 Main Results", page=6),
            GuideCitation(section="6.3 Experiments on LRAE", page=8),
        ],
    ),
    innovations=GuideSection(
        content=(
            "首次系统定义开放式事件预测任务（AQA/STF/LTF）；提出全自动"
            "数据集构建流水线；设计缓解开放式评估低估问题的LRAE方法。"
        ),
        citations=[
            GuideCitation(section="Abstract", page=1),
            GuideCitation(section="3 Task Definition", page=3),
        ],
    ),
    # 验收标准示范：论文片段未提及时如实标注，不补写、引用为空
    limitations=GuideSection(content="原文未说明", citations=[]),
    keywords=["事件预测", "开放式数据集", "OpenForecast", "LRAE", "大语言模型"],
    key_points=[
        "开放式事件预测与封闭式设定的本质差异是答案空间不受限",
        "数据集构建全程由LLM流水线完成，无需人工标注",
        "评估开放式生成答案需要语义级匹配而非表面重合",
    ],
    reading_questions=[
        "LRAE如何缓解开放式答案评估中的低估问题？",
        "两阶段事件时间线标注各解决什么质量风险？",
        "长期预测为何显著难于短期预测？",
    ],
    generator="llm",
    agent_trace_id="example-trace",
)

SECTION_ORDER = (
    ("background", "研究背景"),
    ("research_question", "研究问题"),
    ("method", "核心方法"),
    ("experiment", "实验设计"),
    ("results", "主要结果"),
    ("innovations", "创新点"),
    ("limitations", "局限性"),
)


def _format_citations(citations: list[GuideCitation]) -> str:
    if not citations:
        return ""
    rendered = "; ".join(
        f"{citation.section}, p.{citation.page}" if citation.page else citation.section
        for citation in citations
    )
    return f"（见 {rendered}）"


def render_markdown(guide: GuideResponse) -> str:
    """按学术阅读报告的体例渲染导读。"""
    lines = [
        f"# 《{guide.title}》智能导读",
        "",
        f"> **一句话概括**：{guide.one_liner}",
        "",
        f"**关键词**：{'；'.join(guide.keywords)}",
        "",
        "## 综述",
        "",
        guide.overview,
        "",
    ]
    for field, label in SECTION_ORDER:
        section: GuideSection = getattr(guide, field)
        lines.extend(
            [
                f"## {label}",
                "",
                f"{section.content}{_format_citations(section.citations)}",
                "",
            ]
        )
    lines.extend(["## 阅读重点", ""])
    lines.extend(f"{index}. {point}" for index, point in enumerate(guide.key_points, 1))
    lines.extend(["", "## 建议思考", ""])
    lines.extend(
        f"{index}. {question}"
        for index, question in enumerate(guide.reading_questions, 1)
    )
    lines.append("")
    return "\n".join(lines)


def render_model_json(guide: GuideResponse) -> str:
    """按提示词输出契约的字段渲染JSON，可直接作few-shot示例。"""
    payload = guide.model_dump(
        include={
            "one_liner",
            "background",
            "research_question",
            "method",
            "experiment",
            "results",
            "innovations",
            "limitations",
            "keywords",
            "overview",
            "key_points",
            "reading_questions",
        }
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="输出论文智能导读的规范化范例")
    parser.add_argument(
        "--format",
        choices=("md", "json"),
        default="md",
        help="md=学术化Markdown渲染；json=模型输出契约格式（few-shot素材）",
    )
    parser.add_argument("--output", type=Path, default=None, help="写入文件路径")
    args = parser.parse_args()

    rendered = (
        render_markdown(EXAMPLE_GUIDE)
        if args.format == "md"
        else render_model_json(EXAMPLE_GUIDE)
    )
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
        print(f"范例已写入：{args.output}")
    else:
        if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
            sys.stdout.reconfigure(encoding="utf-8")
        print(rendered)


if __name__ == "__main__":
    main()
