from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable

from app.models.schemas import PaperChunk
from app.services.vector_index import VectorIndex

# ---------------------------------------------------------------------------
# 展示分区识别：把 MinerU 原始版面块按阅读区域分为 body/author/reference/appendix，
# 供结构化切片页"默认隐藏非正文区、可切换显示全部"使用（不影响RAG检索层）。
# ---------------------------------------------------------------------------
_ABSTRACT_BOUNDARY = re.compile(r"^\s*(abstract\b|摘\s*要)", re.IGNORECASE)
_REFERENCE_HEADING = re.compile(r"^\s*(references?|bibliography|参考文献)\s*$", re.IGNORECASE)
_APPENDIX_HEADING = re.compile(r"^\s*(appendix\b|附录)", re.IGNORECASE)
# References 之后形如 "A Details" / "A.1 xxx" / "B.3 xxx" 的标题视为附录小节
_APPENDIX_SECTION = re.compile(r"^[A-Z](\.\d+)*[\s.]")


def classify_display_zones(chunks: list[PaperChunk]) -> dict[str, str]:
    """按阅读顺序给每个MinerU原始版面块标注展示分区。

    规则（保守，识别不出时一律归 body，宁可多显示不误藏）：
    - author：第1~2页、标题块之后、Abstract/摘要边界之前的文本块（作者/机构/邮箱区）；
      找不到 Abstract 边界时不标注任何 author；
    - reference：出现 "References/Bibliography/参考文献" 独立标题后的所有块；
    - appendix：出现 "Appendix/附录" 标题，或 References 区之后出现 "A.1 xxx" 式
      标题后的所有块；
    - 其余为 body。
    """
    zones: dict[str, str] = {}
    # 第一遍：定位标题块与 Abstract 边界（限前20块、前2页）
    first_text_index: int | None = None
    abstract_index: int | None = None
    for index, chunk in enumerate(chunks[:20]):
        if chunk.kind not in {"text", "list"} or chunk.page > 2:
            continue
        if first_text_index is None:
            first_text_index = index
            continue
        if _ABSTRACT_BOUNDARY.match(chunk.content.strip()):
            abstract_index = index
            break

    # 第二遍：顺序状态机
    zone = "body"
    for index, chunk in enumerate(chunks):
        content = chunk.content.strip()
        is_heading = chunk.metadata.get("text_level") is not None
        if zone == "body" and _REFERENCE_HEADING.match(content):
            zone = "reference"
        elif zone != "appendix" and is_heading and _APPENDIX_HEADING.match(content):
            zone = "appendix"
        elif zone == "reference" and is_heading and _APPENDIX_SECTION.match(content):
            zone = "appendix"

        current = zone
        if (
            zone == "body"
            and abstract_index is not None
            and first_text_index is not None
            and first_text_index < index < abstract_index
            and chunk.kind in {"text", "list"}
        ):
            current = "author"
        zones[chunk.chunk_id] = current
    return zones


# ---------------------------------------------------------------------------
# 正文延续块合并：修复"一句话被版面切成两块"的根因表现。
# PDF双栏/跨页排版会让 MinerU 把同一句话输出为两个相邻文本块；本函数在装载源切
# 片时按语言学信号把它们拼回完整段落。规则刻意保守，误合并的代价高于漏合并：
#   仅当【前块明显断在句中】且【后块明显是延续】才合并——
#   前块：末字符不是句末标点/冒号（剥掉引号括号后判断）；
#   后块：以小写拉丁字母或中文字符开头（大写开头视为新句/专名，不合并），
#         且不是 "3.2 xxx" 式编号标题；
#   两块都是无标题层级的 text 类、同页或相邻页、合并后不超长。
# 存储层仍保存 MinerU 原始块（可追溯），合并只发生在内存装载时。
# ---------------------------------------------------------------------------
_TERMINAL_CHARS = set("。．.!?！？；;…")
_COLON_CHARS = set("：:")
_CLOSING_CHARS = set("\"'”’』」)]）》〉】")
_NUMBERED_HEADING_START = re.compile(r"^\d+(\.\d+)*\s+\S")
_MERGED_MAX_CHARS = 2400


def _is_cjk(char: str) -> bool:
    return "一" <= char <= "鿿"


def _ends_mid_sentence(text: str) -> bool:
    stripped = text.rstrip()
    while stripped and stripped[-1] in _CLOSING_CHARS:
        stripped = stripped[:-1].rstrip()
    if not stripped:
        return False
    last = stripped[-1]
    return last not in _TERMINAL_CHARS and last not in _COLON_CHARS


def _continuation_start(text: str) -> bool:
    stripped = text.lstrip()
    if not stripped:
        return False
    first = stripped[0]
    return first.islower() or _is_cjk(first)


