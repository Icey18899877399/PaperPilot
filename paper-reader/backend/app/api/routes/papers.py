import asyncio
from collections import Counter
from hashlib import sha256
from pathlib import Path
import shutil
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)

from app.core.config import get_settings
from app.models.schemas import (
    ConversationRecord,
    GuideResponse,
    MindMapResponse,
    PaperContentsResponse,
    PaperRecord,
    PaperStatus,
)
from app.models.schemas import TranslationRequest
from app.models.schemas import TranslationResponse
from app.services.runtime import runtime

router = APIRouter()


def _paper_upload_path(paper: PaperRecord) -> Path:
    uploads_root = get_settings().uploads_dir.resolve()
    upload_path = (uploads_root / Path(paper.file_url).name).resolve()
    if upload_path.parent != uploads_root:
        raise HTTPException(status_code=400, detail="论文文件路径不安全")
    return upload_path


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
) -> PaperContentsResponse:
    get_paper(paper_id)
    chunks = runtime.kb.all_chunks(paper_id)
    counts = dict(Counter(chunk.kind for chunk in chunks))
    items = [
        chunk
        for chunk in chunks
        if (kind is None or chunk.kind == kind) and (page is None or chunk.page == page)
    ]
    return PaperContentsResponse(
        paper_id=paper_id,
        total=len(items),
        counts=counts,
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
) -> GuideResponse:
    paper = get_paper(paper_id)
    if paper.status != PaperStatus.ready:
        raise HTTPException(status_code=409, detail="论文尚未解析完成")
    if not refresh:
        cached = runtime.store.load_guide(paper_id)
        if cached:
            return cached
    guide = await runtime.coordinator.run(
        "guide",
        paper_id=paper_id,
        filename=paper.filename,
    )
    runtime.store.save_guide(guide)
    return guide


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


# ── conversation management ────────────────────────────────────────


@router.get(
    "/{paper_id}/conversations",
    response_model=list[ConversationRecord],
)
def list_conversations(paper_id: str):
    get_paper(paper_id)
    return runtime.store.load_conversations(paper_id)


@router.get(
    "/{paper_id}/conversations/{conversation_id}",
    response_model=ConversationRecord,
)
def get_conversation(paper_id: str, conversation_id: str):
    conv = runtime.store.load_conversation(conversation_id)
    if not conv or conv.paper_id != paper_id:
        raise HTTPException(status_code=404, detail="对话不存在")
    return conv


@router.delete(
    "/{paper_id}/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_conversation(paper_id: str, conversation_id: str):
    conv = runtime.store.load_conversation(conversation_id)
    if not conv or conv.paper_id != paper_id:
        raise HTTPException(status_code=404, detail="对话不存在")
    runtime.store.delete_conversation(conversation_id)
