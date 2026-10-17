from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class ErrorKind(StrEnum):
    FILTERED = "Отфильтровано"
    UNAVAILABLE = "Недоступно"
    PRIVATE = "Приватная статистика"
    FLOOD_WAIT = "Лимит Telegram"
    DELETED = "Удалено"
    FORBIDDEN = "Нет прав"
    NETWORK = "Сетевая ошибка"
    UNKNOWN = "Неизвестная ошибка"


@dataclass(slots=True)
class FilterConfig:
    excluded_words: list[str] = field(default_factory=list)
    min_users: int = 1
    active_only: bool = False
    public_only: bool = False
    language: str = ""
    writable_only: bool = False
    min_messages_24h: int = 0


@dataclass(slots=True)
class SearchCandidate:
    chat_id: int
    title: str
    username: str | None = None
    chat_type: str = "chat"
    participants: int | None = None
    access_hash: int | None = None

    @property
    def id(self) -> int:
        return self.chat_id

    @property
    def broadcast(self) -> bool:
        return self.chat_type == "channel"


@dataclass(slots=True)
class ChatResult:
    chat_id: int
    title: str
    username: str | None = None
    chat_type: str = "chat"
    participants: int | None = None
    can_write: bool = False
    voice_active: bool = False
    voice_type: str = ""
    last_activity: str = ""
    messages_24h: int = 0
    messages_7d: int = 0
    messages_30d: int = 0
    average_7d: float = 0.0
    average_30d: float = 0.0
    active_authors: int = 0
    views: int = 0
    reactions: int = 0
    engagement_rate: float = 0.0
    online_users: int | None = None
    audience_growth: int | None = None
    discussion_url: str = ""
    language: str = "unknown"
    score: float = 0.0
    collected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def url(self) -> str:
        return f"https://t.me/{self.username}" if self.username else ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class ScanError:
    chat_id: int | None
    title: str
    kind: ErrorKind
    message: str
    occurred_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
