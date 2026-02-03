"""User action logging placeholders."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List
from uuid import UUID


@dataclass
class ActionLogEntry:
    user_id: UUID
    action: str
    context: str
    occurred_at: datetime = field(default_factory=datetime.utcnow)


class UserActionLogger:
    """Collects user actions without processing logic."""

    def __init__(self) -> None:
        self.entries: List[ActionLogEntry] = []

    def record(self, entry: ActionLogEntry) -> None:
        self.entries.append(entry)
