from fastapi import APIRouter

<<<<<<< HEAD
from app.api.routes import agents, chat, health, models, papers, videos
=======
from app.api.routes import agents, chat, conversations, health, learning, models, papers, videos
>>>>>>> 4c4558d (更新说明)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(papers.router, prefix="/papers", tags=["papers"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(conversations.router, prefix="/papers/{paper_id}/conversations", tags=["conversations"])
api_router.include_router(videos.router, prefix="/videos", tags=["videos"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(models.router, prefix="/models", tags=["models"])
