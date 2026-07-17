"""Conversation persistence layer for US-05 multi-turn chat.

Kept as a standalone service so it can be initialized with a data directory
and used directly by the chat route without modifying runtime or coordinator.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.models.schemas import ConversationRecord


class ConversationStore:
    """JSON file-based conversation persistence.

    File naming: {paper_id}-{conversation_id}.json under conversations_dir.
    """

    def __init__(self, conversations_dir: Path):
        self.dir = conversations_dir
        self.dir.mkdir(parents=True, exist_ok=True)

    # ── public API ──────────────────────────────────────────────────

    def load_list(self, paper_id: str) -> list[ConversationRecord]:
        """Return conversations for a paper, newest first."""
        conversations: list[ConversationRecord] = []
        for path in sorted(
            self.dir.glob(f"{paper_id}-*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                conversations.append(ConversationRecord.model_validate(payload))
            except (json.JSONDecodeError, KeyError):
                continue
        return conversations

    def load_one(self, conversation_id: str) -> ConversationRecord | None:
        """Find a conversation by its id (any paper)."""
        matches = list(self.dir.glob(f"*-{conversation_id}.json"))
        if not matches:
            return None
        try:
            return ConversationRecord.model_validate_json(
                matches[0].read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, KeyError):
            return None

    def save(self, conversation: ConversationRecord) -> None:
        """Persist a conversation."""
        conversation.updated_at = datetime.now(timezone.utc)
        path = self.dir / f"{conversation.paper_id}-{conversation.id}.json"
        self._atomic_write(path, conversation.model_dump(mode="json"))

    def delete(self, conversation_id: str) -> None:
        """Delete a conversation by id."""
        for path in self.dir.glob(f"*-{conversation_id}.json"):
            path.unlink(missing_ok=True)

    def clear_paper(self, paper_id: str) -> None:
        """Delete all conversations for a paper."""
        for path in self.dir.glob(f"{paper_id}-*.json"):
            path.unlink(missing_ok=True)

    # ── helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _atomic_write(path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)