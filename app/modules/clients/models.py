"""Clients module data models."""
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from app.database.models_base import BaseModel


@dataclass
class Client(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""


@dataclass
class ClientAttachment(BaseModel):
    client_id: Optional[UUID] = None
    file_path: str = ""


@dataclass
class ClientNote(BaseModel):
    client_id: Optional[UUID] = None
    author_id: Optional[UUID] = None
    note: str = ""
