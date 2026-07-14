from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="参考论文端到端烟雾测试")
    parser.add_argument("reference_dir", type=Path)
    args = parser.parse_args()
    backend_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(backend_dir))

    with tempfile.TemporaryDirectory(prefix="paper-reader-smoke-") as temporary:
        os.environ["BACKEND_DIR"] = temporary
        os.environ["LLM_API_KEY"] = ""
        os.environ["LLM_MODEL"] = ""
        os.environ["MINERU_API_URL"] = ""
        video_dir = Path(temporary) / "data" / "videos"
        video_dir.mkdir(parents=True, exist_ok=True)
        (video_dir / "catalog.json").write_text(
            json.dumps(
                [
                    {
                        "id": "smoke-transformer",
                        "title": "Transformer learning video",
                        "description": "Smoke-test metadata",
                        "keywords": ["transformer", "attention"],
                        "file_url": "/media/videos/transformer.mp4",
                    }
                ]
            ),
            encoding="utf-8",
        )

        # Import after environment setup so the application uses isolated test data.
        from fastapi.testclient import TestClient

        from app.main import app
        from app.services.storage import PaperStore

        client = TestClient(app)
        assert client.get("/api/health").json() == {"status": "ok"}

        results: list[dict[str, object]] = []
        for path in sorted(args.reference_dir.glob("*.pdf")):
            started = time.perf_counter()
            with path.open("rb") as source:
                upload = client.post(
                    "/api/papers",
                    files={"file": (path.name, source, "application/pdf")},
                )
            upload.raise_for_status()
            paper = upload.json()
            assert paper["status"] == "ready", paper
            assert paper["page_count"] > 0
            assert client.get(paper["file_url"]).status_code == 200

            guide = client.post(f"/api/papers/{paper['id']}/guide")
            guide.raise_for_status()
            guide_payload = guide.json()
            assert guide_payload["overview"]
            assert guide_payload["key_points"]

            chat = client.post(
                "/api/chat",
                json={
                    "paper_id": paper["id"],
                    "question": "What is the main contribution of this paper?",
                },
            )
            chat.raise_for_status()
            chat_payload = chat.json()
            assert chat_payload["answer"]
            assert chat_payload["citations"]
            assert all(item["page"] > 0 for item in chat_payload["citations"])

            elapsed = time.perf_counter() - started
            results.append(
                {
                    "file": path.name,
                    "pages": paper["page_count"],
                    "citations": len(chat_payload["citations"]),
                    "seconds": round(elapsed, 2),
                }
            )

        store = PaperStore(Path(temporary) / "data")
        persisted = store.load_papers()
        assert len(persisted) == len(results)
        assert all(store.load_chunks(paper.id) for paper in persisted)

        video_chat = client.post(
            "/api/chat",
            json={
                "paper_id": persisted[0].id,
                "question": "Please recommend a transformer learning video",
            },
        )
        video_chat.raise_for_status()
        assert len(video_chat.json()["videos"]) == 1
        assert len(client.get("/api/videos").json()) == 1

        logs = client.get("/api/agents/logs").json()
        assert len(logs) >= len(results) * 4

        print("REFERENCE_SMOKE_OK")
        for result in results:
            print(
                f"{result['file']}\tpages={result['pages']}"
                f"\tcitations={result['citations']}\tseconds={result['seconds']}"
            )
        print(f"persisted_papers={len(persisted)} agent_logs={len(logs)}")


if __name__ == "__main__":
    main()
