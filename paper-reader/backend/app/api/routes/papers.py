import asyncio
from collections import Counter
from hashlib import sha256
from pathlib import Path
import shutil
from uuid import uuid4

from pypdf import PdfReader

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse

from app.api.sse import sse_event
from app.core.config import get_settings
from app.models.schemas import (
    BilingualPageResponse,
    ChunkExplanationResponse,
    GuideResponse,
    MindMapResponse,
    PaperContentsResponse,
    PaperChunk,
    PaperRecord,
    PaperStatus,
    RetrievalDebugResponse,
    RetrievalHit,
)
from app.models.schemas import TranslationRequest
from app.models.schemas import TranslationResponse
from app.services.knowledge_base import classify_display_zones
from app.services.llm import LLMServiceError
from app.services.runtime import runtime

router = APIRouter()


def _paper_upload_path(paper: PaperRecord) -> Path:
    uploads_root = get_settings().uploads_dir.resolve()
    upload_path = (uploads_root / Path(paper.file_url).name).resolve()
    if upload_path.parent != uploads_root:
        raise HTTPException(status_code=400, detail="论文文件路径不安全")
    return upload_path


def _extract_page_layout_text(paper: PaperRecord, page: int) -> str:
    upload_path = _paper_upload_path(paper)
    if not upload_path.is_file():
        return ""
    try:
        pdf_page = PdfReader(str(upload_path)).pages[page - 1]
        try:
            raw_text = pdf_page.extract_text(extraction_mode="layout") or ""
        except TypeError:
            raw_text = pdf_page.extract_text() or ""
    except (IndexError, OSError, ValueError):
        return ""
    lines = [line.rstrip() for line in raw_text.splitlines() if line.strip()]
    return "\n".join(lines).strip()[:12000]


def _needs_table_text_fallback(chunk: PaperChunk) -> bool:
    if chunk.kind != "table":
        return False
    table_text = str(chunk.metadata.get("table_text") or "").strip()
    # MinerU may return only an image/caption for a visually complex table.
    # The PDF text layer is still useful in that case, so do not restrict the
    # fallback to the exact placeholder string.
    return not table_text


def _enrich_table_chunks(
    paper: PaperRecord,
    chunks: list[PaperChunk],
) -> list[PaperChunk]:
    page_texts: dict[int, str] = {}
    enriched: list[PaperChunk] = []
    for chunk in chunks:
        if not _needs_table_text_fallback(chunk):
            enriched.append(chunk)
            continue
        if chunk.page not in page_texts:
            page_texts[chunk.page] = _extract_page_layout_text(paper, chunk.page)
        page_text = page_texts[chunk.page]
        if not page_text:
            enriched.append(chunk)
            continue
        updated = chunk.model_copy(deep=True)
        updated.content = f"[表格]\n{page_text}"
        updated.metadata["table_text"] = page_text
        updated.metadata["table_text_source"] = "pypdf-page-layout-fallback"
        enriched.append(updated)
    return enriched


def _cached_bilingual_has_placeholder_table(result: BilingualPageResponse) -> bool:
    for block in result.blocks:
        if block.kind != "table":
            continue
        if str(block.metadata.get("table_text") or "").strip():
            continue
        source = block.source_text.strip()
        body = source.removeprefix("[表格]").strip()
        caption = str(block.metadata.get("caption") or "").strip()
        if (
            not body
            or body in {"该页包含一张表格", "This page contains a table."}
            or (caption and body == caption)
        ):
            return True
    return False


def _find_duplicate(file_sha256: str) -> PaperRecord | None:
    for paper in runtime.papers.values():
        known_sha256 = paper.file_sha256
        if not known_sha256:
            upload_path = _paper_upload_path(paper)
            if upload_path.is_file():
                known_sha256 = sha256(upload_path.read_bytes()).hexdigest()
                paper.file_sha256 = known_sha256
                paper.file_size = upload_path.stat().st_size
                runtime.store.save_paper(paper)
        if known_sha256 == file_sha256:
            return paper
    return None


