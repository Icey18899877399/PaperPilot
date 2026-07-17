from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.models.schemas import PaperRecord, PaperStatus
from app.services.parser import PaperParser
from app.services.storage import PaperStore


def _find_content_file(asset_root: Path) -> tuple[Path, bool]:
    candidates = sorted(asset_root.rglob("*_content_list.json"))
    if not candidates:
        candidates = sorted(asset_root.rglob("content_list.json"))
    if candidates:
        return candidates[0], False

    candidates = sorted(asset_root.rglob("*_content_list_v2.json"))
    if not candidates:
        candidates = sorted(asset_root.rglob("content_list_v2.json"))
    if candidates:
        return candidates[0], True
    raise FileNotFoundError(f"MinerU解析目录中没有content_list文件：{asset_root}")


def register(pdf_path: Path, paper_id: str) -> PaperRecord:
    settings = get_settings()
    asset_root = settings.assets_dir / paper_id
    if not asset_root.is_dir():
        raise FileNotFoundError(f"MinerU解析目录不存在：{asset_root}")

    content_file, using_v2 = _find_content_file(asset_root)
    payload = json.loads(content_file.read_text(encoding="utf-8"))
    parser = PaperParser(settings)
    items = parser._flatten_v2(payload) if using_v2 else parser._find_content_items(payload)
    if not items:
        raise RuntimeError(f"MinerU content_list为空：{content_file}")

    page_count, chunks = parser._normalize_mineru_items(
        paper_id,
        items,
        asset_root,
        content_file.parent,
    )
    if page_count <= 0 or not chunks:
        raise RuntimeError("MinerU结果没有生成可用的论文切片")

    destination = settings.uploads_dir / f"{paper_id}-{pdf_path.name}"
    shutil.copy2(pdf_path, destination)
    record = PaperRecord(
        id=paper_id,
        filename=pdf_path.name,
        file_url=f"/media/papers/{destination.name}",
        status=PaperStatus.ready,
        page_count=page_count,
        progress=100,
        stage="解析完成",
    )
    store = PaperStore(settings.data_dir)
    store.save_chunks(paper_id, chunks)
    store.save_paper(record)
    print(
        json.dumps(
            {
                "status": "MINERU_RESULT_REGISTERED",
                "paper_id": paper_id,
                "filename": pdf_path.name,
                "pages": page_count,
                "chunks": len(chunks),
                "content_file": str(content_file),
                "paper_file": str(destination),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return record


def main() -> None:
    argument_parser = argparse.ArgumentParser(
        description="将已有MinerU结构化解析结果注册到PaperPilot论文库"
    )
    argument_parser.add_argument("pdf", type=Path, help="原始PDF文件")
    argument_parser.add_argument(
        "--paper-id",
        default=None,
        help="解析结果对应的paper_id；默认使用mineru-smoke-<文件名>",
    )
    args = argument_parser.parse_args()
    pdf_path = args.pdf.expanduser().resolve()
    if not pdf_path.is_file() or pdf_path.suffix.lower() != ".pdf":
        raise FileNotFoundError(pdf_path)
    paper_id = args.paper_id or f"mineru-smoke-{pdf_path.stem.lower()}"
    register(pdf_path, paper_id)


if __name__ == "__main__":
    main()
