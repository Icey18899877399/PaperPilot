from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.services.llm import LLMClient, LLMServiceError


async def main() -> None:
    client = LLMClient(get_settings())
    status = client.status()
    if not status.configured:
        raise SystemExit(
            "DeepSeek尚未配置。请先在项目根目录运行："
            "powershell -ExecutionPolicy Bypass -File scripts\\configure-deepseek.ps1"
        )
    started = perf_counter()
    try:
        answer = await client.complete(
            "你是连接测试助手，只回答OK。",
            "请回答OK",
        )
    except LLMServiceError as exc:
        raise SystemExit(f"连接失败：{exc}") from exc
    elapsed = round((perf_counter() - started) * 1000)
    print(
        f"DEEPSEEK_CONNECTION_OK provider={status.provider} "
        f"model={status.model} latency_ms={elapsed} response_length={len(answer)}"
    )


if __name__ == "__main__":
    asyncio.run(main())

