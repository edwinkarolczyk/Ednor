"""Inventory module data models."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import UUID

from app.database.models_base import BaseModel


@dataclass
class Material(BaseModel):
    name: str = ""
    type_id: Optional[UUID] = None
    description: str = ""


@dataclass
class MaterialType(BaseModel):
    name: str = ""
    description: str = ""


@dataclass
class MaterialStock(BaseModel):
    material_id: Optional[UUID] = None
    quantity: Optional[float] = None
    location: str = ""


@dataclass
class MaterialPriceHistory(BaseModel):
    material_id: Optional[UUID] = None
    price: Optional[float] = None
    recorded_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class MaterialMovement(BaseModel):
    material_id: Optional[UUID] = None
    quantity: Optional[float] = None
    source: str = ""
    destination: str = ""


@dataclass
class MaterialReservation(BaseModel):
    material_id: Optional[UUID] = None
    reserved_for_order_id: Optional[UUID] = None
    quantity: Optional[float] = None


@dataclass
class MaterialAttachment(BaseModel):
    material_id: Optional[UUID] = None
    file_path: str = ""


@dataclass
class MaterialComment(BaseModel):
    material_id: Optional[UUID] = None
    author_id: Optional[UUID] = None
    content: str = ""
