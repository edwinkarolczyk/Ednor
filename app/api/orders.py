from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.config import UPLOADS_DIR
from app.db import Attachment, Order, OrderAssignment, Role, User, get_db
from app.security import get_current_user

router = APIRouter(tags=["orders"])


def set_templates(templates_obj: Jinja2Templates):
    globals()["templates"] = templates_obj


def _is_admin(user: User) -> bool:
    return "admin" in {role.code for role in user.roles}


def _next_order_no(db: Session) -> int:
    current_max = db.scalar(select(func.max(Order.order_no)))
    return (current_max or 0) + 1


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
    status: str = Form("new"),
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
    order = db.get(Order, order_id)
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
            "is_admin": _is_admin(current_user),
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
