"""Application context storage."""
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class AppContext:
    """Shared application context without business logic."""

    database_path: str
    settings: Dict[str, Any] = field(default_factory=dict)
    user_info: Dict[str, Any] = field(default_factory=dict)
