from __future__ import annotations

import base64

import httpx

from app.core.config import Settings


class VisionServiceError(RuntimeError):
    """视觉模型调用失败（不含密钥），供上层回退文本解释。"""


class VisionClient:
    """OpenAI 兼容的多模态（视觉）客户端，用于图片/图表切片的 AI 解释。

    仅当配置了 VISION_API_URL/KEY/MODEL 时启用；把切片对应的图片以 base64
    data URI 随消息发送给视觉模型。调用失败抛 VisionServiceError，由 Agent
    回退到纯文本解释，保证功能不因视觉服务中断而失效。
    """

    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.settings = settings
        self.transport = transport

    @property
    def enabled(self) -> bool:
        return bool(
            self.settings.vision_api_url
            and self.settings.vision_model
            and self.settings.vision_api_key
        )

    @property
    def model(self) -> str:
        return self.settings.vision_model

    async def describe(
        self,
        system: str,
        user_text: str,
        image_bytes: bytes,
        mime: str = "image/jpeg",
        max_tokens: int = 800,
    ) -> str:
        if not self.enabled:
            return ""
        data_uri = f"data:{mime};base64," + base64.b64encode(image_bytes).decode("ascii")
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                },
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
            "stream": False,
        }
        url = self.settings.vision_api_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.vision_api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(120, connect=20),
                transport=self.transport,
            ) as client:
                response = await client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise VisionServiceError("视觉模型请求超时") from exc
        except httpx.RequestError as exc:
            raise VisionServiceError("无法连接视觉模型服务") from exc

        if response.is_error:
            raise VisionServiceError(
                f"视觉模型请求失败（HTTP {response.status_code}）"
            )
        try:
            data = response.json()
            return (data["choices"][0]["message"].get("content") or "").strip()
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            raise VisionServiceError("视觉模型返回了无法识别的响应结构") from exc
