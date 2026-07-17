from __future__ import annotations

from dataclasses import dataclass, field

from app.agents.chat_agent import ChatAgent
from app.agents.coordinator import CoordinatorAgent
from app.agents.paper_agent import PaperUnderstandingAgent
from app.agents.translation_agent import TranslationAgent
from app.core.config import get_settings
from app.models.schemas import AgentLog, PaperRecord
from app.services.knowledge_base import KnowledgeBase
from app.services.learning import LearningService
from app.services.llm import LLMClient
from app.services.parser import PaperParser
from app.services.storage import PaperStore
from app.services.vector_index import VectorIndex
from app.services.video_catalog import VideoCatalog
from app.services.vision import VisionClient


@dataclass
class Runtime:
    papers: dict[str, PaperRecord] = field(default_factory=dict)
    logs: list[AgentLog] = field(default_factory=list)

    def __post_init__(self) -> None:
        settings = get_settings()
        # US-04：向量索引持久化到已被Git忽略的data/indexes目录，作为可检查
        # 的检索产物；配置EMBEDDING_API_URL后自动切换真实embedding服务
        vector_index = VectorIndex(
            embedding_api_url=settings.embedding_api_url,
            embedding_api_key=settings.embedding_api_key,
            embedding_model=settings.embedding_model,
            persist_dir=settings.data_dir / "indexes",
        )
        self.kb = KnowledgeBase(vector_index)
        self.parser = PaperParser(settings)
        self.store = PaperStore(settings.data_dir)
        self.llm = LLMClient(settings)
        self.videos = VideoCatalog(settings.videos_dir / "catalog.json")
        self.learning = LearningService(
            settings,
            self.kb,
            self.llm,
            self.videos,
            self.logs,
        )
        for paper in self.store.load_papers():
            self.papers[paper.id] = paper
            chunks = self.store.load_chunks(paper.id)
            if chunks:
                self.kb.index(paper.id, chunks)
        self.vision = VisionClient(settings)
        paper_agent = PaperUnderstandingAgent(
            self.kb,
            self.llm,
            self.logs,
            vision=self.vision,
            assets_dir=settings.assets_dir,
        )
        translation_agent = TranslationAgent(self.llm, self.logs)
        chat_agent = ChatAgent(self.kb, self.llm, self.videos, self.logs)
        self.coordinator = CoordinatorAgent(
            paper_agent,
            translation_agent,
            chat_agent,
            self.logs,
        )


runtime = Runtime()
