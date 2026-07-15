"""LLM prompt formatting templates for chat responses.

Kept as a standalone module so templates can be iterated without touching
agent or route code. The chat route prepends these to the user question,
leaving ChatAgent unchanged.
"""

# ── chat response formatting ─────────────────────────────────────

CHAT_FORMATTING_INSTRUCTION = (
    "【格式要求 — 必须严格遵守】\n"
    "请使用以下结构组织你的回答，使内容清晰易读：\n"
    "\n"
    "1. 用「📌 核心要点」作为开头，用1-2句话总括回答。\n"
    "2. 每个分点用「●」开头，各分点之间留一个空行。\n"
    "3. 需要列举时使用「① ② ③」编号，不要使用Markdown编号。\n"
    "4. 引用原文内容时使用「」引号包裹，并标注【第X页】。\n"
    "5. 代码、公式、LaTeX 使用单独一行展示。\n"
    "6. 回答末尾用「---」分隔线，然后附上「💡 提示」1-2句话。\n"
    "\n"
    "示例格式：\n"
    "📌 核心要点：本文提出了...\n"
    "\n"
    "● 方法设计方面，「原文指出...」【第3页】\n"
    "\n"
    "● 实验结果表明：\n"
    "  ① 在数据集A上提升3.2%\n"
    "  ② 在数据集B上提升1.8%【第5页】\n"
    "\n"
    "---\n"
    "💡 提示：可进一步关注第4节的消融实验分析。\n"
    "\n"
    "（以上是格式要求。下面是实际问答内容）\n"
)