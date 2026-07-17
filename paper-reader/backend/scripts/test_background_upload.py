from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from pypdf import PdfWriter


def main() -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(backend_dir))
    with tempfile.TemporaryDirectory(prefix="paper-reader-background-") as temporary:
        os.environ["BACKEND_DIR"] = temporary
        os.environ["MINERU_API_URL"] = ""
        os.environ["DEEPSEEK_API_KEY"] = ""
        os.environ["LLM_API_KEY"] = ""

        from fastapi.testclient import TestClient

        from app.main import app

        pdf_path = Path(temporary) / "background-test.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=595, height=842)
        with pdf_path.open("wb") as destination:
            writer.write(destination)

        client = TestClient(app)
        with pdf_path.open("rb") as source:
            response = client.post(
                "/api/papers?background=true",
                files={"file": (pdf_path.name, source, "application/pdf")},
            )
        response.raise_for_status()
        created = response.json()
        assert created["status"] == "parsing", created
        assert created["progress"] == 5, created

        current = client.get(f"/api/papers/{created['id']}")
        current.raise_for_status()
        completed = current.json()
        assert completed["status"] == "ready", completed
        assert completed["progress"] == 100, completed
        assert completed["stage"] == "解析完成", completed
        assert completed["page_count"] == 1, completed
        print(
            "BACKGROUND_UPLOAD_OK "
            f"initial={created['status']} final={completed['status']} "
            f"progress={completed['progress']}"
        )


if __name__ == "__main__":
    main()
