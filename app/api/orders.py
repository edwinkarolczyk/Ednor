from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.config import UPLOADS_DIR
from app.core.order_materials_engine import determine_material_status
from app.db import (
    Attachment,
    Material,
    Order,
    OrderAssignment,
    OrderMaterial,
    OrderStructureConfig,
    Payment,
    PricingQuote,
    Reservation,
    Role,
    TimeEntry,
    User,
    get_db,
    material_stock_state,
)
from app.security import get_current_user

router = APIRouter(tags=["orders"])


def set_templates(templates_obj: Jinja2Templates):
    globals()["templates"] = templates_obj


def _is_admin(user: User) -> bool:
    return "admin" in {role.code for role in user.roles}


def _is_installer_or_admin(user: User) -> bool:
    role_codes = {role.code for role in user.roles}
    return "admin" in role_codes or "installer" in role_codes


def _next_order_no(db: Session) -> int:
    current_max = db.scalar(select(func.max(Order.order_no)))
    return (current_max or 0) + 1


def _build_order_material_view(order_material: OrderMaterial) -> dict:
    missing_qty = max(float(order_material.qty_required - order_material.qty_reserved), 0.0)
    status = order_material.material_status or determine_material_status(order_material.qty_required, order_material.qty_reserved)
    return {
        "entity": order_material,
        "missing_qty": missing_qty,
        "material_status": status,
        "unit_price": order_material.unit_price,
        "total_cost": order_material.total_cost,
    }


def _build_config_view(config: OrderStructureConfig) -> dict:
    return {
        "entity": config,
        "materials_cost": config.materials_cost,
        "estimated_weight_kg": config.estimated_weight_kg,
        "reservation_status": config.reservation_status or "missing",
    }


@router.get("/my-orders")
def my_orders(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assignments = db.scalars(
        select(OrderAssignment)
        .options(joinedload(OrderAssignment.order))
        .where(OrderAssignment.user_id == current_user.id)
        .order_by(OrderAssignment.created_at.desc())
    ).all()
    return templates.TemplateResponse(
        "my_orders.html",
        {
            "request": request,
            "page_title": "Moje zlecenia",
            "assignments": assignments,
            "current_user": request.state.current_user,
        },
    )


@router.get("/orders")
def orders_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403)
    orders = db.scalars(select(Order).order_by(Order.created_at.desc())).all()
    return templates.TemplateResponse(
        "orders.html",
        {"request": request, "page_title": "Zlecenia", "orders": orders, "current_user": request.state.current_user},
    )


@router.get("/orders/new")
def new_order_form(request: Request, current_user: User = Depends(get_current_user)):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403)
    return templates.TemplateResponse(
        "order_new.html", {"request": request, "page_title": "Nowe zlecenie", "current_user": request.state.current_user}
    )