def _ends_with_comma(text: str) -> bool:
    """前块以逗号/顿号结尾＝句子必然未完，此时允许延续块以大写专名开头。"""
    stripped = text.rstrip()
    while stripped and stripped[-1] in _CLOSING_CHARS:
        stripped = stripped[:-1].rstrip()
    return bool(stripped) and stripped[-1] in ",，、"


def _join_continuation(left: str, right: str) -> str:
    left_part, right_part = left.rstrip(), right.lstrip()
    # 连字符断词：exam- + ple → example
    if left_part.endswith("-") and right_part[:1].islower():
        return left_part[:-1] + right_part
    # 中文之间不加空格，拉丁词之间补一个空格
    if (left_part and _is_cjk(left_part[-1])) or (right_part and _is_cjk(right_part[0])):
        return left_part + right_part
    return f"{left_part} {right_part}"


def merge_continuation_blocks(chunks: list[PaperChunk]) -> list[PaperChunk]:
    """把被跨栏/跨页切断的正文延续块合并回完整段落（不修改传入对象）。"""
    merged: list[PaperChunk] = []
    for chunk in chunks:
        previous = merged[-1] if merged else None
        can_merge = (
            previous is not None
            and previous.kind == "text"
            and chunk.kind == "text"
            and previous.metadata.get("text_level") is None
            and chunk.metadata.get("text_level") is None
            and 0 <= chunk.page - previous.page <= 1
            and len(previous.content) + len(chunk.content) <= _MERGED_MAX_CHARS
            and _ends_mid_sentence(previous.content)
            and (
                _continuation_start(chunk.content)
                # 逗号结尾的断句延续确定无疑，放行大写专名开头（如 "…method," + "LRAE, …"）
                or _ends_with_comma(previous.content)
            )
            and not _NUMBERED_HEADING_START.match(chunk.content.strip())
        )
        if can_merge:
            target = previous
            if not target.metadata.get("merged_continuation"):
                # 写时复制，避免污染调用方（存储层保存的仍是原始块）
                target = previous.model_copy(deep=True)
                target.metadata["merged_continuation"] = True
                target.metadata["merged_chunk_ids"] = [previous.chunk_id]
                merged[-1] = target
            target.content = _join_continuation(target.content, chunk.content)
            target.metadata["merged_chunk_ids"].append(chunk.chunk_id)
            if chunk.page != target.page:
                # 跨页合并后原 bbox 不再覆盖全部内容，置空避免误导定位高亮
                target.bbox = None
            continue
        merged.append(chunk)
    return merged


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

    # 融合检索权重与阈值（US-04：关键词检索与向量检索融合并重排序）
    KEYWORD_WEIGHT = 0.55
    VECTOR_WEIGHT = 0.45
    VECTOR_CANDIDATE_THRESHOLD = 0.15
    # RRF(倒数排名融合)常数，值越大越弱化头部排名的悬殊、结果更平滑
    RRF_K = 60
    # MMR(最大边际相关)：λ越大越偏相关度、越小越偏多样性；用于抑制同章节/近重复霸屏
    MMR_LAMBDA = 0.7

    def __init__(self, vector_index: VectorIndex | None = None) -> None:
        self._source_chunks: dict[str, list[PaperChunk]] = defaultdict(list)
        self._retrieval_chunks: dict[str, list[PaperChunk]] = defaultdict(list)
        # 每个检索切片的预计算词项：paper_id -> {chunk_id: (正文词项, 章节词项)}
        self._chunk_terms: dict[str, dict[str, tuple[set[str], set[str]]]] = {}
        # 未显式注入时使用无持久化的本地TF-IDF索引，保证测试与脚本可独立运行
        self.vector_index = vector_index or VectorIndex()

    def index(self, paper_id: str, chunks: list[PaperChunk]) -> None:
        # 装载时规范化MinerU原始版面块（存储层仍保留原始记录，已解析论文
        # 只需重启即可受益，无需重新解析）：
        # ① 剔除孤立页码与页眉页脚等重复噪音块（此前只在检索层过滤，展示层漏掉了）
        boilerplate = self._repeated_boilerplate(chunks)
        cleaned = [
            chunk
            for chunk in chunks
            if not (
                chunk.kind in {"text", "list"} and self._is_noise(chunk, boilerplate)
            )
        ]
        # ② 合并被跨栏/跨页切断的正文延续块（噪音先剔除，跨页断句才能重新相邻）
        source_chunks = merge_continuation_blocks(cleaned)
        self._source_chunks[paper_id] = source_chunks
        retrieval = self._build_retrieval_chunks(paper_id, source_chunks)
        self._retrieval_chunks[paper_id] = retrieval
        # 索引时预计算每个切片的词项集合，避免检索时对每个切片重复分词（US-04性能优化）
        self._chunk_terms[paper_id] = {
            chunk.chunk_id: (
                self._terms(f"{self._kind_words(chunk.kind)} {chunk.content}"),
                self._terms(
                    " ".join(str(value) for value in chunk.metadata.get("section_path", []))
                ),
            )
            for chunk in retrieval
        }
        # 同步重建向量索引；VectorIndex内部先删后建，重解析不会产生重复索引
        self.vector_index.index(paper_id, retrieval)

    def all_chunks(self, paper_id: str) -> list[PaperChunk]:
        """Return unmodified parser blocks for layout-aware user interfaces."""

        return list(self._source_chunks.get(paper_id, []))

    def retrieval_chunks(self, paper_id: str) -> list[PaperChunk]:
        """Return normalized chunks used by guide generation and retrieval."""

        return list(self._retrieval_chunks.get(paper_id, []))

    def remove(self, paper_id: str) -> None:
        self._source_chunks.pop(paper_id, None)
        self._retrieval_chunks.pop(paper_id, None)
        self._chunk_terms.pop(paper_id, None)
        # 删除论文时同步删除向量索引（AC US-04）
        self.vector_index.remove(paper_id)

    def search(self, paper_id: str, query: str, limit: int = 5) -> list[PaperChunk]:
        return [chunk for _, chunk in self.search_scored(paper_id, query, limit)]

    def search_scored(
        self,
        paper_id: str,
        query: str,
        limit: int = 5,
    ) -> list[tuple[float, PaperChunk]]:
        """关键词与向量融合检索，返回(相关度, 切片)并按相关度降序。

        基于US-04验收标准：关键词检索与向量检索融合并重排序；检索测试
        能够展示召回片段及相关度。零匹配时返回空列表而不是论文开头切片，
        使聊天Agent可以正确回答"当前论文证据不足"（US-05 AC-05-02）。
        """
        query_terms = self._terms(query)
        requested_kinds = self._requested_kinds(query)
        query_requests_references = any(
            keyword in query.lower()
            for keyword in ("参考文献", "引用", "reference", "bibliography", "citation")
        )
        chunks = self._retrieval_chunks.get(paper_id, [])
        if not chunks:
            return []

        vector_scores = self.vector_index.search(paper_id, query)
        term_cache = self._chunk_terms.get(paper_id, {})

        keyword_scores: dict[str, float] = {}
        for chunk in chunks:
            cached = term_cache.get(chunk.chunk_id)
            if cached is None:
                # 兜底：切片未进缓存时即时计算（正常路径不会走到）
                text_terms = self._terms(f"{self._kind_words(chunk.kind)} {chunk.content}")
                section_terms = self._terms(
                    " ".join(str(value) for value in chunk.metadata.get("section_path", []))
                )
            else:
                text_terms, section_terms = cached
            overlap = len(query_terms & text_terms)
            section_bonus = len(query_terms & section_terms) * 2
            phrase_bonus = 2 if query.lower() in chunk.content.lower() else 0
            kind_bonus = 4 if chunk.kind in requested_kinds else 0
            reference_penalty = (
                -3
                if chunk.metadata.get("is_reference") and not query_requests_references
                else 0
            )
            keyword_scores[chunk.chunk_id] = float(
                overlap + section_bonus + phrase_bonus + kind_bonus + reference_penalty
            )

        # 基于US-04优化：改用RRF(倒数排名融合)代替加权和。两路检索各自按分值排名，
        # 再按 KEYWORD_WEIGHT/(K+rank) + VECTOR_WEIGHT/(K+rank) 融合——只看排名不看
        # 分值绝对尺度，避免"关键词按最大值归一、向量用原始余弦"两种不可比尺度直接
        # 相加导致的排序失真；两路都未命中的切片自然得0分、被排除（保持零命中返回空）。
        keyword_ranking = sorted(
            (cid for cid, score in keyword_scores.items() if score > 0),
            key=lambda cid: keyword_scores[cid],
            reverse=True,
        )
        keyword_rank = {cid: rank for rank, cid in enumerate(keyword_ranking, start=1)}
        vector_ranking = sorted(
            (
                cid
                for cid, score in vector_scores.items()
                if score >= self.VECTOR_CANDIDATE_THRESHOLD
            ),
            key=lambda cid: vector_scores[cid],
            reverse=True,
        )
        vector_rank = {cid: rank for rank, cid in enumerate(vector_ranking, start=1)}

        results: list[tuple[float, PaperChunk]] = []
        for chunk in chunks:
            cid = chunk.chunk_id
            if cid not in keyword_rank and cid not in vector_rank:
                continue
            fused = 0.0
            if cid in keyword_rank:
                fused += self.KEYWORD_WEIGHT / (self.RRF_K + keyword_rank[cid])
            if cid in vector_rank:
                fused += self.VECTOR_WEIGHT / (self.RRF_K + vector_rank[cid])
            results.append((fused, chunk))

        results.sort(key=lambda item: item[0], reverse=True)
        # 基于US-04优化：对候选做MMR重排去重，避免同章节/重叠切分产生的近重复
        # 片段霸占top-k，提升召回覆盖面（聊天证据更全面）。候选池取宽一些供挑选。
        pool = results[: max(limit * 4, 20)]
        selected = self._mmr_select(paper_id, pool, limit)

        scored_hits: list[tuple[float, PaperChunk]] = []
        for rank, (score, chunk) in enumerate(selected, start=1):
            # 返回副本并写入相关度，避免不同查询的分数互相污染知识库内的切片
            hit = chunk.model_copy(deep=True)
            hit.metadata["retrieval_score"] = round(score, 6)
            hit.metadata["retrieval_rank"] = rank
            scored_hits.append((round(score, 6), hit))
        return scored_hits

    def _mmr_select(
        self,
        paper_id: str,
        pool: list[tuple[float, PaperChunk]],
        limit: int,
    ) -> list[tuple[float, PaperChunk]]:
        """MMR贪心选取：每步选 λ·相关度 −(1−λ)·与已选最大相似度 最高的候选。

        pool已按相关度降序。返回数不超过limit的候选（保持"零命中返回空"）；
        候选不多于limit时无需去重，直接按相关度返回。
        """
        if len(pool) <= limit:
            return pool
        max_rel = pool[0][0] or 1.0
        selected: list[tuple[float, PaperChunk]] = []
        remaining = list(pool)
        while remaining and len(selected) < limit:
            best_index = 0
            best_mmr = None
            for index, (relevance, chunk) in enumerate(remaining):
                relevance_norm = relevance / max_rel if max_rel else 0.0
                if selected:
                    max_similarity = max(
                        self._chunk_similarity(paper_id, chunk, chosen)
                        for _, chosen in selected
                    )
                else:
                    max_similarity = 0.0
                mmr = (
                    self.MMR_LAMBDA * relevance_norm
                    - (1 - self.MMR_LAMBDA) * max_similarity
                )
                if best_mmr is None or mmr > best_mmr:
                    best_mmr = mmr
                    best_index = index
            selected.append(remaining.pop(best_index))
        return selected

    def _chunk_similarity(self, paper_id: str, left: PaperChunk, right: PaperChunk) -> float:
        """切片间相似度：正文词项Jaccard + 同末级章节信号（复用预计算词项缓存）。"""
        terms = self._chunk_terms.get(paper_id, {})
        left_terms = terms.get(left.chunk_id, (set(), set()))[0]
        right_terms = terms.get(right.chunk_id, (set(), set()))[0]
        union = left_terms | right_terms
        jaccard = len(left_terms & right_terms) / len(union) if union else 0.0
        left_section = left.metadata.get("section_path") or []
        right_section = right.metadata.get("section_path") or []
        same_section = (
            bool(left_section)
            and bool(right_section)
            and left_section[-1] == right_section[-1]
        )
        # 同章节near-dup是本次要压制的主要场景，给予较强相似度权重
        return 0.5 * jaccard + (0.5 if same_section else 0.0)

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
        # \u57fa\u4e8eUS-04\u4f18\u5316\uff1a\u4e2d\u6587\u7531\u5355\u5b57\u6539\u4e3a\u4e8c\u5143\u7ec4\uff0c\u4e0e\u5411\u91cf\u7d22\u5f15\u5206\u8bcd\u4fdd\u6301\u4e00\u81f4\u3002
        # \u5355\u5b57\u4f1a\u8ba9"\u7684/\u662f/\u5ea6"\u7b49\u9ad8\u9891\u5b57\u4e0e\u4efb\u610f\u4e2d\u6587\u5207\u7247\u4f2a\u5339\u914d\uff0c\u5bfc\u81f4\u65e0\u5173\u95ee\u9898
        # \u4e5f\u80fd\u53ec\u56de\u5185\u5bb9\uff0c\u7834\u574f"\u8bc1\u636e\u4e0d\u8db3"\u5224\u5b9a\uff08US-05 AC-05-02\uff09
        latin = re.findall(r"[a-zA-Z0-9_]{2,}", text.lower())
        chinese = re.findall(r"[\u4e00-\u9fff]", text)
        bigrams = [
            chinese[index] + chinese[index + 1]
            for index in range(len(chinese) - 1)
        ]
        if len(chinese) == 1:
            bigrams = chinese
        return set(latin + bigrams)

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
