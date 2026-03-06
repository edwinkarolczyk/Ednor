from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.materials_engine import normalize_price, normalize_quantity_for_stock
from app.db import INVENTORY_CATEGORIES, Material, MaterialPrice, Reservation, Stock, StockMove, get_db, material_stock_state
from app.security import get_current_user

router = APIRouter(tags=["inventory"])

STOCK_UNITS = ["mb", "kg", "szt"]
PURCHASE_PRICING_MODES = ["per_kg", "per_mb", "per_piece", "mixed"]


def set_templates(templates_obj: Jinja2Templates):
    globals()["templates"] = templates_obj


def _parse_optional_float(raw: str) -> float | None:
    value = (raw or "").strip().replace(",", ".")
    if not value:
        return None
    return float(value)


def _format_latest_price_for_material(material: Material, price: MaterialPrice | None) -> str:
    if not price:
        return "brak ceny"

    stock_unit = (material.stock_unit or material.unit or "").strip().lower()
    if stock_unit == "mb" and price.normalized_price_per_mb is not None:
        return f"{price.normalized_price_per_mb:.2f} PLN/mb"
    if stock_unit == "kg" and price.normalized_price_per_kg is not None:
        return f"{price.normalized_price_per_kg:.2f} PLN/kg"
    if stock_unit == "szt" and price.normalized_price_per_piece is not None:
        return f"{price.normalized_price_per_piece:.2f} PLN/szt"

    if price.input_price is not None and price.input_unit:
        return f"{price.input_price:.2f} PLN/{price.input_unit}"
    if price.price is not None:
        return f"{price.price:.2f} PLN"
    return "brak ceny"