def _clear_parse_outputs(paper_id: str) -> None:
    settings = get_settings()
    assets_root = settings.assets_dir.resolve()
    paper_assets = (assets_root / paper_id).resolve()
    if paper_assets.parent != assets_root:
        raise HTTPException(status_code=400, detail="论文资源路径不安全")
    if paper_assets.is_dir():
        shutil.rmtree(paper_assets)
    runtime.kb.remove(paper_id)
    runtime.store.clear_derived_data(paper_id)


async def _parse_and_index(paper_id: str, destination: Path) -> None:
    record = runtime.papers[paper_id]
    record.status = PaperStatus.parsing
    record.progress = 10
    record.stage = "MinerU结构化解析中"
    record.error = None
    runtime.store.save_paper(record)
    try:
        parse_task = asyncio.create_task(runtime.parser.parse(paper_id, destination))
        while True:
            try:
                page_count, chunks = await asyncio.wait_for(
                    asyncio.shield(parse_task),
                    timeout=15,
                )
                break
            except TimeoutError:
                record.progress = min(75, record.progress + 5)
                record.stage = f"MinerU结构化解析中（估算{record.progress}%）"
                runtime.store.save_paper(record)
        record.progress = 85
        record.stage = "构建论文检索索引"
        runtime.store.save_paper(record)
        runtime.kb.index(paper_id, chunks)
        runtime.store.save_chunks(paper_id, chunks)
        record.page_count = page_count
        record.progress = 92
        record.stage = "自动生成论文导读"
        runtime.store.save_paper(record)
        try:
            guide = await runtime.coordinator.run(
                "guide",
                paper_id=paper_id,
                filename=record.filename,
            )
            runtime.store.save_guide(guide)
            record.stage = "解析完成，导读已生成"
        except Exception as guide_error:
            record.stage = "解析完成，导读生成失败，可手动重试"
            record.error = f"自动导读生成失败：{guide_error}"
        record.status = PaperStatus.ready
        record.progress = 100
    except Exception as exc:
        record.status = PaperStatus.failed
        record.progress = 100
        record.stage = "解析失败"
        record.error = str(exc)
    runtime.store.save_paper(record)


@router.post("", response_model=PaperRecord, status_code=201)
async def upload_paper(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    background: bool = Query(
        default=False,
        description="为true时后台解析并立即返回论文状态；默认为同步模式以兼容脚本调用",
    ),
) -> PaperRecord:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持PDF文件")

    settings = get_settings()
    max_bytes = settings.max_pdf_size_mb * 1024 * 1024
    payload = await file.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"PDF文件不能超过{settings.max_pdf_size_mb}MB",
        )
    if not payload.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="文件内容不是有效的PDF")

    file_sha256 = sha256(payload).hexdigest()
    duplicate = _find_duplicate(file_sha256)
    if duplicate:
        action = "请使用重新解析" if duplicate.status == PaperStatus.failed else "请直接选择已有论文"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"检测到重复论文：{duplicate.filename}（ID：{duplicate.id}），{action}",
        )

    paper_id = uuid4().hex
    safe_name = Path(file.filename).name
    destination = settings.uploads_dir / f"{paper_id}-{safe_name}"
    destination.write_bytes(payload)
    record = PaperRecord(
        id=paper_id,
        filename=safe_name,
        file_url=f"/media/papers/{destination.name}",
        file_sha256=file_sha256,
        file_size=len(payload),
        status=PaperStatus.parsing,
        progress=5,
        stage="PDF已上传，等待解析",
    )
    runtime.papers[paper_id] = record
    runtime.store.save_paper(record)

    if background:
        background_tasks.add_task(_parse_and_index, paper_id, destination)
    else:
        await _parse_and_index(paper_id, destination)
    return record


@router.get("", response_model=list[PaperRecord])
def list_papers() -> list[PaperRecord]:
    return list(runtime.papers.values())


