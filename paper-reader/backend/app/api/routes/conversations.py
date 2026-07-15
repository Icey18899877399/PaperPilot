"""Conversation CRUD endpoints for US-05 multi-turn chat.

Registered under /api/papers/{paper_id}/conversations.
"""

from fastapi import APIRouter, HTTPException, status

from app.core.config import get_settings
from app.models.schemas import ConversationRecord
from app.services.conversation_store import ConversationStore

router = APIRouter()
_store = ConversationStore(get_settings().data_dir / "conversations")


@router.get("", response_model=list[ConversationRecord])
def list_conversations(paper_id: str) -> list[ConversationRecord]:
    """List all conversations for a paper, newest first."""
    return _store.load_list(paper_id)


@router.get("/{conversation_id}", response_model=ConversationRecord)
def get_conversation(paper_id: str, conversation_id: str) -> ConversationRecord:
    """Retrieve a single conversation by id."""
    conv = _store.load_one(conversation_id)
    if not conv or conv.paper_id != paper_id:
        raise HTTPException(status_code=404, detail="对话不存在")
    return conv


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_conversation(paper_id: str, conversation_id: str):
    """Delete a conversation."""
    conv = _store.load_one(conversation_id)
    if not conv or conv.paper_id != paper_id:
        raise HTTPException(status_code=404, detail="对话不存在")
    _store.delete(conversation_id)