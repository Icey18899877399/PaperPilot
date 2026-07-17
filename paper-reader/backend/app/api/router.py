from fastapi import APIRouter

from app.api.routes import agents, chat, health, learning, models, papers, videos

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(papers.router, prefix="/papers", tags=["papers"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(videos.router, prefix="/videos", tags=["videos"])
api_router.include_router(learning.router, prefix="/learning", tags=["learning"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(models.router, prefix="/models", tags=["models"])
