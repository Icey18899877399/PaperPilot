from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings
from app.services.llm import LLMClient, LLMServiceError


def handler(request: httpx.Request) -> httpx.Response:
    assert request.url == httpx.URL("https://api.deepseek.com/chat/completions")
    assert request.headers["Authorization"] == "Bearer test-key-not-real-1234567890"
    payload = json.loads(request.content)
    assert payload["model"] == "deepseek-v4-flash"
    assert payload["thinking"] == {"type": "disabled"}
    if payload.get("response_format"):
        content = json.dumps(
            {
                "overview": "测试概述",
                "key_points": ["重点一", "重点二", "重点三"],
                "reading_questions": ["问题一", "问题二", "问题三"],
            },
            ensure_ascii=False,
        )
    else:
        content = "OK"
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": content,
                    }
                }
            ]
        },
    )


async def main() -> None:
    settings = Settings(
        deepseek_api_key="test-key-not-real-1234567890",
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-v4-flash",
        deepseek_thinking=False,
    )
    client = LLMClient(settings, transport=httpx.MockTransport(handler))
    assert client.status().configured
    assert client.status().provider == "deepseek"
    assert await client.complete("system", "user") == "OK"
    structured = await client.complete_json("JSON only", "paper")
    assert structured
    assert len(structured["key_points"]) == 3

    def error_handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            400,
            json={"error": {"msg": "invalid request body for smoke test"}},
        )

    failing = LLMClient(
        settings,
        transport=httpx.MockTransport(error_handler),
    )
    try:
        await failing.complete("system", "user")
    except LLMServiceError as exc:
        assert "invalid request body" in str(exc)
        assert settings.deepseek_api_key not in str(exc)
    else:
        raise AssertionError("Expected a sanitized LLMServiceError")
    print("DEEPSEEK_ADAPTER_OK")


if __name__ == "__main__":
    asyncio.run(main())