@router.get("/inventory")
def inventory_page(
    request: Request,
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    materials = db.scalars(select(Material).options(joinedload(Material.stock_row)).order_by(Material.code)).unique().all()
    deduped_latest_prices: dict[int, MaterialPrice] = {}
    for price in db.scalars(select(MaterialPrice).order_by(MaterialPrice.material_id, MaterialPrice.valid_from.desc())).all():
        deduped_latest_prices.setdefault(price.material_id, price)
    material_states = {material.id: material_stock_state(db, material.id) for material in materials}
    latest_prices_display = {
        material.id: _format_latest_price_for_material(material, deduped_latest_prices.get(material.id)) for material in materials
    }

    return templates.TemplateResponse(
        "inventory.html",
        {
            "request": request,
            "page_title": "Magazyn",
            "materials": materials,
            "latest_prices_display": latest_prices_display,
            "material_states": material_states,
            "current_user": request.state.current_user,
        },
    )


@router.get("/inventory/new")
def new_material_form(request: Request, _current_user=Depends(get_current_user)):
    return templates.TemplateResponse(
        "inventory_new.html",
        {
            "request": request,
            "page_title": "Nowy materiał",
            "categories": INVENTORY_CATEGORIES,
            "stock_units": STOCK_UNITS,
            "purchase_pricing_modes": PURCHASE_PRICING_MODES,
            "current_user": request.state.current_user,
        },
    )


@router.post("/inventory/new")
def create_material(
    code: str = Form(...),
    name: str = Form(...),
    category: str = Form(...),
    unit: str = Form(...),
    initial_price: str = Form(""),
    width_mm: str = Form(""),
    height_mm: str = Form(""),
    thickness_mm: str = Form(""),
    diameter_mm: str = Form(""),
    grade: str = Form(""),
    finish: str = Form(""),
    weight_per_meter_kg: str = Form(""),
    weight_per_piece_kg: str = Form(""),
    trade_length_m: str = Form(""),
    stock_unit: str = Form(""),
    purchase_pricing_mode: str = Form(""),
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    existing = db.scalar(select(Material).where(Material.code == code.strip()))
    if existing:
        raise HTTPException(status_code=400, detail="Materiał o podanym kodzie już istnieje.")

    stock_unit_value = stock_unit.strip() or unit.strip()
    material = Material(
        code=code.strip(),
        name=name.strip(),
        category=category.strip(),
        unit=unit.strip(),
        width_mm=_parse_optional_float(width_mm),
        height_mm=_parse_optional_float(height_mm),
        thickness_mm=_parse_optional_float(thickness_mm),
        diameter_mm=_parse_optional_float(diameter_mm),
        grade=grade.strip() or None,
        finish=finish.strip() or None,
        weight_per_meter_kg=_parse_optional_float(weight_per_meter_kg),
        weight_per_piece_kg=_parse_optional_float(weight_per_piece_kg),
        trade_length_m=_parse_optional_float(trade_length_m),
        stock_unit=stock_unit_value,
        purchase_pricing_mode=purchase_pricing_mode.strip() or None,
    )
    db.add(material)
    db.flush()

    stock_row = db.get(Stock, material.id)
    if not stock_row:
        db.add(Stock(material_id=material.id, qty_on_hand=0))

    if initial_price.strip():
        initial_price_value = float(initial_price)
        normalized = normalize_price(material, initial_price_value, unit.strip())
        db.add(
            MaterialPrice(
                material_id=material.id,
                price=initial_price_value,
                input_price=initial_price_value,
                input_unit=unit.strip(),
                normalized_price_per_kg=normalized["normalized_price_per_kg"],
                normalized_price_per_mb=normalized["normalized_price_per_mb"],
                normalized_price_per_piece=normalized["normalized_price_per_piece"],
                currency="PLN",
                note="Cena początkowa",
            )
        )

    db.commit()
    return RedirectResponse(url=f"/inventory/{material.id}", status_code=303)


@router.get("/inventory/{material_id}")
def material_detail(
    material_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    material = db.scalar(select(Material).where(Material.id == material_id))
    if not material:
        raise HTTPException(status_code=404)

    stock_row = db.get(Stock, material_id)
    if not stock_row:
        stock_row = Stock(material_id=material_id, qty_on_hand=0)
        db.add(stock_row)
        db.commit()
        db.refresh(stock_row)

    prices = db.scalars(
        select(MaterialPrice).where(MaterialPrice.material_id == material_id).order_by(MaterialPrice.valid_from.desc())
    ).all()
    moves = db.scalars(select(StockMove).where(StockMove.material_id == material_id).order_by(StockMove.created_at.desc())).all()
    reservations = db.scalars(
        select(Reservation)
        .where(Reservation.material_id == material_id)
        .order_by(Reservation.created_at.desc())
    ).all()
    physical_qty, reserved_qty, available_qty = material_stock_state(db, material_id)

    return templates.TemplateResponse(
        "inventory_detail.html",
        {
            "request": request,
            "page_title": f"Materiał {material.code}",
            "material": material,
            "stock_row": stock_row,
            "physical_qty": physical_qty,
            "reserved_qty": reserved_qty,
            "available_qty": available_qty,
            "prices": prices,
            "moves": moves,
            "reservations": reservations,
            "last_delivery_conversion": request.query_params.get("delivery_info"),
            "current_user": request.state.current_user,
        },
    )


@router.post("/inventory/{material_id}/delivery")
def add_delivery(
    material_id: int,
    qty_input: float = Form(...),
    qty_unit: str = Form(...),
    input_price: float = Form(...),
    input_price_unit: str = Form(...),
    note: str = Form(""),
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    material = db.get(Material, material_id)
    if not material:
        raise HTTPException(status_code=404)

    stock_row = db.get(Stock, material_id)
    if not stock_row:
        stock_row = Stock(material_id=material_id, qty_on_hand=0)
        db.add(stock_row)

    try:
        qty_data = normalize_quantity_for_stock(material, qty_input, qty_unit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    normalized = normalize_price(material, input_price, input_price_unit)

    qty_stock = float(qty_data["qty_stock"])
    qty_stock_unit = str(qty_data["qty_stock_unit"])
    stock_row.qty_on_hand += qty_stock

    move_note = note.strip() or "Dostawa"
    db.add(StockMove(material_id=material_id, move_type="in", qty=qty_stock, unit_price=input_price, note=move_note))
    db.add(
        MaterialPrice(
            material_id=material_id,
            price=input_price,
            input_price=input_price,
            input_unit=input_price_unit,
            normalized_price_per_kg=normalized["normalized_price_per_kg"],
            normalized_price_per_mb=normalized["normalized_price_per_mb"],
            normalized_price_per_piece=normalized["normalized_price_per_piece"],
            currency="PLN",
            note=move_note,
        )
    )
    db.commit()

    delivery_info = f"Dostawa przeliczona: {qty_input:.3f} {qty_unit} -> {qty_stock:.3f} {qty_stock_unit}"
    return RedirectResponse(url=f"/inventory/{material_id}?delivery_info={quote_plus(delivery_info)}", status_code=303)


@router.post("/inventory/{material_id}/adjust")
def adjust_stock(
    material_id: int,
    qty: float = Form(...),
    note: str = Form(""),
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    material = db.get(Material, material_id)
    if not material:
        raise HTTPException(status_code=404)

    stock_row = db.get(Stock, material_id)
    if not stock_row:
        stock_row = Stock(material_id=material_id, qty_on_hand=0)
        db.add(stock_row)

    stock_row.qty_on_hand = qty
    db.add(StockMove(material_id=material_id, move_type="adjust", qty=qty, note=note.strip() or "Korekta"))
    db.commit()
    return RedirectResponse(url=f"/inventory/{material_id}", status_code=303)
