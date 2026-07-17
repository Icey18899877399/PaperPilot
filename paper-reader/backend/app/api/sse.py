from __future__ import annotations

import json
from typing import Any


def sse_event(event: str, data: Any) -> str:
    """统一SSE编码，ensure_ascii=False保证中文状态可直接调试。"""
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"
