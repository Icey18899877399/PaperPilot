"""正文延续块合并（修复"一句话被版面切成两块"）测试。"""

from app.models.schemas import PaperChunk
from app.services.knowledge_base import KnowledgeBase, merge_continuation_blocks


def _c(cid, page, content, kind="text", heading=False):
    return PaperChunk(
        chunk_id=cid,
        paper_id="p",
        page=page,
        kind=kind,
        content=content,
        metadata={"text_level": 1 if heading else None},
    )


def test_merges_latin_sentence_split_across_columns():
    chunks = [
        _c("a", 3, "Existing methods are restricted to a limited"),
        _c("b", 3, "answer space and cannot handle complex events."),
    ]
    merged = merge_continuation_blocks(chunks)
    assert len(merged) == 1
    assert merged[0].content == (
        "Existing methods are restricted to a limited "
        "answer space and cannot handle complex events."
    )
    # 原对象不被修改（存储层保存的原始块不受污染）
    assert chunks[0].content.endswith("limited")
    assert merged[0].metadata["merged_chunk_ids"] == ["a", "b"]


def test_merges_hyphenated_word_and_cjk_without_space():
    latin = merge_continuation_blocks(
        [_c("a", 1, "this is an exam-"), _c("b", 1, "ple of hyphenation.")]
    )
    assert latin[0].content == "this is an exam-ple of hyphenation." or \
           latin[0].content == "this is an example of hyphenation."
    cjk = merge_continuation_blocks(
        [_c("a", 1, "事件预测的目标是根据背景信息"), _c("b", 2, "预测未来可能发生的事件。")]
    )
    assert len(cjk) == 1
    assert "背景信息预测未来" in cjk[0].content  # 中文合并不加空格


def test_does_not_merge_completed_sentences_or_headings():
    kept = merge_continuation_blocks(
        [
            _c("a", 1, "This sentence is complete."),
            _c("b", 1, "another paragraph starts here."),
            _c("h", 1, "3.2 Experimental Setup"),
            _c("c", 1, "OpenForecast: A Large-Scale Dataset"),
            _c("d", 1, "Zhen Wang, Xi Zhou, Yating Yang"),
        ]
    )
    # 句号结尾不合并；编号标题不被吸收；标题/作者行（大写开头）不合并
    assert [x.chunk_id for x in kept] == ["a", "b", "h", "c", "d"]


def test_cross_page_merge_keeps_first_page_and_clears_bbox():
    first = _c("a", 4, "the proposed pipeline consists of")
    first.bbox = [1, 2, 3, 4]
    merged = merge_continuation_blocks([first, _c("b", 5, "three sequential stages.")])
    assert len(merged) == 1
    assert merged[0].page == 4
    assert merged[0].bbox is None


def test_kb_index_exposes_merged_chunks():
    kb = KnowledgeBase()
    kb.index(
        "p",
        [
            _c("a", 2, "Complex events exhibit unforeseen and"),
            _c("b", 2, "multifaceted developments over time."),
        ],
    )
    chunks = kb.all_chunks("p")
    assert len(chunks) == 1 and "unforeseen and multifaceted" in chunks[0].content


def test_comma_split_merges_even_with_uppercase_continuation():
    merged = merge_continuation_blocks(
        [
            _c("a", 2, "We introduce an open-ended evaluation method,"),
            _c("b", 2, "LRAE, demonstrating the highest consistency."),
        ]
    )
    assert len(merged) == 1
    assert "method, LRAE, demonstrating" in merged[0].content


def test_kb_index_drops_page_number_noise_and_bridges_pages():
    kb = KnowledgeBase()
    kb.index(
        "p",
        [
            _c("a", 5, "the pipeline consists of two stages that are"),
            _c("pgnum", 5, "5277"),  # 孤立页码噪音块
            _c("b", 6, "executed sequentially during training."),
        ],
    )
    chunks = kb.all_chunks("p")
    # 页码被剔除；剔除后跨页断句重新相邻并成功合并
    assert all(chunk.content != "5277" for chunk in chunks)
    assert len(chunks) == 1
    assert "that are executed sequentially" in chunks[0].content
