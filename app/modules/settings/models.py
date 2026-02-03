"""Settings module data models."""
from dataclasses import dataclass

from app.database.models_base import BaseModel


@dataclass
class StatusDefinition(BaseModel):
    name: str = ""
    description: str = ""


@dataclass
class MaterialUnit(BaseModel):
    name: str = ""
    symbol: str = ""


@dataclass
class PriorityDefinition(BaseModel):
    name: str = ""
    description: str = ""


@dataclass
class AlertDefinition(BaseModel):
    name: str = ""
    level: str = ""


@dataclass
class QRDefinition(BaseModel):
    name: str = ""
    description: str = ""
