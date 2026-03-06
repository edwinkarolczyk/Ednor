from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import Material, MaterialPrice, OrderMaterial, Reservation, Stock


def get_latest_material_unit_price(db: Session, material: Material) -> float | None:
    latest_price = db.scalar(
        select(MaterialPrice)
        .where(MaterialPrice.material_id == material.id)
        .order_by(MaterialPrice.valid_from.desc(), MaterialPrice.id.desc())
        .limit(1)
    )
    if not latest_price:
        return None

    stock_unit = (material.stock_unit or material.unit or "").strip().lower()
    if stock_unit == "mb":
        return latest_price.normalized_price_per_mb
    if stock_unit == "kg":
        return latest_price.normalized_price_per_kg
    if stock_unit == "szt":
        return latest_price.normalized_price_per_piece
    return None


def get_material_physical_reserved_available(db: Session, material_id: int) -> dict[str, float]:
    stock_row = db.get(Stock, material_id)
    physical_qty = float(stock_row.qty_on_hand if stock_row else 0.0)
    reserved_qty = float(
        db.scalar(
            select(func.coalesce(func.sum(Reservation.qty_reserved), 0.0)).where(
                Reservation.material_id == material_id,
                Reservation.status == "reserved",
            )
        )
        or 0.0
    )
    available_qty = physical_qty - reserved_qty
    return {
        "physical_qty": physical_qty,
        "reserved_qty": reserved_qty,
        "available_qty": available_qty,
    }


def determine_material_status(qty_required: float, qty_reserved: float) -> str:
    if qty_required > 0 and qty_reserved >= qty_required:
        return "ok"
    if 0 < qty_reserved < qty_required:
        return "partial"
    return "missing"


def estimate_material_weight(material: Material, qty_required: float) -> float | None:
    stock_unit = (material.stock_unit or material.unit or "").strip().lower()
    if stock_unit == "mb" and material.weight_per_meter_kg is not None:
        return qty_required * material.weight_per_meter_kg
    if stock_unit == "szt" and material.weight_per_piece_kg is not None:
        return qty_required * material.weight_per_piece_kg
    if stock_unit == "kg":
        return qty_required
    return None


def auto_reserve_order_material(db: Session, order_material: OrderMaterial) -> float:
    missing = float(order_material.qty_required - order_material.qty_reserved)
    if missing <= 0:
        order_material.material_status = determine_material_status(order_material.qty_required, order_material.qty_reserved)
        return 0.0

    availability = get_material_physical_reserved_available(db, order_material.material_id)
    reserve_qty = min(missing, max(availability["available_qty"], 0.0))

    if reserve_qty > 0:
        db.add(
            Reservation(
                order_id=order_material.order_id,
                material_id=order_material.material_id,
                qty_reserved=reserve_qty,
                status="reserved",
                note="Automatyczna rezerwacja z konfiguracji",
            )
        )
        order_material.qty_reserved += reserve_qty

    order_material.material_status = determine_material_status(order_material.qty_required, order_material.qty_reserved)
    return reserve_qty


def summarize_config_reservation_status(order_materials_for_config: list[OrderMaterial]) -> str:
    if not order_materials_for_config:
        return "missing"

    statuses = {material.material_status for material in order_materials_for_config}
    if statuses == {"ok"}:
        return "ok"
    if "partial" in statuses:
        return "partial"
    if statuses == {"missing"}:
        return "missing"
    return "partial"
