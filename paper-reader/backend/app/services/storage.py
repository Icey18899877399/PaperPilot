from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from app.models.schemas import (
    BilingualPageResponse,
    GuideResponse,
    MindMapResponse,
    PaperChunk,
    PaperRecord,
)


class PaperStore:
    """Small JSON persistence layer for the course MVP.

    It keeps persistence behind a service boundary so SQLite/PostgreSQL and a
    real vector database can replace it without changing API routes or agents.
    """

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.papers_file = data_dir / "papers.json"
        self.indexes_dir = data_dir / "indexes"
        self.guides_dir = data_dir / "guides"
        self.mindmaps_dir = data_dir / "mindmaps"
        self.translations_dir = data_dir / "translations"
        self.indexes_dir.mkdir(parents=True, exist_ok=True)
        self.guides_dir.mkdir(parents=True, exist_ok=True)
        self.mindmaps_dir.mkdir(parents=True, exist_ok=True)
        self.translations_dir.mkdir(parents=True, exist_ok=True)

    def load_papers(self) -> list[PaperRecord]:
        if not self.papers_file.exists():
            return []
        payload = json.loads(self.papers_file.read_text(encoding="utf-8"))
        return [PaperRecord.model_validate(item) for item in payload]

    def save_paper(self, paper: PaperRecord) -> None:
        papers = {item.id: item for item in self.load_papers()}
        papers[paper.id] = paper
        payload = [
            item.model_dump(mode="json")
            for item in sorted(papers.values(), key=lambda value: value.created_at)
        ]
        self._atomic_write(self.papers_file, payload)

    def load_chunks(self, paper_id: str) -> list[PaperChunk]:
        path = self.indexes_dir / f"{paper_id}.json"
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [PaperChunk.model_validate(item) for item in payload]

    def save_chunks(self, paper_id: str, chunks: list[PaperChunk]) -> None:
        path = self.indexes_dir / f"{paper_id}.json"
        self._atomic_write(
            path,
            [chunk.model_dump(mode="json") for chunk in chunks],
        )

    def load_guide(self, paper_id: str) -> GuideResponse | None:
        path = self.guides_dir / f"{paper_id}.json"
        if not path.exists():
            return None
        return GuideResponse.model_validate_json(path.read_text(encoding="utf-8"))

    def save_guide(self, guide: GuideResponse) -> None:
        path = self.guides_dir / f"{guide.paper_id}.json"
        self._atomic_write(path, guide.model_dump(mode="json"))

    def load_mind_map(self, paper_id: str) -> MindMapResponse | None:
        path = self.mindmaps_dir / f"{paper_id}.json"
        if not path.exists():
            return None
        return MindMapResponse.model_validate_json(path.read_text(encoding="utf-8"))

    def save_mind_map(self, mind_map: MindMapResponse) -> None:
        path = self.mindmaps_dir / f"{mind_map.paper_id}.json"
        self._atomic_write(path, mind_map.model_dump(mode="json"))

    def load_bilingual_page(
        self,
        paper_id: str,
        page: int,
        target_language: str,
    ) -> BilingualPageResponse | None:
        path = self._translation_path(paper_id, page, target_language)
        if not path.exists():
            return None
        return BilingualPageResponse.model_validate_json(
            path.read_text(encoding="utf-8")
        )

    def save_bilingual_page(self, result: BilingualPageResponse) -> None:
        path = self._translation_path(
            result.paper_id,
            result.page,
            result.target_language,
        )
        self._atomic_write(path, result.model_dump(mode="json"))

    def delete_paper(self, paper_id: str) -> None:
        remaining = [paper for paper in self.load_papers() if paper.id != paper_id]
        self._atomic_write(
            self.papers_file,
            [paper.model_dump(mode="json") for paper in remaining],
        )
        self.clear_derived_data(paper_id)

    def clear_derived_data(self, paper_id: str) -> None:
        (self.indexes_dir / f"{paper_id}.json").unlink(missing_ok=True)
        (self.guides_dir / f"{paper_id}.json").unlink(missing_ok=True)
        (self.mindmaps_dir / f"{paper_id}.json").unlink(missing_ok=True)
        for path in self.translations_dir.glob(f"{paper_id}-*.json"):
            path.unlink(missing_ok=True)

    def _translation_path(
        self,
        paper_id: str,
        page: int,
        target_language: str,
    ) -> Path:
        language_key = sha256(target_language.encode("utf-8")).hexdigest()[:12]
        return self.translations_dir / f"{paper_id}-{page}-{language_key}.json"

    @staticmethod
    def _atomic_write(path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)
