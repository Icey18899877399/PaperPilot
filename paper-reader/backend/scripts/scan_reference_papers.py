from __future__ import annotations

import argparse
from pathlib import Path

from pypdf import PdfReader


def main() -> None:
    parser = argparse.ArgumentParser(description="扫描课程参考论文的基础可解析性")
    parser.add_argument("reference_dir", type=Path)
    args = parser.parse_args()

    for path in sorted(args.reference_dir.glob("*.pdf")):
        reader = PdfReader(str(path))
        text_length = sum(len(page.extract_text() or "") for page in reader.pages)
        title = ""
        if reader.metadata:
            title = reader.metadata.title or ""
        print(
            f"{path.name}\tpages={len(reader.pages)}\tchars={text_length}"
            f"\ttitle={title.strip()}"
        )


if __name__ == "__main__":
    main()
