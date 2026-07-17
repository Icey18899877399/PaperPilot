"""结构化切片展示分区（作者区/参考文献/附录默认隐藏）测试。"""

from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import PaperChunk, PaperRecord, PaperStatus
from app.services.knowledge_base import KnowledgeBase, classify_display_zones
from app.services.runtime import runtime
from app.services.storage import PaperStore


def _chunk(cid, page, content, kind="text", heading=False):
    return PaperChunk(
        chunk_id=cid,
        paper_id="paper-z",
        page=page,
        kind=kind,
        content=content,
        metadata={"text_level": 1 if heading else None},
    )


def _paper_chunks():
    return [
        _chunk("c-title", 1, "OpenForecast: A Large-Scale Dataset"),
        _chunk("c-authors", 1, "Zhen Wang, Xi Zhou, Yating Yang"),
        _chunk("c-affil", 1, "Xinjiang Technical Institute, CAS"),
        _chunk("c-abstract", 1, "Abstract Complex event forecasting is important..."),
        _chunk("c-intro-h", 1, "1 Introduction", heading=True),
        _chunk("c-body1", 2, "Event forecasting aims to predict future events."),
        _chunk("c-fig", 3, "[图片] Figure 1 overview", kind="image"),
        _chunk("c-ref-h", 9, "References", heading=True),
        _chunk("c-ref1", 9, "Smith et al. 2020. Some paper. ACL."),
        _chunk("c-ref2", 10, "Lee et al. 2021. Another paper. EMNLP."),
        _chunk("c-app-h", 12, "A.1 Details of Dataset Collection", heading=True),
        _chunk("c-app1", 12, "We collect complex events from Wikipedia."),
        _chunk("c-app-fig", 13, "[图表] appendix chart", kind="chart"),
    ]


def test_classify_display_zones():
    zones = classify_display_zones(_paper_chunks())
    assert zones["c-title"] == "body"
    # 作者与机构在标题之后、Abstract之前 → author
    assert zones["c-authors"] == "author"
    assert zones["c-affil"] == "author"
    assert zones["c-abstract"] == "body"
    assert zones["c-body1"] == "body"
    assert zones["c-fig"] == "body"
    # References 标题及其后 → reference
    assert zones["c-ref-h"] == "reference"
    assert zones["c-ref1"] == "reference"
    # References 后的 "A.1 xxx" 标题 → appendix（含其后的图表）
    assert zones["c-app-h"] == "appendix"
    assert zones["c-app1"] == "appendix"
    assert zones["c-app-fig"] == "appendix"


def test_classify_without_abstract_marks_no_author():
    chunks = [
        _chunk("t", 1, "Some Title"),
        _chunk("a", 1, "Author Names"),
        _chunk("b", 2, "Body content without abstract keyword."),
    ]
    zones = classify_display_zones(chunks)
    # 找不到 Abstract 边界时保守不标 author，宁可多显示
    assert all(zone == "body" for zone in zones.values())


def test_contents_endpoint_filters_and_toggles(tmp_path, monkeypatch):
    paper = PaperRecord(
        id="paper-z",
        filename="z.pdf",
        file_url="/media/papers/z.pdf",
        status=PaperStatus.ready,
        page_count=13,
    )
    kb = KnowledgeBase()
    kb.index(paper.id, _paper_chunks())
    monkeypatch.setattr(runtime, "papers", {paper.id: paper})
    monkeypatch.setattr(runtime, "kb", kb)
    monkeypatch.setattr(runtime, "store", PaperStore(tmp_path))

    with TestClient(app) as client:
        default_view = client.get(f"/api/papers/{paper.id}/contents?kind=text").json()
        full_view = client.get(
            f"/api/papers/{paper.id}/contents?kind=text&include_all=true"
        ).json()

    default_ids = {item["chunk_id"] for item in default_view["items"]}
    # 默认视图：作者/机构/参考文献/附录文本全部隐藏
    assert "c-authors" not in default_ids and "c-affil" not in default_ids
    assert "c-ref1" not in default_ids and "c-app1" not in default_ids
    assert "c-title" in default_ids and "c-body1" in default_ids
    # 隐藏的 text 类切片：authors+affil+ref标题+ref1+ref2+附录标题+app1 = 7
    assert default_view["hidden"] == 7

    full_ids = {item["chunk_id"] for item in full_view["items"]}
    assert {"c-authors", "c-ref1", "c-app1"} <= full_ids
    assert full_view["hidden"] == 0


def test_multimodal_chunks_visible_even_in_appendix(tmp_path, monkeypatch):
    """分区过滤只治理正文碎片：附录中的图表/公式等多模态内容默认仍可见。"""
    paper = PaperRecord(
        id="paper-z",
        filename="z.pdf",
        file_url="/media/papers/z.pdf",
        status=PaperStatus.ready,
        page_count=13,
    )
    kb = KnowledgeBase()
    kb.index(paper.id, _paper_chunks())
    monkeypatch.setattr(runtime, "papers", {paper.id: paper})
    monkeypatch.setattr(runtime, "kb", kb)
    monkeypatch.setattr(runtime, "store", PaperStore(tmp_path))

    with TestClient(app) as client:
        chart_view = client.get(f"/api/papers/{paper.id}/contents?kind=chart").json()

    # c-app-fig 位于附录区，但属于多模态内容 → 默认视图不隐藏
    assert {item["chunk_id"] for item in chart_view["items"]} == {"c-app-fig"}
    assert chart_view["hidden"] == 0
