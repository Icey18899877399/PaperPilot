"""US-04向量索引与融合检索测试。"""

import httpx

from app.models.schemas import PaperChunk
from app.services.knowledge_base import KnowledgeBase
from app.services.vector_index import VectorIndex


def make_chunk(chunk_id: str, page: int, content: str, kind: str = "text") -> PaperChunk:
    return PaperChunk(
        chunk_id=chunk_id,
        paper_id="paper-vs",
        page=page,
        kind=kind,
        content=content,
        metadata={"text_level": None},
    )


def build_kb() -> KnowledgeBase:
    kb = KnowledgeBase()
    kb.index(
        "paper-vs",
        [
            make_chunk(
                "c1",
                1,
                "本文提出一种基于Transformer的事件预测方法，通过注意力机制建模事件序列。"
                * 3,
            ),
            make_chunk(
                "c2",
                2,
                "实验在OpenForecast数据集上进行，评价指标包括准确率和F1分数，"
                "并与LSTM基线模型对比。" * 3,
            ),
            make_chunk(
                "c3",
                3,
                "系统采用检索增强生成架构，向量索引负责召回论文相关片段。" * 3,
            ),
        ],
    )
    return kb


def test_fused_search_ranks_relevant_chunk_first():
    kb = build_kb()
    scored = kb.search_scored("paper-vs", "实验使用了什么数据集和评价指标", limit=3)
    assert scored, "相关问题必须有召回"
    top_score, top_chunk = scored[0]
    assert "数据集" in top_chunk.content
    assert top_score > 0
    # US-04：召回结果必须携带相关度，供检索调试接口展示
    assert top_chunk.metadata["retrieval_score"] == top_score
    assert top_chunk.metadata["retrieval_rank"] == 1


def test_zero_match_returns_empty_instead_of_head_chunks():
    kb = build_kb()
    # 与论文完全无关的问题不应再返回论文开头切片（US-05 AC-05-02前置）
    assert kb.search("paper-vs", "唐朝的科举制度如何运作", limit=3) == []


def test_vector_index_rebuild_and_remove(tmp_path):
    index = VectorIndex(persist_dir=tmp_path)
    kb = KnowledgeBase(index)
    chunks = [make_chunk("c1", 1, "深度学习模型训练与优化方法研究。" * 5)]
    kb.index("paper-vs", chunks)
    persisted = tmp_path / "paper-vs.vectors.json"
    assert persisted.exists(), "向量索引应持久化为可检查产物"

    # 重新索引不应产生重复条目（US-04：重新解析不得产生重复索引）
    kb.index("paper-vs", chunks)
    assert index.backend_name("paper-vs") == "local-tfidf"

    # 删除论文时同步删除索引（US-04）
    kb.remove("paper-vs")
    assert index.backend_name("paper-vs") == "none"
    assert not persisted.exists()
    assert kb.search("paper-vs", "深度学习", limit=3) == []


def _fake_embed(text: str) -> list[float]:
    # 8维确定性"语义"向量：按几个标记词的出现给不同维度加权，
    # 使含相同关键词的文本向量相近，便于验证dense检索链路。
    markers = ["dataset", "数据", "model", "模型", "result", "结果", "method", "方法"]
    lowered = text.lower()
    vector = [float(lowered.count(marker)) + 0.1 for marker in markers]
    return vector


def _embedding_transport(counter: dict):
    import json as _json

    def handler(request):
        counter["calls"] = counter.get("calls", 0) + 1
        body = _json.loads(request.content)
        data = [
            {"index": i, "embedding": _fake_embed(text)}
            for i, text in enumerate(body["input"])
        ]
        return httpx.Response(200, json={"data": data})

    return httpx.MockTransport(handler)


def test_remote_embedding_persists_and_reuses(tmp_path):
    import json as _json

    counter: dict = {}
    kwargs = dict(
        embedding_api_url="http://fake-embed",
        embedding_api_key="k",
        embedding_model="fake-model",
        persist_dir=tmp_path,
        transport=_embedding_transport(counter),
    )
    chunks = [
        make_chunk("c1", 1, "the dataset and model details" * 3),
        make_chunk("c2", 2, "the main result and method" * 3),
    ]

    index = VectorIndex(**kwargs)
    index.index("paper-e", chunks)
    assert index.backend_name("paper-e") == "remote-embedding"
    persisted = tmp_path / "paper-e.vectors.json"
    payload = _json.loads(persisted.read_text(encoding="utf-8"))
    assert payload["dense"] and payload["signature"]
    build_calls = counter["calls"]
    assert build_calls >= 1

    # 模拟重启：新实例、相同内容 → 复用持久化向量，不再调用embedding建库
    index2 = VectorIndex(**{**kwargs, "transport": _embedding_transport(counter)})
    index2.index("paper-e", chunks)
    assert index2.backend_name("paper-e") == "remote-embedding"
    assert counter["calls"] == build_calls, "复用持久化向量时不应再次调用embedding接口"

    # 查询走稠密向量（会产生一次查询嵌入调用）
    scores = index2.search("paper-e", "关于 dataset 数据 的问题")
    assert counter["calls"] == build_calls + 1
    assert isinstance(scores, dict) and scores


