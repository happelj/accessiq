from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock
from uuid import uuid4

from .models import Conversation, ConversationMessage


class ConversationStore:
    def __init__(self) -> None:
        self._conversations: dict[str, Conversation] = {}
        self._lock = Lock()

    def get_or_create(
        self,
        conversation_id: str | None = None,
        *,
        metadata: dict[str, object] | None = None,
    ) -> Conversation:
        now = _utc_now()
        with self._lock:
            if conversation_id is not None and conversation_id in self._conversations:
                return self._conversations[conversation_id]

            resolved_id = conversation_id or str(uuid4())
            conversation = Conversation(
                conversation_id=resolved_id,
                messages=[],
                metadata=dict(metadata or {}),
                created_at=now,
                updated_at=now,
            )
            self._conversations[resolved_id] = conversation
            return conversation

    def append_message(
        self,
        conversation_id: str,
        *,
        role: str,
        content: str,
        metadata: dict[str, object] | None = None,
    ) -> ConversationMessage:
        message = ConversationMessage(
            role=role,  # type: ignore[arg-type]
            content=content,
            created_at=_utc_now(),
            metadata=dict(metadata or {}),
        )
        with self._lock:
            conversation = self._conversations[conversation_id]
            conversation.messages.append(message)
            conversation.updated_at = message.created_at
            return message


conversation_store = ConversationStore()


def _utc_now() -> datetime:
    return datetime.now(UTC)
