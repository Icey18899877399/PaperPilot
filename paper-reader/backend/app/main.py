from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import get_settings
from app.services.llm import LLMServiceError

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix="/api")
app.mount("/media/papers", StaticFiles(directory=settings.uploads_dir), name="papers")
app.mount("/media/videos", StaticFiles(directory=settings.videos_dir), name="videos")
app.mount("/media/assets", StaticFiles(directory=settings.assets_dir), name="assets")


@app.exception_handler(LLMServiceError)
async def llm_error_handler(
    request: Request,
    exc: LLMServiceError,
) -> JSONResponse:
    del request
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "docs": "/docs",
        "health": "/api/health",
    }
