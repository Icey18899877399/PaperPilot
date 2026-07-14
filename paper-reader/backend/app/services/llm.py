from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.core.config import Settings
from app.models.schemas import LLMStatus


class LLMServiceError(RuntimeError):
    """Safe error returned by the model adapter without credentials."""


class LLMClient:
    """OpenAI-compatible adapter with first-class DeepSeek configuration."""

    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.settings = settings
        self.transport = transport

    @property
    def enabled(self) -> bool:
        key = self.settings.effective_llm_api_key
        if self.provider == "deepseek" and len(key) < 20:
            return False
        return bool(key and self.settings.effective_llm_model)

    @property
    def provider(self) -> str:
        return self.settings.llm_provider

    @property
    def model(self) -> str:
        return self.settings.effective_llm_model

    def status(self) -> LLMStatus:
        model = self.model
        warning = None
        if (
            self.provider == "deepseek"
            and self.settings.deepseek_api_key
            and len(self.settings.deepseek_api_key) < 20
        ):
            warning = "DeepSeek API Key长度异常，请重新运行安全配置脚本。"
        elif model in {"deepseek-chat", "deepseek-reasoner"}:
            warning = (
                "该旧模型名称将在2026-07-24停用，"
                "建议改为deepseek-v4-flash或deepseek-v4-pro。"
            )
        return LLMStatus(
            provider=self.provider,
            configured=self.enabled,
            base_url=self.settings.effective_llm_base_url,
            model=model,
            thinking=(
                self.provider == "deepseek"
                and self.settings.deepseek_thinking
            ),
            warning=warning,
        )

    async def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 1600,
    ) -> str:
        if not self.enabled:
            return ""
        payload = self._payload(system, user, max_tokens=max_tokens)
        data = await self._post(payload)
        content = data["choices"][0]["message"].get("content")
        return (content or "").strip()

    async def complete_json(
        self,
        system: str,
        user: str,
        max_tokens: int = 1600,
    ) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        payload = self._payload(system, user, max_tokens=max_tokens)
        payload["response_format"] = {"type": "json_object"}
        data = await self._post(payload)
        content = data["choices"][0]["message"].get("content") or ""
        cleaned = re.sub(r"^\s*```(?:json)?|\s*```\s*$", "", content.strip())
        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise LLMServiceError("模型返回内容不是有效JSON") from exc
        if not isinstance(result, dict):
            raise LLMServiceError("模型返回JSON必须是对象")
        return result

    def _payload(
        self,
        system: str,
        user: str,
        max_tokens: int = 1600,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if self.provider == "deepseek" and self.model.startswith("deepseek-v4"):
            payload["thinking"] = {
                "type": (
                    "enabled"
                    if self.settings.deepseek_thinking
                    else "disabled"
                )
            }
        return payload

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = (
            self.settings.effective_llm_base_url.rstrip("/")
            + "/chat/completions"
        )
        headers = {
            "Authorization": f"Bearer {self.settings.effective_llm_api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(120, connect=20),
                transport=self.transport,
            ) as client:
                response = await client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise LLMServiceError("模型服务请求超时") from exc
        except httpx.RequestError as exc:
            raise LLMServiceError("无法连接模型服务，请检查网络和BASE_URL") from exc

        if response.is_error:
            message = self._response_error(response)
            raise LLMServiceError(
                f"模型服务请求失败（HTTP {response.status_code}）：{message}"
            )
        try:
            data = response.json()
            choices = data["choices"]
            if not choices:
                raise KeyError("empty choices")
            return data
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMServiceError("模型服务返回了无法识别的响应结构") from exc

    def _response_error(self, response: httpx.Response) -> str:
        raw_text = response.text.strip()
        try:
            payload = response.json()
            error = payload.get("error", payload)
            if isinstance(error, dict):
                for key in ("message", "msg", "detail", "code"):
                    message = error.get(key)
                    if message:
                        return self._redact(str(message))[:300]
            elif error:
                return self._redact(str(error))[:300]
        except ValueError:
            pass
        if raw_text:
            return self._redact(raw_text)[:300]
        return "请检查API密钥、模型名称和账户余额"

    def _redact(self, text: str) -> str:
        secret = self.settings.effective_llm_api_key
        if secret:
            text = text.replace(secret, "[REDACTED]")
        return re.sub(r"sk-[A-Za-z0-9_-]{12,}", "[REDACTED]", text)
