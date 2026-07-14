import json
import zipfile
from collections import Counter
from io import BytesIO

import pytest

from app.core.config import Settings
from app.services.knowledge_base import KnowledgeBase
from app.services.parser import MinerUParseError, PaperParser


def build_mineru_zip() -> bytes:
    items = [
        {
            "type": "text",
            "text": "本文提出一种多模态论文阅读方法。",
            "text_level": 1,
            "bbox": [50, 60, 900, 120],
            "page_idx": 0,
        },
        {
            "type": "image",
            "img_path": "images/figure-1.png",
            "image_caption": ["图1 系统总体结构"],
            "image_footnote": ["箭头表示数据流"],
            "bbox": [100, 180, 880, 600],
            "page_idx": 0,
        },
        {
            "type": "table",
            "img_path": "images/table-1.png",
            "table_caption": ["表1 模型性能对比"],
            "table_body": "<table><tr><th>模型</th><th>准确率</th></tr><tr><td>A</td><td>91%</td></tr></table>",
            "bbox": [80, 140, 920, 720],
            "page_idx": 1,
        },
        {
            "type": "equation",
            "text": "L = -\\sum_i y_i \\log p_i",
            "text_format": "latex",
            "bbox": [200, 300, 800, 400],
            "page_idx": 2,
        },
    ]
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("demo/sample_content_list.json", json.dumps(items, ensure_ascii=False))
        archive.writestr("demo/images/figure-1.png", b"fixture-image")
        archive.writestr("demo/images/table-1.png", b"fixture-table")
    return stream.getvalue()


def test_mineru_zip_normalizes_multimodal_blocks(tmp_path):
    parser = PaperParser(Settings(backend_dir=tmp_path))
    page_count, chunks = parser._parse_mineru_zip("paper-1", build_mineru_zip())

    assert page_count == 3
    assert Counter(chunk.kind for chunk in chunks) == {
        "text": 1,
        "image": 1,
        "table": 1,
        "equation": 1,
    }
    image = next(chunk for chunk in chunks if chunk.kind == "image")
    table = next(chunk for chunk in chunks if chunk.kind == "table")
    equation = next(chunk for chunk in chunks if chunk.kind == "equation")
    assert image.resource_url == "/media/assets/paper-1/demo/images/figure-1.png"
    assert image.bbox == [100.0, 180.0, 880.0, 600.0]
    assert "系统总体结构" in image.content
    assert "模型 | 准确率 | A | 91%" in table.metadata["table_text"]
    assert table.resource_url == "/media/assets/paper-1/demo/images/table-1.png"
    assert equation.metadata["latex"] == "L = -\\sum_i y_i \\log p_i"

    kb = KnowledgeBase()
    kb.index("paper-1", chunks)
    assert kb.search("paper-1", "解释论文中的公式", limit=1)[0].kind == "equation"
    assert kb.search("paper-1", "表格里的准确率是多少", limit=1)[0].kind == "table"


def test_mineru_zip_rejects_path_traversal(tmp_path):
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("../outside.txt", "unsafe")
    parser = PaperParser(Settings(backend_dir=tmp_path))

    with pytest.raises(MinerUParseError, match="不安全"):
        parser._parse_mineru_zip("paper-2", stream.getvalue())
