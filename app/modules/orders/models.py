"""Orders module data models."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import UUID

from app.database.models_base import BaseModel


@dataclass
class Order(BaseModel):
    client_id: Optional[UUID] = None
    title: str = ""
    description: str = ""
    status_id: Optional[UUID] = None


@dataclass
class OrderMaterial(BaseModel):
    order_id: Optional[UUID] = None
    material_id: Optional[UUID] = None
    quantity: Optional[float] = None


@dataclass
class OrderCost(BaseModel):
    order_id: Optional[UUID] = None
    label: str = ""
    amount: Optional[float] = None


@dataclass
class OrderAttachment(BaseModel):
    order_id: Optional[UUID] = None
    file_path: str = ""


@dataclass
class OrderComment(BaseModel):
    order_id: Optional[UUID] = None
    author_id: Optional[UUID] = None
    content: str = ""


@dataclass
class OrderStatus(BaseModel):
    name: str = ""
    description: str = ""


@dataclass
class OrderQRCode(BaseModel):
    order_id: Optional[UUID] = None
    payload: str = ""
    generated_at: datetime = field(default_factory=datetime.utcnow)
