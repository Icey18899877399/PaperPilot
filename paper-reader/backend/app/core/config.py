from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "多Agent论文智能阅读系统"
    app_env: str = "development"
    backend_port: int = 8000
    frontend_origin: str = "http://localhost:5173"
    max_pdf_size_mb: int = 50

    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = ""

    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_thinking: bool = False

    mineru_api_url: str = ""
    mineru_api_token: str = ""
    mineru_backend: str = "pipeline"
    mineru_language: str = "ch"
    mineru_timeout_seconds: int = 3600

    openalex_api_key: str = ""
    crossref_mailto: str = ""
    youtube_api_key: str = ""
    learning_search_timeout_seconds: int = 20

    backend_dir: Path = Path(__file__).resolve().parents[2]

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def data_dir(self) -> Path:
        return self.backend_dir / "data"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def videos_dir(self) -> Path:
        return self.data_dir / "videos"

    @property
    def assets_dir(self) -> Path:
        return self.data_dir / "assets"

    @property
    def llm_provider(self) -> str:
        if self.deepseek_api_key:
            return "deepseek"
        if self.llm_api_key:
            return "openai-compatible"
        return "none"

    @property
    def effective_llm_base_url(self) -> str:
        if self.deepseek_api_key:
            return self.deepseek_base_url
        return self.llm_base_url

    @property
    def effective_llm_api_key(self) -> str:
        return self.deepseek_api_key or self.llm_api_key

    @property
    def effective_llm_model(self) -> str:
        if self.deepseek_api_key:
            return self.deepseek_model
        return self.llm_model


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.videos_dir.mkdir(parents=True, exist_ok=True)
    settings.assets_dir.mkdir(parents=True, exist_ok=True)
    return settings
