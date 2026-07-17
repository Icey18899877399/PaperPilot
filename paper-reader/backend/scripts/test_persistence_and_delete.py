from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from pypdf import PdfWriter


def main() -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(backend_dir))
    with tempfile.TemporaryDirectory(prefix="paper-reader-manage-") as temporary:
        os.environ["BACKEND_DIR"] = temporary
        os.environ["MINERU_API_URL"] = ""
        os.environ["DEEPSEEK_API_KEY"] = ""
        os.environ["LLM_API_KEY"] = ""

        from fastapi.testclient import TestClient

        from app.main import app
        from app.models.schemas import (
            MindMapBranch,
            MindMapResponse,
            PaperRecord,
            PaperStatus,
        )
        from app.services.runtime import runtime

        pdf_path = Path(temporary) / "manage-test.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=595, height=842)
        with pdf_path.open("wb") as destination:
            writer.write(destination)

        client = TestClient(app)
        with pdf_path.open("rb") as source:
            response = client.post(
                "/api/papers",
                files={"file": (pdf_path.name, source, "application/pdf")},
            )
        response.raise_for_status()
        paper = response.json()
        paper_id = paper["id"]

        cached = MindMapResponse(
            paper_id=paper_id,
            title="缓存测试",
            center="测试论文",
            branches=[
                MindMapBranch(
                    label="研究问题",
                    summary="验证思维导图可以持久化。",
                    children=["缓存读取", "安全删除"],
                )
            ],
            agent_trace_id="cached-trace",
        )
        runtime.store.save_mind_map(cached)
        cached_path = runtime.store.mindmaps_dir / f"{paper_id}.json"
        upload_path = runtime.store.data_dir / "uploads" / Path(paper["file_url"]).name
        index_path = runtime.store.indexes_dir / f"{paper_id}.json"
        assert cached_path.is_file()
        assert upload_path.is_file()
        assert index_path.is_file()

        loaded = client.get(f"/api/papers/{paper_id}/mind-map")
        loaded.raise_for_status()
        assert loaded.json()["agent_trace_id"] == "cached-trace"
        reused = client.post(f"/api/papers/{paper_id}/mind-map")
        reused.raise_for_status()
        assert reused.json()["agent_trace_id"] == "cached-trace"

        deleted = client.delete(f"/api/papers/{paper_id}")
        assert deleted.status_code == 204, deleted.text
        assert client.get(f"/api/papers/{paper_id}").status_code == 404
        assert not cached_path.exists()
        assert not upload_path.exists()
        assert not index_path.exists()
        assert not runtime.kb.all_chunks(paper_id)

        parsing = PaperRecord(
            id="parsing-paper",
            filename="parsing.pdf",
            file_url="/media/papers/parsing.pdf",
            status=PaperStatus.parsing,
            progress=25,
            stage="MinerU结构化解析中",
        )
        runtime.papers[parsing.id] = parsing
        runtime.store.save_paper(parsing)
        protected = client.delete(f"/api/papers/{parsing.id}")
        assert protected.status_code == 409, protected.text
        assert parsing.id in runtime.papers
        print("PERSISTENCE_DELETE_OK cache=reused delete=clean parsing=protected")


if __name__ == "__main__":
    main()
