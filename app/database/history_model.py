"""History of changes structure."""
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass
class HistoryEntry:
    object_id: UUID
    object_type: str
    field: str
    old_value: Any
    new_value: Any
    changed_at: datetime
