from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="使用一篇真实论文验证DeepSeek导读、问答和翻译"
    )
    parser.add_argument("paper", type=Path)
    args = parser.parse_args()
    if not args.paper.exists() or args.paper.suffix.lower() != ".pdf":
        raise SystemExit("请提供存在的PDF论文路径")

    with tempfile.TemporaryDirectory(prefix="deepseek-paper-smoke-") as temporary:
        os.environ["BACKEND_DIR"] = temporary

        # Import after BACKEND_DIR setup. DeepSeek credentials are loaded from
        # the project .env file and are never printed by this script.
        from fastapi.testclient import TestClient

        from app.main import app
        from app.services.runtime import runtime

        status = runtime.llm.status()
        if not status.configured or status.provider != "deepseek":
            raise SystemExit(
                "DeepSeek尚未配置。请先运行项目根目录下的"
                "scripts\\configure-deepseek.ps1"
            )

        client = TestClient(app)
        started = perf_counter()
        with args.paper.open("rb") as source:
            upload = client.post(
                "/api/papers",
                files={
                    "file": (
                        args.paper.name,
                        source,
                        "application/pdf",
                    )
                },
            )
        upload.raise_for_status()
        paper = upload.json()

        guide = client.post(f"/api/papers/{paper['id']}/guide")
        guide.raise_for_status()
        guide_data = guide.json()

        chat = client.post(
            "/api/chat",
            json={
                "paper_id": paper["id"],
                "question": (
                    "请用中文说明这篇论文的研究问题、核心方法和主要贡献，"
                    "并依据论文页码回答。"
                ),
            },
        )
        chat.raise_for_status()
        chat_data = chat.json()

        translation = client.post(
            f"/api/papers/{paper['id']}/translate",
            json={
                "text": (
                    "Large language models are increasingly used for "
                    "forecasting future events."
                ),
                "target_language": "中文",
            },
        )
        translation.raise_for_status()
        translation_data = translation.json()

        elapsed = round(perf_counter() - started, 2)
        print(
            "DEEPSEEK_REFERENCE_SMOKE_OK "
            f"model={status.model} paper={args.paper.name} "
            f"pages={paper['page_count']} "
            f"guide_chars={len(guide_data['overview'])} "
            f"key_points={len(guide_data['key_points'])} "
            f"answer_chars={len(chat_data['answer'])} "
            f"citations={len(chat_data['citations'])} "
            f"translation_chars={len(translation_data['translated_text'])} "
            f"seconds={elapsed}"
        )


if __name__ == "__main__":
    main()

