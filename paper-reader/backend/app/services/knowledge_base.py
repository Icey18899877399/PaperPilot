from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable

from app.models.schemas import PaperChunk


class KnowledgeBase:
    """Keep MinerU display blocks separate from retrieval-oriented chunks.

    MinerU blocks retain their original page, bbox and media metadata for the
    structured-content and bilingual-reading views. Search uses a second layer
    that merges short neighbouring blocks, carries section headings forward,
    and splits oversized blocks at sentence boundaries with overlap.
    """

    TARGET_CHARS = 1200
    MAX_CHARS = 1600
    MIN_CHARS = 120
    OVERLAP_CHARS = 180
    HEADING_MAX_CHARS = 240
    SECTION_PREFIX_MAX_CHARS = 320

    def __init__(self) -> None:
        self._source_chunks: dict[str, list[PaperChunk]] = defaultdict(list)
        self._retrieval_chunks: dict[str, list[PaperChunk]] = defaultdict(list)

    def index(self, paper_id: str, chunks: list[PaperChunk]) -> None:
        source_chunks = list(chunks)
        self._source_chunks[paper_id] = source_chunks
        self._retrieval_chunks[paper_id] = self._build_retrieval_chunks(
            paper_id,
            source_chunks,
        )

    def all_chunks(self, paper_id: str) -> list[PaperChunk]:
        """Return unmodified parser blocks for layout-aware user interfaces."""

        return list(self._source_chunks.get(paper_id, []))

    def retrieval_chunks(self, paper_id: str) -> list[PaperChunk]:
        """Return normalized chunks used by guide generation and retrieval."""

        return list(self._retrieval_chunks.get(paper_id, []))

    def remove(self, paper_id: str) -> None:
        self._source_chunks.pop(paper_id, None)
        self._retrieval_chunks.pop(paper_id, None)

    def search(self, paper_id: str, query: str, limit: int = 5) -> list[PaperChunk]:
        query_terms = self._terms(query)
        requested_kinds = self._requested_kinds(query)
        query_requests_references = any(
            keyword in query.lower()
            for keyword in ("参考文献", "引用", "reference", "bibliography", "citation")
        )
        chunks = self._retrieval_chunks.get(paper_id, [])
        scored: list[tuple[int, PaperChunk]] = []
        for chunk in chunks:
            text_terms = self._terms(f"{self._kind_words(chunk.kind)} {chunk.content}")
            section_terms = self._terms(
                " ".join(str(value) for value in chunk.metadata.get("section_path", []))
            )
            overlap = len(query_terms & text_terms)
            section_bonus = len(query_terms & section_terms) * 2
            phrase_bonus = 2 if query.lower() in chunk.content.lower() else 0
            kind_bonus = 4 if chunk.kind in requested_kinds else 0
            reference_penalty = (
                -3
                if chunk.metadata.get("is_reference") and not query_requests_references
                else 0
            )
            scored.append(
                (
                    overlap
                    + section_bonus
                    + phrase_bonus
                    + kind_bonus
                    + reference_penalty,
                    chunk,
                )
            )
        scored.sort(key=lambda item: item[0], reverse=True)
        positive = [chunk for score, chunk in scored if score > 0]
        return (positive or chunks)[:limit]

    def _build_retrieval_chunks(
        self,
        paper_id: str,
        chunks: list[PaperChunk],
    ) -> list[PaperChunk]:
        if not chunks:
            return []

        boilerplate = self._repeated_boilerplate(chunks)
        result: list[PaperChunk] = []
        headings: list[str] = []
        buffer: list[PaperChunk] = []
        buffer_chars = 0
        buffer_page: int | None = None
        buffer_section: tuple[str, ...] = ()

        def flush_buffer() -> None:
            nonlocal buffer, buffer_chars, buffer_page, buffer_section
            if buffer:
                body = "\n".join(chunk.content.strip() for chunk in buffer if chunk.content.strip())
                if body:
                    result.append(
                        self._make_retrieval_chunk(
                            paper_id,
                            len(result) + 1,
                            buffer,
                            body,
                            buffer_section,
                        )
                    )
            buffer = []
            buffer_chars = 0
            buffer_page = None
            buffer_section = ()

        for source in chunks:
            content = source.content.strip()
            if not content:
                continue

            heading_level = self._heading_level(source)
            if heading_level is not None:
                flush_buffer()
                headings = self._update_heading_path(headings, heading_level, content)
                continue

            if self._is_noise(source, boilerplate):
                continue

            section = tuple(value for value in headings if value)
            if source.kind not in {"text", "list"}:
                flush_buffer()
                for part in self._split_text(
                    content,
                    self._body_budget(section),
                ):
                    result.append(
                        self._make_retrieval_chunk(
                            paper_id,
                            len(result) + 1,
                            [source],
                            part,
                            section,
                            kind=source.kind,
                        )
                    )
                continue

            if len(content) > self._body_budget(section):
                flush_buffer()
                for part in self._split_text(
                    content,
                    self._body_budget(section),
                ):
                    result.append(
                        self._make_retrieval_chunk(
                            paper_id,
                            len(result) + 1,
                            [source],
                            part,
                            section,
                            kind=source.kind,
                        )
                    )
                continue

            page_changed = buffer_page is not None and source.page != buffer_page
            section_changed = bool(buffer) and section != buffer_section
            would_exceed_target = (
                bool(buffer)
                and buffer_chars + len(content) + 1 > self.TARGET_CHARS
                and buffer_chars >= self.MIN_CHARS
            )
            if page_changed or section_changed or would_exceed_target:
                flush_buffer()

            if not buffer:
                buffer_page = source.page
                buffer_section = section
            buffer.append(source)
            buffer_chars += len(content) + 1

        flush_buffer()
        return result

    def _make_retrieval_chunk(
        self,
        paper_id: str,
        sequence: int,
        sources: list[PaperChunk],
        body: str,
        section: tuple[str, ...],
        *,
        kind: str | None = None,
    ) -> PaperChunk:
        source_ids = [chunk.chunk_id for chunk in sources]
        pages = [chunk.page for chunk in sources]
        effective_kind = kind or (
            sources[0].kind if all(chunk.kind == sources[0].kind for chunk in sources) else "text"
        )
        prefix = self._section_prefix(section)
        resource_url = next(
            (chunk.resource_url for chunk in sources if chunk.resource_url),
            None,
        )
        bbox = self._union_bbox(sources) if len(set(pages)) == 1 else None
        is_reference = self._is_reference_section(section)
        return PaperChunk(
            chunk_id=f"{paper_id}-r{sequence}",
            paper_id=paper_id,
            page=min(pages),
            kind=effective_kind,
            content=f"{prefix}{body}".strip(),
            resource_url=resource_url,
            bbox=bbox,
            metadata={
                "parser": "retrieval-postprocessor",
                "section_path": list(section),
                "source_chunk_ids": source_ids,
                "page_start": min(pages),
                "page_end": max(pages),
                "is_reference": is_reference,
            },
        )

    def _split_text(self, text: str, max_chars: int | None = None) -> list[str]:
        max_chars = max_chars or self.MAX_CHARS
        text = re.sub(r"[ \t]+", " ", text).strip()
        if len(text) <= max_chars:
            return [text]

        sentences = [
            item.strip()
            for item in re.split(r"(?<=[。！？.!?；;])\s+|\n+", text)
            if item.strip()
        ]
        if not sentences:
            sentences = [text]

        units: list[str] = []
        for sentence in sentences:
            if len(sentence) <= max_chars:
                units.append(sentence)
                continue
            units.extend(self._hard_split(sentence, max_chars))

        parts: list[str] = []
        current = ""
        for unit in units:
            candidate = f"{current} {unit}".strip()
            if current and len(candidate) > max_chars:
                parts.append(current)
                overlap = self._overlap_tail(current)
                current = f"{overlap} {unit}".strip()
                if len(current) > max_chars:
                    overflow = self._hard_split(current, max_chars)
                    parts.extend(overflow[:-1])
                    current = overflow[-1]
            else:
                current = candidate
        if current:
            if (
                parts
                and len(current) < self.MIN_CHARS
                and len(parts[-1]) + len(current) + 1 <= max_chars
            ):
                parts[-1] = f"{parts[-1]} {current}".strip()
            else:
                parts.append(current)
        return parts

    def _body_budget(self, section: tuple[str, ...]) -> int:
        return max(
            self.MIN_CHARS,
            self.MAX_CHARS - len(self._section_prefix(section)),
        )

    def _section_prefix(self, section: tuple[str, ...]) -> str:
        if not section:
            return ""
        label = f"章节：{' > '.join(section)}"
        if len(label) > self.SECTION_PREFIX_MAX_CHARS:
            label = f"章节：…{label[-(self.SECTION_PREFIX_MAX_CHARS - 4):]}"
        return f"{label}\n"

    @staticmethod
    def _hard_split(text: str, size: int) -> list[str]:
        words = text.split()
        if len(words) <= 1:
            return [text[start : start + size] for start in range(0, len(text), size)]
        parts: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and len(candidate) > size:
                parts.append(current)
                current = word
            else:
                current = candidate
        if current:
            parts.append(current)
        return parts

    def _overlap_tail(self, text: str) -> str:
        if len(text) <= self.OVERLAP_CHARS:
            return text
        tail = text[-self.OVERLAP_CHARS :]
        first_space = tail.find(" ")
        return tail[first_space + 1 :] if first_space >= 0 else tail

    @classmethod
    def _heading_level(cls, chunk: PaperChunk) -> int | None:
        if chunk.kind not in {"text", "list"} or len(chunk.content.strip()) > cls.HEADING_MAX_CHARS:
            return None
        value = chunk.metadata.get("text_level")
        if value is None:
            return None
        try:
            return max(1, min(6, int(value)))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _update_heading_path(path: list[str], level: int, heading: str) -> list[str]:
        updated = list(path[: max(0, level - 1)])
        while len(updated) < level - 1:
            updated.append("")
        updated.append(heading.strip())
        return updated

    @classmethod
    def _repeated_boilerplate(cls, chunks: Iterable[PaperChunk]) -> set[str]:
        occurrences: dict[str, set[int]] = defaultdict(set)
        for chunk in chunks:
            content = chunk.content.strip()
            if (
                chunk.kind not in {"text", "list"}
                or cls._heading_level(chunk) is not None
                or not content
                or len(content) > 80
            ):
                continue
            normalized = cls._normalize_noise(content)
            if normalized:
                occurrences[normalized].add(chunk.page)
        return {
            value
            for value, pages in occurrences.items()
            if len(pages) >= 3
        }

    @classmethod
    def _is_noise(cls, chunk: PaperChunk, repeated: set[str]) -> bool:
        content = chunk.content.strip()
        if re.fullmatch(r"(?:page\s*)?\d{1,5}", content, flags=re.IGNORECASE):
            return True
        return cls._normalize_noise(content) in repeated

    @staticmethod
    def _normalize_noise(text: str) -> str:
        return re.sub(r"[^\w\u4e00-\u9fff]+", "", text.lower())

    @staticmethod
    def _union_bbox(chunks: Iterable[PaperChunk]) -> list[float] | None:
        boxes = [chunk.bbox for chunk in chunks if chunk.bbox and len(chunk.bbox) == 4]
        if not boxes:
            return None
        return [
            min(box[0] for box in boxes),
            min(box[1] for box in boxes),
            max(box[2] for box in boxes),
            max(box[3] for box in boxes),
        ]

    @staticmethod
    def _is_reference_section(section: tuple[str, ...]) -> bool:
        lowered = " ".join(section).lower()
        return any(
            keyword in lowered
            for keyword in ("references", "bibliography", "参考文献", "参考资料")
        )

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
