from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db import INVENTORY_CATEGORIES, Material, MaterialPrice, Stock, StockMove, get_db
from app.security import get_current_user

router = APIRouter(tags=["inventory"])


def set_templates(templates_obj: Jinja2Templates):
    globals()["templates"] = templates_obj


@router.get("/inventory")
def inventory_page(
    request: Request,
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    materials = db.scalars(select(Material).options(joinedload(Material.stock_row)).order_by(Material.code)).unique().all()
    # latest price per material (first row per material after DESC sort)
    deduped_latest_prices: dict[int, MaterialPrice] = {}
    for price in db.scalars(select(MaterialPrice).order_by(MaterialPrice.material_id, MaterialPrice.valid_from.desc())).all():
        deduped_latest_prices.setdefault(price.material_id, price)

    return templates.TemplateResponse(
        "inventory.html",
        {
            "request": request,
            "page_title": "Magazyn",
            "materials": materials,
            "latest_prices": deduped_latest_prices,
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
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    existing = db.scalar(select(Material).where(Material.code == code.strip()))
    if existing:
        raise HTTPException(status_code=400, detail="Materiał o podanym kodzie już istnieje.")

    material = Material(code=code.strip(), name=name.strip(), category=category.strip(), unit=unit.strip())
    db.add(material)
    db.flush()

    stock_row = db.get(Stock, material.id)
    if not stock_row:
        db.add(Stock(material_id=material.id, qty_on_hand=0))

    if initial_price.strip():
        db.add(MaterialPrice(material_id=material.id, price=float(initial_price), currency="PLN", note="Cena początkowa"))

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

    return templates.TemplateResponse(
        "inventory_detail.html",
        {
            "request": request,
            "page_title": f"Materiał {material.code}",
            "material": material,
            "stock_row": stock_row,
            "prices": prices,
            "moves": moves,
            "current_user": request.state.current_user,
        },
    )


@router.post("/inventory/{material_id}/delivery")
def add_delivery(
    material_id: int,
    qty: float = Form(...),
    unit_price: float = Form(...),
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

    stock_row.qty_on_hand += qty
    move_note = note.strip() or "Dostawa"
    db.add(StockMove(material_id=material_id, move_type="in", qty=qty, unit_price=unit_price, note=move_note))
    db.add(MaterialPrice(material_id=material_id, price=unit_price, currency="PLN", note=move_note))
    db.commit()
    return RedirectResponse(url=f"/inventory/{material_id}", status_code=303)


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
