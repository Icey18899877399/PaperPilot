from app.models.schemas import PaperChunk
from app.services.knowledge_base import KnowledgeBase


def chunk(
    chunk_id: str,
    page: int,
    content: str,
    *,
    kind: str = "text",
    level: int | None = None,
) -> PaperChunk:
    metadata = {"text_level": level} if level is not None else {}
    return PaperChunk(
        chunk_id=chunk_id,
        paper_id="paper-1",
        page=page,
        kind=kind,
        content=content,
        bbox=[10, 20, 500, 120],
        metadata=metadata,
    )


def test_retrieval_chunks_preserve_source_blocks_and_normalize_boundaries() -> None:
    running_header = "PaperPilot Conference Running Header"
    long_method = (
        "This sentence explains the proposed model, training process, and experiment results. "
        * 55
    )
    long_table = " | ".join(f"row {index} accuracy value" for index in range(180))
    source = [
        chunk("heading-method", 1, "2 Proposed Method", level=1),
        chunk("method-a", 1, "The method starts with a compact event representation."),
        chunk("method-b", 1, "It then predicts future states with a constrained decoder."),
        chunk("page-number", 1, "5273"),
        chunk("header-1", 1, running_header),
        chunk("header-2", 2, running_header),
        chunk("header-3", 3, running_header),
        chunk("method-long", 2, long_method),
        chunk("heading-reference", 3, "References", level=1),
        chunk("reference-list", 3, "Model reference entry. " * 120, kind="list"),
        chunk("results-table", 4, long_table, kind="table"),
    ]

    knowledge_base = KnowledgeBase()
    knowledge_base.index("paper-1", source)

    assert knowledge_base.all_chunks("paper-1") == source
    retrieval = knowledge_base.retrieval_chunks("paper-1")
    assert retrieval
    assert all(item.metadata["parser"] == "retrieval-postprocessor" for item in retrieval)
    assert all("5273" != item.content.strip() for item in retrieval)
    assert all(running_header not in item.content for item in retrieval)

    method_chunks = [
        item
        for item in retrieval
        if "method-long" in item.metadata["source_chunk_ids"]
    ]
    assert len(method_chunks) >= 2
    assert all(item.content.startswith("章节：2 Proposed Method") for item in method_chunks)
    assert all(len(item.content) <= KnowledgeBase.MAX_CHARS for item in method_chunks)

    table_chunks = [item for item in retrieval if item.kind == "table"]
    assert len(table_chunks) >= 2
    assert all("results-table" in item.metadata["source_chunk_ids"] for item in table_chunks)
    assert all(len(item.content) <= KnowledgeBase.MAX_CHARS for item in table_chunks)

    reference_chunks = [
        item for item in retrieval if item.metadata.get("is_reference")
    ]
    assert reference_chunks
    assert knowledge_base.search("paper-1", "proposed model", limit=1)[0].metadata[
        "is_reference"
    ] is False


def test_short_neighbouring_blocks_merge_without_losing_bbox() -> None:
    knowledge_base = KnowledgeBase()
    source = [
        chunk("heading", 1, "Introduction", level=1),
        chunk("short-a", 1, "First short paragraph."),
        chunk("short-b", 1, "Second short paragraph."),
    ]
    knowledge_base.index("paper-1", source)

    retrieval = knowledge_base.retrieval_chunks("paper-1")
    assert len(retrieval) == 1
    assert retrieval[0].metadata["source_chunk_ids"] == ["short-a", "short-b"]
    assert retrieval[0].bbox == [10.0, 20.0, 500.0, 120.0]
    assert "First short paragraph" in retrieval[0].content
    assert "Second short paragraph" in retrieval[0].content


def test_section_prefix_is_included_in_maximum_chunk_length() -> None:
    knowledge_base = KnowledgeBase()
    source = [
        chunk("heading", 1, "A" * KnowledgeBase.HEADING_MAX_CHARS, level=1),
        chunk("body", 1, "method result " * 130),
    ]
    knowledge_base.index("paper-1", source)

    retrieval = knowledge_base.retrieval_chunks("paper-1")
    assert len(retrieval) >= 2
    assert all(len(item.content) <= KnowledgeBase.MAX_CHARS for item in retrieval)
