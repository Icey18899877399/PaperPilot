from __future__ import annotations

import re
from collections import defaultdict

from app.models.schemas import PaperChunk


class KnowledgeBase:
    """Replaceable retrieval boundary inspired by RAGFlow's dataset/retrieval split."""

    def __init__(self) -> None:
        self._chunks: dict[str, list[PaperChunk]] = defaultdict(list)

    def index(self, paper_id: str, chunks: list[PaperChunk]) -> None:
        self._chunks[paper_id] = chunks

    def all_chunks(self, paper_id: str) -> list[PaperChunk]:
        return list(self._chunks.get(paper_id, []))

    def remove(self, paper_id: str) -> None:
        self._chunks.pop(paper_id, None)

    def search(self, paper_id: str, query: str, limit: int = 5) -> list[PaperChunk]:
        query_terms = self._terms(query)
        requested_kinds = self._requested_kinds(query)
        chunks = self._chunks.get(paper_id, [])
        scored: list[tuple[int, PaperChunk]] = []
        for chunk in chunks:
            text_terms = self._terms(f"{self._kind_words(chunk.kind)} {chunk.content}")
            overlap = len(query_terms & text_terms)
            phrase_bonus = 2 if query.lower() in chunk.content.lower() else 0
            kind_bonus = 4 if chunk.kind in requested_kinds else 0
            scored.append((overlap + phrase_bonus + kind_bonus, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        positive = [chunk for score, chunk in scored if score > 0]
        return (positive or chunks)[:limit]

    @staticmethod
    def _terms(text: str) -> set[str]:
        latin = re.findall(r"[a-zA-Z0-9_]{2,}", text.lower())
        chinese = re.findall(r"[\u4e00-\u9fff]", text)
        return set(latin + chinese)

    @staticmethod
    def _kind_words(kind: str) -> str:
        return {
            "image": "图片 图像 figure image",
            "chart": "图表 曲线图 柱状图 chart figure",
            "table": "表格 数据 table",
            "equation": "公式 方程 数学 equation formula latex",
            "code": "代码 程序 code",
        }.get(kind, "正文 文字 text")

    @staticmethod
    def _requested_kinds(query: str) -> set[str]:
        lowered = query.lower()
        mapping = {
            "image": ("图片", "图像", "figure", "image"),
            "chart": ("图表", "曲线图", "柱状图", "chart"),
            "table": ("表格", "数据表", "table"),
            "equation": ("公式", "方程", "equation", "formula", "latex"),
            "code": ("代码", "程序", "code"),
        }
        return {
            kind
            for kind, keywords in mapping.items()
            if any(keyword in lowered for keyword in keywords)
        }
