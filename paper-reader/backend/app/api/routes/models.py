from time import perf_counter

from fastapi import APIRouter, HTTPException

from app.models.schemas import GuidePromptInfo, LLMStatus, LLMTestResponse
from app.prompts.guide import DEFAULT_GUIDE_PROMPT_KEY, list_guide_prompts
from app.services.llm import LLMServiceError
from app.services.runtime import runtime

router = APIRouter()


@router.get("/guide-prompts", response_model=list[GuidePromptInfo])
def guide_prompts() -> list[GuidePromptInfo]:
    """列出US-02导读提示词版本，前端据此渲染"导读风格"选择。"""
    return [
        GuidePromptInfo(
            key=version.key,
            name=version.name,
            domain=version.domain,
            audience=version.audience,
            description=version.description,
            is_default=version.key == DEFAULT_GUIDE_PROMPT_KEY,
        )
        for version in list_guide_prompts()
    ]


@router.get("/status", response_model=LLMStatus)
def model_status() -> LLMStatus:
    return runtime.llm.status()


@router.post("/test", response_model=LLMTestResponse)
async def test_model_connection() -> LLMTestResponse:
    status = runtime.llm.status()
    if not status.configured:
        raise HTTPException(status_code=409, detail="尚未配置模型API密钥")

    started = perf_counter()
    try:
        answer = await runtime.llm.complete(
            "你是连接测试助手，只能回答OK。",
            "请回答OK",
        )
    except LLMServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    latency_ms = round((perf_counter() - started) * 1000)
    if not answer:
        raise HTTPException(status_code=502, detail="模型返回了空内容")
    return LLMTestResponse(
        success=True,
        provider=status.provider,
        model=status.model,
        latency_ms=latency_ms,
        message="模型连接成功",
    )