def test_remote_embedding_reembeds_on_content_change(tmp_path):
    counter: dict = {}
    kwargs = dict(
        embedding_api_url="http://fake-embed",
        embedding_api_key="k",
        embedding_model="fake-model",
        persist_dir=tmp_path,
        transport=_embedding_transport(counter),
    )
    index = VectorIndex(**kwargs)
    index.index("paper-e", [make_chunk("c1", 1, "original content" * 3)])
    calls_after_first = counter["calls"]

    # 内容变化（重解析）→ 签名失配 → 必须重新嵌入
    index.index("paper-e", [make_chunk("c1", 1, "changed content entirely" * 3)])
    assert counter["calls"] > calls_after_first


def test_failed_embedding_does_not_clobber_reusable_cache(tmp_path):
    counter: dict = {}
    kwargs = dict(
        embedding_api_url="http://fake-embed",
        embedding_api_key="k",
        embedding_model="fake-model",
        persist_dir=tmp_path,
    )
    chunks = [make_chunk("c1", 1, "the dataset and model details" * 3)]

    # 首次成功建库并持久化稠密向量
    VectorIndex(**kwargs, transport=_embedding_transport(counter)).index("paper-e", chunks)

    # 相同内容重建时 embedding 接口故障 → 不得用空向量覆盖已有缓存
    def boom(request):
        raise RuntimeError("embedding service down")

    VectorIndex(**kwargs, transport=httpx.MockTransport(boom)).index("paper-e", chunks)

    # 故障后新实例仍能复用持久化向量（缓存未被破坏），且不再联网嵌入
    reuse_counter: dict = {}
    reused = VectorIndex(**kwargs, transport=_embedding_transport(reuse_counter))
    reused.index("paper-e", chunks)
    assert reused.backend_name("paper-e") == "remote-embedding"
    assert reuse_counter.get("calls", 0) == 0


def _mmr_chunk(chunk_id: str, section: str) -> PaperChunk:
    return PaperChunk(
        chunk_id=chunk_id,
        paper_id="paper-mmr",
        page=1,
        kind="text",
        content="x",
        metadata={"section_path": [section]},
    )


def test_mmr_select_diversifies_over_same_section_near_duplicates():
    # 直接驱动MMR选取逻辑：三条同章节近重复(6.3) + 一条相关但不同章节(5)。
    # 纯相关度top-2会是两条6.3；MMR应把不同章节的m1提上来。
    kb = KnowledgeBase()
    kb._chunk_terms["paper-mmr"] = {
        "d1": ({"lrae", "eval", "f1", "retrieval"}, set()),
        "d2": ({"lrae", "eval", "f1", "retrieval"}, set()),
        "d3": ({"lrae", "eval", "f1", "retrieval"}, set()),
        "m1": ({"lrae", "eval", "method", "retrieval"}, set()),
    }
    pool = [
        (1.00, _mmr_chunk("d1", "6.3 Experiments on LRAE")),
        (0.98, _mmr_chunk("d2", "6.3 Experiments on LRAE")),
        (0.96, _mmr_chunk("d3", "6.3 Experiments on LRAE")),
        (0.90, _mmr_chunk("m1", "5 LRAE Method")),
    ]
    selected = kb._mmr_select("paper-mmr", pool, limit=2)
    sections = {tuple(chunk.metadata["section_path"]) for _, chunk in selected}
    assert len(sections) == 2, "MMR应让top-2覆盖两个不同章节，而非同章节近重复霸屏"
    # 最相关的一条仍排第一（MMR不牺牲首位相关度）
    assert selected[0][1].chunk_id == "d1"


def test_mmr_returns_pool_when_not_exceeding_limit():
    kb = KnowledgeBase()
    kb._chunk_terms["p"] = {"a": ({"x"}, set()), "b": ({"y"}, set())}
    pool = [(1.0, _mmr_chunk("a", "S1")), (0.5, _mmr_chunk("b", "S2"))]
    # 候选不多于limit时按相关度原样返回，不做多样性重排
    assert kb._mmr_select("p", pool, limit=3) == pool
