"""Alert structures."""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Alert:
    level: str
    source: str
    message: str
    created_at: datetime = field(default_factory=datetime.utcnow)
