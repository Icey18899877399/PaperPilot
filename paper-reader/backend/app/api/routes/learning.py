from fastapi import APIRouter, HTTPException, status

from app.models.schemas import LearningSearchRequest, LearningSearchResponse
from app.services.runtime import runtime

router = APIRouter()


@router.post("/search", response_model=LearningSearchResponse)
async def search_learning_resources(
    payload: LearningSearchRequest,
) -> LearningSearchResponse:
    paper = None
    if payload.paper_id:
        paper = runtime.papers.get(payload.paper_id)
        if paper is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="论文不存在",
            )
        if paper.status != "ready":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="论文尚未解析完成",
            )
    return await runtime.learning.search(payload, paper)
