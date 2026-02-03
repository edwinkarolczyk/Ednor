"""Pricing module data models."""
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from app.database.models_base import BaseModel


@dataclass
class PricingTemplate(BaseModel):
    name: str = ""
    description: str = ""


@dataclass
class OrderPricing(BaseModel):
    order_id: Optional[UUID] = None
    template_id: Optional[UUID] = None
    notes: str = ""


@dataclass
class ProfitLossView(BaseModel):
    order_id: Optional[UUID] = None
    summary: str = ""
