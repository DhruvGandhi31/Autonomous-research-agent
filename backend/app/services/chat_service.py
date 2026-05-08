import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger


@dataclass
class FileAttachment:
    name: str
    file_type: str  # "image" | "pdf" | "docx"
    extracted_text: str
    description: str = ""
    size: int = 0


@dataclass
class ChatMessage:
    id: str
    role: str  # "user" | "assistant"
    content: str
    timestamp: str
    attachments: list = field(default_factory=list)
    research_id: Optional[str] = None
    sources: list = field(default_factory=list)


@dataclass
class ChatSession:
    id: str
    title: str
    created_at: str
    updated_at: str
    mode: str = "chat"  # "chat" | "research"
    messages: list = field(default_factory=list)


class ChatService:
    def __init__(self, data_dir: str = "./app/data/chat"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, ChatSession] = {}
        self._load_sessions()

    def _load_sessions(self):
        for f in self.data_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                messages = [ChatMessage(**m) for m in data.get("messages", [])]
                session = ChatSession(
                    id=data["id"],
                    title=data["title"],
                    created_at=data["created_at"],
                    updated_at=data["updated_at"],
                    mode=data.get("mode", "chat"),
                    messages=messages,
                )
                self._sessions[session.id] = session
            except Exception as e:
                logger.warning(f"Failed to load chat session {f}: {e}")

    def _save_session(self, session: ChatSession):
        path = self.data_dir / f"{session.id}.json"
        path.write_text(
            json.dumps(asdict(session), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def create_session(self, title: str = "New Chat", mode: str = "chat") -> ChatSession:
        session = ChatSession(
            id=str(uuid.uuid4()),
            title=title,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            mode=mode,
        )
        self._sessions[session.id] = session
        self._save_session(session)
        return session

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[ChatSession]:
        return sorted(
            self._sessions.values(), key=lambda s: s.updated_at, reverse=True
        )

    def delete_session(self, session_id: str) -> bool:
        if session_id not in self._sessions:
            return False
        del self._sessions[session_id]
        path = self.data_dir / f"{session_id}.json"
        if path.exists():
            path.unlink()
        return True

    def add_message(self, session_id: str, message: ChatMessage) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False
        session.messages.append(message)
        session.updated_at = datetime.now().isoformat()
        # Auto-title from first user message
        if len(session.messages) == 1 and message.role == "user":
            title = message.content[:60]
            session.title = title + ("..." if len(message.content) > 60 else "")
        self._save_session(session)
        return True

    def update_last_assistant_message(
        self, session_id: str, content: str, sources: list | None = None
    ) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False
        for msg in reversed(session.messages):
            if msg.role == "assistant":
                msg.content = content
                if sources is not None:
                    msg.sources = sources
                self._save_session(session)
                return True
        return False

    def get_conversation_history(
        self, session_id: str, limit: int = 20
    ) -> list[dict]:
        session = self._sessions.get(session_id)
        if not session:
            return []
        messages = session.messages[-limit:]
        history = []
        for m in messages:
            content = m.content
            if m.role == "user" and m.attachments:
                parts = []
                for att in m.attachments:
                    att_text = (
                        att.get("extracted_text", "")
                        if isinstance(att, dict)
                        else att.extracted_text
                    )
                    att_name = (
                        att.get("name", "file")
                        if isinstance(att, dict)
                        else att.name
                    )
                    if att_text:
                        parts.append(f"[Attached: {att_name}]\n{att_text}")
                if parts:
                    content = "\n\n".join(parts) + "\n\n" + content
            history.append({"role": m.role, "content": content})
        return history

    def rename_session(self, session_id: str, title: str) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False
        session.title = title[:100]
        self._save_session(session)
        return True


chat_service = ChatService()