@router.get("/{paper_id}", response_model=PaperRecord)
def get_paper(paper_id: str) -> PaperRecord:
    paper = runtime.papers.get(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")
    return paper


@router.post("/{paper_id}/retry", response_model=PaperRecord)
async def retry_paper(
    paper_id: str,
    background_tasks: BackgroundTasks,
    background: bool = Query(default=True, description="为true时在后台重新解析"),
) -> PaperRecord:
    paper = get_paper(paper_id)
    if paper.status != PaperStatus.failed:
        raise HTTPException(status_code=409, detail="只有解析失败的论文可以重新解析")
    upload_path = _paper_upload_path(paper)
    if not upload_path.is_file():
        raise HTTPException(status_code=404, detail="原始PDF不存在，无法重新解析")

    _clear_parse_outputs(paper_id)
    paper.status = PaperStatus.parsing
    paper.progress = 5
    paper.stage = "等待重新解析"
    paper.error = None
    runtime.store.save_paper(paper)
    if background:
        background_tasks.add_task(_parse_and_index, paper_id, upload_path)
    else:
        await _parse_and_index(paper_id, upload_path)
    return paper


@router.delete("/{paper_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_paper(paper_id: str) -> Response:
    paper = get_paper(paper_id)
    if paper.status == PaperStatus.parsing:
        raise HTTPException(status_code=409, detail="论文正在解析，暂时不能删除")

    upload_path = _paper_upload_path(paper)
    upload_path.unlink(missing_ok=True)
    _clear_parse_outputs(paper_id)
    runtime.store.delete_paper(paper_id)
    runtime.papers.pop(paper_id, None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{paper_id}/contents", response_model=PaperContentsResponse)
def list_paper_contents(
    paper_id: str,
    kind: str | None = Query(default=None),
    page: int | None = Query(default=None, ge=1),
    include_all: bool = Query(
        default=False,
        description="为true时包含作者区/References/Appendix的版面块；默认只展示正文区",
    ),
) -> PaperContentsResponse:
    get_paper(paper_id)
    chunks = runtime.kb.all_chunks(paper_id)

    def matches(chunk: PaperChunk) -> bool:
        return (kind is None or chunk.kind == kind) and (
            page is None or chunk.page == page
        )

    # 默认视图过滤作者区/参考文献/附录的碎块（US-01核对需求用 include_all=true 查看全部）
    if include_all:
        visible = chunks
        hidden = 0
    else:
        zones = classify_display_zones(chunks)

        def zone_visible(chunk: PaperChunk) -> bool:
            # 分区过滤只治理正文/列表碎片；图/图表/表格/公式/代码等多模态内容
            # 稀少且有核对价值，即便位于附录（如附录B中的公式）也照常展示
            if chunk.kind not in {"text", "list"}:
                return True
            return zones.get(chunk.chunk_id, "body") == "body"

        visible = [chunk for chunk in chunks if zone_visible(chunk)]
        hidden = sum(1 for chunk in chunks if matches(chunk)) - sum(
            1 for chunk in visible if matches(chunk)
        )

    counts = dict(Counter(chunk.kind for chunk in visible))
    items = [chunk for chunk in visible if matches(chunk)]
    return PaperContentsResponse(
        paper_id=paper_id,
        total=len(items),
        counts=counts,
        items=items,
        hidden=hidden,
    )


@router.get("/{paper_id}/search", response_model=RetrievalDebugResponse)
def search_paper(
    paper_id: str,
    q: str = Query(min_length=1, max_length=200, description="检索问题"),
    limit: int = Query(default=5, ge=1, le=20),
) -> RetrievalDebugResponse:
    """检索调试接口（US-04：检索测试能够展示召回片段及相关度）。"""
    get_paper(paper_id)
    scored = runtime.kb.search_scored(paper_id, q, limit)
    items = [
        RetrievalHit(
            chunk_id=chunk.chunk_id,
            page=chunk.page,
            kind=chunk.kind,
            score=score,
            section_path=[
                str(value) for value in chunk.metadata.get("section_path", [])
            ],
            excerpt=chunk.content[:280],
        )
        for score, chunk in scored
    ]
    return RetrievalDebugResponse(
        paper_id=paper_id,
        query=q,
        vector_backend=runtime.kb.vector_index.backend_name(paper_id),
        total_indexed=len(runtime.kb.retrieval_chunks(paper_id)),
        items=items,
    )


@router.get("/{paper_id}/guide", response_model=GuideResponse)
def get_cached_guide(paper_id: str) -> GuideResponse:
    get_paper(paper_id)
    cached = runtime.store.load_guide(paper_id)
    if not cached:
        raise HTTPException(status_code=404, detail="尚未生成论文导读")
    return cached


@router.post("/{paper_id}/guide", response_model=GuideResponse)
async def create_guide(
    paper_id: str,
    refresh: bool = Query(default=False, description="为true时忽略缓存并重新生成"),
    prompt_key: str | None = Query(
        default=None,
        description="导读提示词版本（见app/prompts/guide.py注册表），缺省用通用学术版",
    ),
) -> GuideResponse:
    paper = get_paper(paper_id)
    if paper.status != PaperStatus.ready:
        raise HTTPException(status_code=409, detail="论文尚未解析完成")
    if not refresh:
        cached = runtime.store.load_guide(paper_id)
        if cached:
            return cached
    try:
        guide = await runtime.coordinator.run(
            "guide",
            paper_id=paper_id,
            filename=paper.filename,
            prompt_key=prompt_key,
        )
    except LLMServiceError as exc:
        # Agent内部已有降级路径，此处兜底覆盖其余模型异常，避免裸500（US-02）
        raise HTTPException(status_code=502, detail=f"导读生成失败：{exc}") from exc
    runtime.store.save_guide(guide)
    return guide


@router.post("/{paper_id}/guide/stream")
async def create_guide_stream(
    paper_id: str,
    request: Request,
    refresh: bool = Query(default=False, description="为true时忽略缓存并重新生成"),
    prompt_key: str | None = Query(default=None, description="导读提示词版本"),
) -> StreamingResponse:
    """US-02导读SSE：持续回传阶段和生成量，完成后发送严格结构化结果。"""
    paper = get_paper(paper_id)
    if paper.status != PaperStatus.ready:
        raise HTTPException(status_code=409, detail="论文尚未解析完成")

    async def events():
        if not refresh:
            cached = runtime.store.load_guide(paper_id)
            if cached:
                yield sse_event("complete", cached.model_dump(mode="json"))
                return

        queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()
        generated_chars = 0

        async def on_delta(delta: str) -> None:
            nonlocal generated_chars
            previous = generated_chars
            generated_chars += len(delta)
            # 每约120字报告一次进度，避免逐token事件拖慢浏览器主线程。
            if generated_chars < 80 or previous // 120 != generated_chars // 120:
                await queue.put(
                    (
                        "progress",
                        {
                            "chars": generated_chars,
                            "message": f"正在组织结构化导读 · 已生成约{generated_chars}字",
                        },
                    )
                )

        async def generate() -> None:
            try:
                guide = await runtime.coordinator.run(
                    "guide",
                    paper_id=paper_id,
                    filename=paper.filename,
                    prompt_key=prompt_key,
                    on_delta=on_delta,
                )
                runtime.store.save_guide(guide)
                await queue.put(("complete", guide.model_dump(mode="json")))
            except Exception as exc:
                message = (
                    f"导读生成失败：{exc}"
                    if isinstance(exc, LLMServiceError)
                    else "导读生成失败，请稍后重试"
                )
                await queue.put(("error", {"message": message}))

        yield sse_event("status", {"message": "正在采样全文并核对关键章节"})
        task = asyncio.create_task(generate())
        try:
            while True:
                if await request.is_disconnected():
                    task.cancel()
                    return
                try:
                    event, data = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield sse_event(event, data)
                if event in {"complete", "error"}:
                    return
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{paper_id}/mind-map", response_model=MindMapResponse)
def get_cached_mind_map(paper_id: str) -> MindMapResponse:
    get_paper(paper_id)
    cached = runtime.store.load_mind_map(paper_id)
    if not cached:
        raise HTTPException(status_code=404, detail="尚未生成思维导图")
    return cached


@router.post("/{paper_id}/mind-map", response_model=MindMapResponse)
async def create_mind_map(
    paper_id: str,
    refresh: bool = Query(default=False, description="为true时忽略缓存并重新生成"),
) -> MindMapResponse:
    paper = get_paper(paper_id)
    if paper.status != PaperStatus.ready:
        raise HTTPException(status_code=409, detail="论文尚未解析完成")
    if not refresh:
        cached = runtime.store.load_mind_map(paper_id)
        if cached:
            return cached
    mind_map = await runtime.coordinator.run(
        "mind-map",
        paper_id=paper_id,
        filename=paper.filename,
    )
    runtime.store.save_mind_map(mind_map)
    return mind_map


@router.post("/{paper_id}/translate", response_model=TranslationResponse)
async def translate(
    paper_id: str,
    request: TranslationRequest,
) -> TranslationResponse:
    get_paper(paper_id)
    return await runtime.coordinator.run(
        "translate",
        text=request.text,
        target_language=request.target_language,
    )


@router.get(
    "/{paper_id}/bilingual/{page}",
    response_model=BilingualPageResponse,
)
def get_cached_bilingual_page(
    paper_id: str,
    page: int,
    target_language: str = Query(default="中文"),
) -> BilingualPageResponse:
    paper = get_paper(paper_id)
    if page < 1 or (paper.page_count and page > paper.page_count):
        raise HTTPException(status_code=404, detail="论文页码不存在")
    cached = runtime.store.load_bilingual_page(paper_id, page, target_language)
    if not cached or _cached_bilingual_has_placeholder_table(cached):
        raise HTTPException(status_code=404, detail="本页尚未生成中文译文")
    return cached


@router.post(
    "/{paper_id}/bilingual/{page}",
    response_model=BilingualPageResponse,
)
async def create_bilingual_page(
    paper_id: str,
    page: int,
    target_language: str = Query(default="中文"),
    refresh: bool = Query(default=False),
) -> BilingualPageResponse:
    paper = get_paper(paper_id)
    if paper.status != PaperStatus.ready:
        raise HTTPException(status_code=409, detail="论文尚未解析完成")
    if page < 1 or (paper.page_count and page > paper.page_count):
        raise HTTPException(status_code=404, detail="论文页码不存在")
    if not refresh:
        cached = runtime.store.load_bilingual_page(paper_id, page, target_language)
        if cached and not _cached_bilingual_has_placeholder_table(cached):
            return cached

    chunks = [
        chunk
        for chunk in runtime.kb.all_chunks(paper_id)
        if chunk.page == page
        and chunk.kind in {"text", "list", "image", "chart", "table", "equation", "code"}
    ]
    chunks = _enrich_table_chunks(paper, chunks)
    if not chunks:
        raise HTTPException(status_code=404, detail="本页没有可用于对照阅读的解析内容")
    trace_id = runtime.coordinator.new_trace_id()
    blocks = await runtime.coordinator.run(
        "translate-page",
        trace_id=trace_id,
        chunks=chunks,
        target_language=target_language,
    )
    result = BilingualPageResponse(
        paper_id=paper_id,
        page=page,
        target_language=target_language,
        blocks=blocks,
        agent_trace_id=trace_id,
    )
    runtime.store.save_bilingual_page(result)
    return result


@router.post(
    "/{paper_id}/chunks/{chunk_id}/explanation",
    response_model=ChunkExplanationResponse,
)
async def explain_chunk(
    paper_id: str,
    chunk_id: str,
    refresh: bool = Query(default=False, description="为true时忽略缓存并重新解释"),
) -> ChunkExplanationResponse:
    paper = get_paper(paper_id)
    if paper.status != PaperStatus.ready:
        raise HTTPException(status_code=409, detail="论文尚未解析完成")
    chunk = next(
        (item for item in runtime.kb.all_chunks(paper_id) if item.chunk_id == chunk_id),
        None,
    )
    if chunk is None:
        raise HTTPException(status_code=404, detail="论文切片不存在")
    # 命中缓存直接返回，避免同一切片反复点击重复消耗模型（US-04 派生数据持久化）
    if not refresh:
        cached = runtime.store.load_chunk_explanation(paper_id, chunk_id)
        if cached:
            return cached
    enriched = _enrich_table_chunks(paper, [chunk])[0]
    try:
        result = await runtime.coordinator.run(
            "explain-chunk",
            paper_id=paper_id,
            filename=paper.filename,
            chunk=enriched,
        )
    except LLMServiceError as exc:
        # 模型服务异常返回结构化502，而非裸500
        raise HTTPException(status_code=502, detail=f"切片解释失败：{exc}") from exc
    # 仅在有可用模型时缓存（无模型的兜底文案不落盘，配置模型后无需刷新即可生成真解释）
    if runtime.llm.enabled or runtime.vision.enabled:
        runtime.store.save_chunk_explanation(result)
    return result
