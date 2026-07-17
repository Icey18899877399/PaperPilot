import json

import httpx
import pytest

from app.core.config import Settings
from app.services.llm import LLMClient

FAKE_KEY = "sk-test-1234567890abcdefghij"


def make_client(content: str) -> LLMClient:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200, text=content)

    settings = Settings(
        deepseek_api_key=FAKE_KEY,
        deepseek_model="deepseek-v4-flash",
        backend_dir=Settings().backend_dir,
    )
    return LLMClient(settings, transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_complete_stream_yields_openai_compatible_deltas():
    stream = "\n\n".join(
        [
            'data: {"choices":[{"delta":{"content":"论文"}}]}',
            'data: {"choices":[{"delta":{"content":"回答"}}]}',
            "data: [DONE]",
            "",
        ]
    )
    parts = [part async for part in make_client(stream).complete_stream("s", "u")]
    assert parts == ["论文", "回答"]


@pytest.mark.asyncio
async def test_complete_json_stream_reports_progress_and_parses_final_object():
    stream = "\n\n".join(
        [
            'data: {"choices":[{"delta":{"content":"{\\\"one_"}}]}',
            'data: {"choices":[{"delta":{"content":"liner\\\":\\\"结论\\\"}"}}]}',
            "data: [DONE]",
            "",
        ]
    )
    deltas: list[str] = []

    async def on_delta(delta: str) -> None:
        deltas.append(delta)

    result = await make_client(stream).complete_json_stream(
        "s",
        "u",
        on_delta=on_delta,
    )
    assert result == {"one_liner": "结论"}
    assert "".join(deltas) == '{"one_liner":"结论"}'
