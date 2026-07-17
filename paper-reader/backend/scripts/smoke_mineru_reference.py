from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.services.parser import PaperParser


async def run(pdf_path: Path) -> None:
    settings = get_settings()
    if not settings.mineru_api_url:
        raise RuntimeError("MINERU_API_URL is not configured")
    paper_id = f"mineru-smoke-{pdf_path.stem.lower()}"
    started = time.perf_counter()
    page_count, chunks = await PaperParser(settings).parse(paper_id, pdf_path)
    elapsed = time.perf_counter() - started
    counts = Counter(chunk.kind for chunk in chunks)
    resources = sum(1 for chunk in chunks if chunk.resource_url)
    if page_count <= 0 or not chunks:
        raise RuntimeError("MinerU returned no structured content")
    result = {
        "status": "MINERU_REFERENCE_OK",
        "paper": pdf_path.name,
        "pages": page_count,
        "chunks": len(chunks),
        "counts": dict(counts),
        "resources": resources,
        "seconds": round(elapsed, 2),
        "assets": str(settings.assets_dir / paper_id),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="使用真实论文验证MinerU结构化解析")
    parser.add_argument("pdf", type=Path)
    args = parser.parse_args()
    pdf_path = args.pdf.expanduser().resolve()
    if not pdf_path.is_file() or pdf_path.suffix.lower() != ".pdf":
        raise FileNotFoundError(pdf_path)
    asyncio.run(run(pdf_path))


if __name__ == "__main__":
    main()