@router.post("/orders/new")
def create_order(
    title: str = Form(...),
    client_name: str = Form(""),
    address: str = Form(""),
    status: str = Form("draft"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403)

    order = Order(
        order_no=_next_order_no(db),
        title=title,
        client_name=client_name or None,
        address=address or None,
        status=status,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return RedirectResponse(url=f"/orders/{order.id}", status_code=303)


@router.get("/orders/{order_id}")
def order_detail(
    order_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    order = db.scalar(
        select(Order)
        .options(
            joinedload(Order.order_materials).joinedload(OrderMaterial.material),
            joinedload(Order.payments),
        )
        .where(Order.id == order_id)
    )
    if not order:
        raise HTTPException(status_code=404)

    if not _is_admin(current_user):
        assigned = db.scalar(
            select(OrderAssignment).where(OrderAssignment.order_id == order_id, OrderAssignment.user_id == current_user.id)
        )
        if not assigned:
            raise HTTPException(status_code=403)

    assignments = db.scalars(
        select(OrderAssignment)
        .options(joinedload(OrderAssignment.user))
        .where(OrderAssignment.order_id == order_id)
        .order_by(OrderAssignment.created_at.desc())
    ).all()
    users = db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.username)).all()
    roles = db.scalars(select(Role).order_by(Role.name)).all()
    attachments = db.scalars(select(Attachment).where(Attachment.order_id == order_id)).all()
    latest_quote = db.scalar(
        select(PricingQuote).where(PricingQuote.order_id == order_id).order_by(PricingQuote.version_no.desc()).limit(1)
    )
    payments = db.scalars(select(Payment).where(Payment.order_id == order_id).order_by(Payment.created_at.desc())).all()
    materials = db.scalars(select(Material).where(Material.is_active.is_(True)).order_by(Material.code)).all()
    material_states = {
        material.id: material_stock_state(db, material.id)
        for material in materials
    }
    latest_time_entries = db.scalars(
        select(TimeEntry)
        .options(joinedload(TimeEntry.user))
        .where(TimeEntry.order_id == order_id, TimeEntry.work_type == "installation")
        .order_by(TimeEntry.started_at.desc())
        .limit(10)
    ).all()
    order_structure_configs = db.scalars(
        select(OrderStructureConfig)
        .options(joinedload(OrderStructureConfig.template))
        .where(OrderStructureConfig.order_id == order_id)
        .order_by(OrderStructureConfig.created_at.desc())
    ).all()
    order_materials_view = [_build_order_material_view(line) for line in order.order_materials]
    order_structure_configs_view = [_build_config_view(config) for config in order_structure_configs]

    return templates.TemplateResponse(
        "order_detail.html",
        {
            "request": request,
            "page_title": f"Zlecenie #{order.order_no}",
            "order": order,
            "assignments": assignments,
            "users": users,
            "roles": roles,
            "attachments": attachments,
            "latest_quote": latest_quote,
            "is_admin": _is_admin(current_user),
            "can_track_installation_time": _is_installer_or_admin(current_user),
            "latest_time_entries": latest_time_entries,
            "payments": payments,
            "materials": materials,
            "order_materials": order_materials_view,
            "order_structure_configs": order_structure_configs_view,
            "material_states": material_states,
            "current_user": request.state.current_user,
        },
    )


@router.post("/orders/{order_id}/assign")
def assign_user(
    order_id: int,
    user_id: int = Form(...),
    role_code: str = Form(...),
    note: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403)
    assignment = OrderAssignment(order_id=order_id, user_id=user_id, role_code=role_code, note=note or None)
    db.add(assignment)
    db.commit()
    return RedirectResponse(url=f"/orders/{order_id}", status_code=303)


@router.post("/orders/{order_id}/materials/add")
def add_material_to_order(
    order_id: int,
    material_id: int = Form(...),
    qty_required: float = Form(...),
    note: str = Form(""),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404)

    material = db.get(Material, material_id)
    if not material:
        raise HTTPException(status_code=404)

    order_material = db.scalar(
        select(OrderMaterial).where(
            OrderMaterial.order_id == order_id,
            OrderMaterial.material_id == material_id,
        )
    )
    if order_material:
        order_material.qty_required += qty_required
        order_material.material_status = determine_material_status(order_material.qty_required, order_material.qty_reserved)
        if note.strip():
            order_material.note = note.strip()
    else:
        db.add(
            OrderMaterial(
                order_id=order_id,
                material_id=material_id,
                qty_required=qty_required,
                qty_reserved=0,
                material_status="missing",
                note=note.strip() or None,
            )
        )

    db.commit()
    return RedirectResponse(url=f"/orders/{order_id}", status_code=303)


@router.post("/orders/{order_id}/materials/{order_material_id}/reserve")
def reserve_order_material(
    order_id: int,
    order_material_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    order_material = db.get(OrderMaterial, order_material_id)
    if not order_material or order_material.order_id != order_id:
        raise HTTPException(status_code=404)

    missing_to_reserve = max(order_material.qty_required - order_material.qty_reserved, 0)
    if missing_to_reserve <= 0:
        return RedirectResponse(url=f"/orders/{order_id}", status_code=303)

    _, _, available_qty = material_stock_state(db, order_material.material_id)
    reserve_qty = min(missing_to_reserve, max(available_qty, 0))

    if reserve_qty > 0:
        db.add(
            Reservation(
                order_id=order_id,
                material_id=order_material.material_id,
                qty_reserved=reserve_qty,
                status="reserved",
                note=f"Rezerwacja dla pozycji materiałowej #{order_material.id}",
            )
        )
        order_material.qty_reserved += reserve_qty

    order_material.material_status = determine_material_status(order_material.qty_required, order_material.qty_reserved)

    db.commit()
    return RedirectResponse(url=f"/orders/{order_id}", status_code=303)


@router.post("/orders/{order_id}/materials/{order_material_id}/release")
def release_order_material(
    order_id: int,
    order_material_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    order_material = db.get(OrderMaterial, order_material_id)
    if not order_material or order_material.order_id != order_id:
        raise HTTPException(status_code=404)

    reservations = db.scalars(
        select(Reservation).where(
            Reservation.order_id == order_id,
            Reservation.material_id == order_material.material_id,
            Reservation.status == "reserved",
        )
    ).all()
    for reservation in reservations:
        reservation.status = "released"

    order_material.qty_reserved = 0
    order_material.material_status = determine_material_status(order_material.qty_required, order_material.qty_reserved)
    db.commit()
    return RedirectResponse(url=f"/orders/{order_id}", status_code=303)




@router.post("/orders/{order_id}/payments/{payment_id}/mark-paid")
def mark_payment_paid(
    order_id: int,
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403)

    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404)

    payment = db.get(Payment, payment_id)
    if not payment or payment.order_id != order_id:
        raise HTTPException(status_code=404)

    payment.status = "paid"
    payment.paid_at = datetime.utcnow()

    if payment.payment_type == "deposit":
        order.status = "awaiting_materials"

    db.commit()
    return RedirectResponse(url=f"/orders/{order_id}", status_code=303)


@router.post("/api/orders/{order_id}/upload")
async def upload_order_file(
    order_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404)

    target_dir = UPLOADS_DIR / str(order_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    safe_name = Path(file.filename or "uploaded_file").name
    target_file = target_dir / safe_name

    with target_file.open("wb") as buffer:
        while chunk := await file.read(1024 * 1024):
            buffer.write(chunk)

    await file.close()
    db.add(Attachment(order_id=order_id, filename=safe_name, filepath=str(target_file)))
    db.commit()
    return RedirectResponse(url=f"/orders/{order_id}", status_code=303)
