from typing import NoReturn

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.models.schemas import VideoResource, VideoUpdateRequest
from app.services.runtime import runtime
from app.services.video_catalog import (
    DuplicateVideoError,
    InvalidVideoError,
    VideoCatalogError,
    VideoNotFoundError,
)

router = APIRouter()


@router.get("", response_model=list[VideoResource])
def list_videos() -> list[VideoResource]:
    return runtime.videos.list()


@router.post("", response_model=VideoResource, status_code=status.HTTP_201_CREATED)
async def create_video(
    title: str = Form(...),
    description: str = Form(""),
    source: str = Form("本地维护"),
    keywords: str = Form(""),
    tags: str = Form(""),
    knowledge_points: str = Form(""),
    local_path: str = Form(""),
    file: UploadFile | None = File(None),
    cover: UploadFile | None = File(None),
) -> VideoResource:
    try:
        return runtime.videos.create(
            title=title,
            description=description,
            source=source,
            keywords=_split_terms(keywords),
            tags=_split_terms(tags),
            knowledge_points=_split_terms(knowledge_points),
            video_bytes=await file.read() if file else None,
            original_filename=file.filename if file else None,
            local_path=local_path.strip() or None,
            cover_bytes=await cover.read() if cover else None,
            cover_filename=cover.filename if cover else None,
        )
    except (DuplicateVideoError, InvalidVideoError, VideoCatalogError) as exc:
        _raise_video_error(exc)


@router.put("/{video_id}", response_model=VideoResource)
def update_video(video_id: str, payload: VideoUpdateRequest) -> VideoResource:
    try:
        return runtime.videos.update(video_id, payload)
    except (DuplicateVideoError, InvalidVideoError, VideoNotFoundError, VideoCatalogError) as exc:
        _raise_video_error(exc)


@router.delete("/{video_id}", response_model=VideoResource)
def delete_video(video_id: str, delete_file: bool = False) -> VideoResource:
    try:
        return runtime.videos.delete(video_id, delete_file=delete_file)
    except (VideoNotFoundError, VideoCatalogError) as exc:
        _raise_video_error(exc)


def _split_terms(value: str) -> list[str]:
    normalized = value.replace("，", ",").replace("；", ",").replace(";", ",")
    return [item.strip() for item in normalized.replace("\n", ",").split(",") if item.strip()]


def _raise_video_error(exc: Exception) -> NoReturn:
    if isinstance(exc, VideoNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, DuplicateVideoError):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(exc, InvalidVideoError):
        status_code = status.HTTP_400_BAD_REQUEST
    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    raise HTTPException(status_code=status_code, detail=str(exc)) from exc

