"""Visual query classification and dedicated analysis prompts for US-07.

Kept separate from the agent so prompts can be tuned without touching
agent logic, and classification can be reused by chat.py.  """

import re

# ── visual keyword detection ─────────────────────────────────────

# Regex patterns for explicit element references
_FIGURE_RE = re.compile(
    r"(?:图|Fig(?:ure)?\.?)\s*(\d+)",
    re.IGNORECASE,
)
_TABLE_RE = re.compile(
    r"(?:表|Table\.?)\s*(\d+)",
    re.IGNORECASE,
)
_EQUATION_RE = re.compile(
    r"(?:公式|Equation|Eq\.?|Eqn\.?)\s*[\(（]?\s*(\d+)\s*[\)）]?",
    re.IGNORECASE,
)

# Keywords that indicate a visual query (no specific number)
_IMAGE_KEYWORDS = [
    "图", "图表", "图片", "图像", "曲线图", "柱状图", "饼图", "折线图",
    "散点图", "热力图", "示意图", "流程图", "架构图", "框图",
    "figure", "chart", "graph", "plot", "diagram", "image",
]
_TABLE_KEYWORDS = ["表", "表格", "数据表", "table"]
_EQUATION_KEYWORDS = [
    "公式", "方程", "算式", "equation", "formula", "latex",
]


def is_visual_query(question: str) -> bool:
    """Return True if the question targets visual content."""
    lowered = question.lower()
    for kw in _IMAGE_KEYWORDS + _TABLE_KEYWORDS + _EQUATION_KEYWORDS:
        if kw in lowered:
            return True
    return False


def classify_query(question: str) -> dict:
    """Extract target kind and reference number.

    Returns: {"kind": "image"|"table"|"equation"|None, "ref": str|None}
    """
    lowered = question.lower()

    m = _FIGURE_RE.search(question)
    if m:
        return {"kind": "image", "ref": m.group(1)}

    m = _TABLE_RE.search(question)
    if m:
        return {"kind": "table", "ref": m.group(1)}

    m = _EQUATION_RE.search(question)
    if m:
        return {"kind": "equation", "ref": m.group(1)}

    if any(kw in lowered for kw in _TABLE_KEYWORDS):
        return {"kind": "table", "ref": None}
    if any(kw in lowered for kw in _EQUATION_KEYWORDS):
        return {"kind": "equation", "ref": None}
    if any(kw in lowered for kw in _IMAGE_KEYWORDS):
        return {"kind": "image", "ref": None}

    return {"kind": None, "ref": None}


# ── dedicated system prompts ─────────────────────────────────────

_EVIDENCE_RULE = (
    "【关键规则】如果提供的视觉内容数据与用户问题完全无关，或数据不足以做"
    "出任何可靠分析，你必须只回复一行：INSUFFICIENT_EVIDENCE\n"
    "不得编造、猜测或输出任何其他内容。\n"
)

IMAGE_SYSTEM_PROMPT = (
    "你是视觉内容分析Agent，专门分析论文中的图片和图表。"
    "严格遵循以下规则：\n"
    "1. 你只能依据下方提供的「视觉内容数据」进行分析，严禁编造。\n"
    "2. 按以下结构组织回答：\n"
    "   📌 先一句话概括该图/表的主题。\n"
    "   ● 图表类型（如流程图/柱状图/架构图）。\n"
    "   ● 关键元素与模块（逐一说明各组成部分的含义）。\n"
    "   ● 核心信息（该图传达的主要发现或结论）。\n"
    "3. 每条结论标注【第X页】，不确定处明确说「无法确定」。\n"
    "4. 使用中文回答。\n"
    + _EVIDENCE_RULE
)

TABLE_SYSTEM_PROMPT = (
    "你是视觉内容分析Agent，专门分析论文中的表格数据。"
    "严格遵循以下规则：\n"
    "1. 你只能依据下方提供的「表格数据」进行分析，严禁编造数值。\n"
    "2. 按以下结构组织回答：\n"
    "   📌 一句话说明该表格的用途。\n"
    "   ● 表头/列含义（逐一解释每列代表什么）。\n"
    "   ● 关键数据对比（引用原文数值，标注单位）。\n"
    "   ● 主要发现/趋势（从数据中得出的结论）。\n"
    "3. 引用的数值必须与原数据一致，每条结论标注【第X页】。\n"
    "4. 使用中文回答。\n"
    + _EVIDENCE_RULE
)

EQUATION_SYSTEM_PROMPT = (
    "你是视觉内容分析Agent，专门分析论文中的数学公式。"
    "严格遵循以下规则：\n"
    "1. 你只能依据下方提供的「公式数据」进行分析，严禁编造。\n"
    "2. 按以下结构组织回答：\n"
    "   📌 一句话说明该公式的用途。\n"
    "   ● LaTeX原文（先给出完整公式）。\n"
    "   ● 符号含义（逐项解释每个符号代表什么）。\n"
    "   ● 公式含义的自然语言描述。\n"
    "3. 每条结论标注【第X页】，不确定处明确说「无法确定」。\n"
    "4. 使用中文回答。\n"
    + _EVIDENCE_RULE
)

MIXED_SYSTEM_PROMPT = (
    "你是视觉内容分析Agent，专门分析论文中的图片、图表、表格和公式。"
    "严格遵循以下规则：\n"
    "1. 你只能依据下方提供的「视觉内容数据」进行分析，严禁编造。\n"
    "2. 按以下结构组织回答：\n"
    "   📌 先总体概括。\n"
    "   ● 逐一分析每个视觉元素（图片说明类型和关键信息，表格说明表头和关键数据，公式给出LaTeX和符号解释）。\n"
    "3. 每条结论标注【第X页】，不确定处明确说「无法确定」。\n"
    "4. 使用中文回答。\n"
    + _EVIDENCE_RULE
)


def select_prompt(kind: str | None) -> str:
    """Return the right system prompt for the target kind."""
    if kind == "equation":
        return EQUATION_SYSTEM_PROMPT
    if kind == "table":
        return TABLE_SYSTEM_PROMPT
    if kind == "image":
        return IMAGE_SYSTEM_PROMPT
    return MIXED_SYSTEM_PROMPT


# ── kind display names ────────────────────────────────────────────

KIND_NAMES: dict[str, str] = {
    "image": "图片",
    "chart": "图表",
    "table": "表格",
    "equation": "公式",
    "code": "代码",
    "list": "列表",
    "text": "正文",
}


def kind_name(kind: str | None) -> str:
    return KIND_NAMES.get(kind or "", "视觉元素")