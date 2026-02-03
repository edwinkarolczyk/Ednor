"""Contractors module data models."""
from dataclasses import dataclass
from typing import Optional

from app.database.models_base import BaseModel


@dataclass
class Contractor(BaseModel):
    name: str = ""
    contact_person: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""
    notes: Optional[str] = None
