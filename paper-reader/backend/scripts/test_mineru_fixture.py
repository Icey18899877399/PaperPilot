"""Offline MinerU adapter smoke test; does not require a running MinerU service."""

import json
import sys
import tempfile
import zipfile
from collections import Counter
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings
from app.services.knowledge_base import KnowledgeBase
from app.services.parser import PaperParser


def build_fixture() -> bytes:
    items = [
        {"type": "text", "text": "多模态论文阅读", "page_idx": 0},
        {
            "type": "image",
            "img_path": "images/figure.png",
            "image_caption": ["图1 系统结构"],
            "bbox": [10, 20, 900, 600],
            "page_idx": 0,
        },
        {
            "type": "table",
            "table_caption": ["表1 准确率"],
            "table_body": "<table><tr><td>模型A</td><td>91%</td></tr></table>",
            "page_idx": 1,
        },
        {
            "type": "equation",
            "text": "L = -\\sum_i y_i \\log p_i",
            "page_idx": 2,
        },
    ]
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("demo/sample_content_list.json", json.dumps(items, ensure_ascii=False))
        archive.writestr("demo/images/figure.png", b"fixture")
    return output.getvalue()


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="mineru-fixture-") as temporary:
        parser = PaperParser(Settings(backend_dir=Path(temporary)))
        pages, chunks = parser._parse_mineru_zip("fixture", build_fixture())
        counts = Counter(chunk.kind for chunk in chunks)
        assert pages == 3
        assert counts == {"text": 1, "image": 1, "table": 1, "equation": 1}
        assert next(chunk for chunk in chunks if chunk.kind == "image").resource_url

        knowledge_base = KnowledgeBase()
        knowledge_base.index("fixture", chunks)
        assert knowledge_base.search("fixture", "解释公式", limit=1)[0].kind == "equation"
        assert knowledge_base.search("fixture", "表格准确率", limit=1)[0].kind == "table"
        print(f"MINERU_FIXTURE_OK pages={pages} counts={dict(counts)}")


if __name__ == "__main__":
    main()
