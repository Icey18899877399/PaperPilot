from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.services.knowledge_base import KnowledgeBase
from app.services.parser import PaperParser


def main() -> None:
    argument_parser = argparse.ArgumentParser(description="验证真实MinerU内容的多模态检索")
    argument_parser.add_argument("assets", type=Path)
    args = argument_parser.parse_args()
    asset_root = args.assets.expanduser().resolve()
    content_files = sorted(asset_root.rglob("*_content_list.json"))
    if not content_files:
        raise FileNotFoundError("No *_content_list.json found")

    content_file = content_files[0]
    payload = json.loads(content_file.read_text(encoding="utf-8"))
    parser = PaperParser(get_settings())
    items = parser._find_content_items(payload)
    paper_id = asset_root.name
    _, chunks = parser._normalize_mineru_items(
        paper_id,
        items,
        asset_root,
        content_file.parent,
    )
    knowledge_base = KnowledgeBase()
    knowledge_base.index(paper_id, chunks)
    cases = [
        ("解释论文中的公式", "equation"),
        ("表格中有哪些实验结果", "table"),
        ("图表展示了什么趋势", "chart"),
    ]
    results = []
    for question, expected in cases:
        hit = knowledge_base.search(paper_id, question, limit=1)[0]
        if hit.kind != expected:
            raise AssertionError(f"{question}: expected {expected}, got {hit.kind}")
        if hit.resource_url:
            public_prefix = f"/media/assets/{paper_id}/"
            relative_resource = hit.resource_url.removeprefix(public_prefix)
            if relative_resource == hit.resource_url or not (asset_root / relative_resource).is_file():
                raise AssertionError(f"Missing cited resource: {hit.resource_url}")
        results.append(
            {
                "question": question,
                "kind": hit.kind,
                "page": hit.page,
                "resource_url": hit.resource_url,
            }
        )
    print(json.dumps({"status": "MINERU_RETRIEVAL_OK", "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
