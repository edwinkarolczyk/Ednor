"""Orders repository placeholders."""
from typing import Optional
from uuid import UUID

from app.modules.orders.models import Order


class OrdersRepository:
    """CRUD interface without business logic."""

    def create(self, order: Order) -> None:
        pass

    def get(self, order_id: UUID) -> Optional[Order]:
        return None

    def update(self, order: Order) -> None:
        pass

    def delete(self, order_id: UUID) -> None:
        pass
