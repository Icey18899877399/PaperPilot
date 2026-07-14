from fastapi import APIRouter

from app.models.schemas import VideoResource
from app.services.runtime import runtime

router = APIRouter()


@router.get("", response_model=list[VideoResource])
def list_videos() -> list[VideoResource]:
    return runtime.videos.list()

