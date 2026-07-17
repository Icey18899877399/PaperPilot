from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.routes import papers as papers_route
from app.core.config import Settings
from app.main import app
from app.models.schemas import GuideResponse, PaperChunk
from app.services.knowledge_base import KnowledgeBase
from app.services.runtime import runtime
from app.services.storage import PaperStore


class FakeParser:
    def __init__(self, fail_first: bool = False):
        self.fail_first = fail_first
        self.calls = 0

    async def parse(self, paper_id, path):
        del path
        self.calls += 1
        if self.fail_first and self.calls == 1:
            raise RuntimeError("模拟MinerU解析失败")
        return 1, [
            PaperChunk(
                chunk_id=f"{paper_id}-p1-c1",
                paper_id=paper_id,
                page=1,
                content="用于验证自动导读的论文内容。",
            )
        ]


class FakeCoordinator:
    async def run(self, task: str, **payload):
        if task != "guide":
            raise AssertionError(f"意外任务：{task}")
        return GuideResponse(
            paper_id=payload["paper_id"],
            title=payload["filename"].removesuffix(".pdf"),
            overview="自动生成的测试导读",
            key_points=["研究问题", "核心方法", "主要结果"],
            reading_questions=["问题一", "问题二", "问题三"],
            agent_trace_id="test-trace",
        )


class TestUS01UploadFlow(TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.settings = Settings(
            backend_dir=Path(self.temporary.name),
            max_pdf_size_mb=1,
        )
        self.settings.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.settings.assets_dir.mkdir(parents=True, exist_ok=True)
        self.parser = FakeParser()
        self.patchers = [
            patch.object(papers_route, "get_settings", return_value=self.settings),
            patch.object(runtime, "papers", {}),
            patch.object(runtime, "kb", KnowledgeBase()),
            patch.object(runtime, "store", PaperStore(self.settings.data_dir)),
            patch.object(runtime, "parser", self.parser),
            patch.object(runtime, "coordinator", FakeCoordinator()),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temporary.cleanup()

    def upload(self, payload: bytes, filename: str = "demo.pdf"):
        return self.client.post(
            "/api/papers?background=false",
            files={"file": (filename, payload, "application/pdf")},
        )

    def test_rejects_pdf_over_configured_size(self) -> None:
        payload = b"%PDF-1.7\n" + b"0" * (1024 * 1024)
        response = self.upload(payload)

        self.assertEqual(response.status_code, 413)
        self.assertIn("不能超过1MB", response.json()["detail"])
        self.assertEqual(list(self.settings.uploads_dir.iterdir()), [])

    def test_detects_duplicate_and_persists_automatic_guide(self) -> None:
        payload = b"%PDF-1.7\nfixture"
        first = self.upload(payload, "first.pdf")

        self.assertEqual(first.status_code, 201)
        record = first.json()
        self.assertEqual(record["status"], "ready")
        self.assertTrue(record["file_sha256"])
        self.assertEqual(record["stage"], "解析完成，导读已生成")

        guide = self.client.get(f"/api/papers/{record['id']}/guide")
        self.assertEqual(guide.status_code, 200)
        self.assertEqual(guide.json()["overview"], "自动生成的测试导读")

        duplicate = self.upload(payload, "renamed.pdf")
        self.assertEqual(duplicate.status_code, 409)
        self.assertIn("检测到重复论文", duplicate.json()["detail"])
        self.assertIn(record["id"], duplicate.json()["detail"])

    def test_failed_paper_can_be_retried_with_original_pdf(self) -> None:
        self.parser.fail_first = True
        failed = self.upload(b"%PDF-1.7\nretry", "retry.pdf")

        self.assertEqual(failed.status_code, 201)
        record = failed.json()
        self.assertEqual(record["status"], "failed")
        self.assertIn("模拟MinerU解析失败", record["error"])

        retried = self.client.post(
            f"/api/papers/{record['id']}/retry?background=false"
        )
        self.assertEqual(retried.status_code, 200)
        self.assertEqual(retried.json()["status"], "ready")
        self.assertEqual(retried.json()["stage"], "解析完成，导读已生成")
        self.assertEqual(self.parser.calls, 2)

        guide = self.client.get(f"/api/papers/{record['id']}/guide")
        self.assertEqual(guide.status_code, 200)

