"""US-07 图片/图表切片视觉解释测试（离线 MockTransport，不访问真实视觉服务）。"""

import json

import httpx
import pytest

from app.agents.paper_agent import PaperUnderstandingAgent
from app.core.config import Settings
from app.models.schemas import PaperChunk
from app.services.knowledge_base import KnowledgeBase
from app.services.vision import VisionClient


def _vision_settings() -> Settings:
    return Settings(
        vision_api_url="http://fake-vision/v1",
        vision_api_key="vk-123456",
        vision_model="fake-vl",
        backend_dir=Settings().backend_dir,
    )


def _vision_transport(seen: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen["model"] = body["model"]
        # 记录用户消息里是否带了 image_url（多模态标志）
        user = next(m for m in body["messages"] if m["role"] == "user")
        seen["has_image"] = any(
            part.get("type") == "image_url" for part in user["content"]
        )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "这是视觉模型对该图的解释。"}}]},
        )

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_vision_client_sends_image_and_returns_text():
    seen: dict = {}
    client = VisionClient(_vision_settings(), transport=_vision_transport(seen))
    assert client.enabled
    result = await client.describe("系统", "解释这张图", b"\x89PNG-bytes", "image/png")
    assert result == "这是视觉模型对该图的解释。"
    assert seen["has_image"] is True and seen["model"] == "fake-vl"


@pytest.mark.asyncio
async def test_explain_image_chunk_routes_to_vision(tmp_path, monkeypatch):
    # 准备一张真实存在的图片文件 + 指向它的图片切片
    assets_dir = tmp_path / "assets"
    paper_dir = assets_dir / "paper-v"
    paper_dir.mkdir(parents=True)
    (paper_dir / "fig1.png").write_bytes(b"\x89PNG-fake-image-bytes")

    chunk = PaperChunk(
        chunk_id="paper-v-m1",
        paper_id="paper-v",
        page=3,
        kind="image",
        content="[图片] Figure 1 system architecture",
        resource_url="/media/assets/paper-v/fig1.png",
        metadata={"caption": "Figure 1 system architecture"},
    )
    kb = KnowledgeBase()
    kb.index("paper-v", [chunk])

    seen: dict = {}
    vision = VisionClient(_vision_settings(), transport=_vision_transport(seen))

    class _NoTextLLM:
        async def complete(self, *args, **kwargs):
            raise AssertionError("图片切片不应走纯文本模型")

    agent = PaperUnderstandingAgent(
        kb, _NoTextLLM(), [], vision=vision, assets_dir=assets_dir
    )
    result = await agent.explain_chunk(
        "paper-v", "demo.pdf", chunk, trace_id="t-vision"
    )
    assert result.explanation == "这是视觉模型对该图的解释。"
    assert seen["has_image"] is True


@pytest.mark.asyncio
async def test_explain_table_chunk_stays_on_text_even_with_vision(tmp_path):
    # 表格切片即便配置了视觉也应走纯文本（结构化数值更准）
    chunk = PaperChunk(
        chunk_id="paper-v-m2",
        paper_id="paper-v",
        page=6,
        kind="table",
        content="[表格] 模型A 91.5% 模型B 80.3%",
        metadata={"caption": "Table 1"},
    )
    kb = KnowledgeBase()
    kb.index("paper-v", [chunk])

    called = {"text": False}

    class _TextLLM:
        async def complete(self, *args, **kwargs):
            called["text"] = True
            return "文本模型对表格的解释。"

    class _BoomVision:
        enabled = True

        async def describe(self, *args, **kwargs):
            raise AssertionError("表格不应走视觉模型")

    agent = PaperUnderstandingAgent(
        kb, _TextLLM(), [], vision=_BoomVision(), assets_dir=tmp_path
    )
    result = await agent.explain_chunk("paper-v", "demo.pdf", chunk, trace_id="t2")
    assert called["text"] is True
    assert result.explanation == "文本模型对表格的解释。"
