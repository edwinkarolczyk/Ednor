from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.fence_engine import generate_basic_fence_lines
from app.core.pricing_engine import calc_totals
from app.db import FenceQuoteInput, FenceTemplate, Order, OrderAssignment, PricingQuote, QuoteLine, User, get_db
from app.security import get_current_user
from app.utils.pdf import generate_quote_pdf

router = APIRouter(tags=["pricing"])


def set_templates(templates_obj: Jinja2Templates):
    globals()["templates"] = templates_obj


def _is_admin(user: User) -> bool:
    return "admin" in {role.code for role in user.roles}


def _assert_order_access(db: Session, order_id: int, user: User) -> Order:
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404)
    if _is_admin(user):
        return order
    assigned = db.scalar(select(OrderAssignment.id).where(OrderAssignment.order_id == order_id, OrderAssignment.user_id == user.id))
    if not assigned:
        raise HTTPException(status_code=403)
    return order


def _to_float(value: str | None, default: float = 0.0) -> float:
    try:
        return float(value) if value not in (None, "") else default
    except ValueError:
        return default


def _to_int(value: str | None, default: int = 0) -> int:
    try:
        return int(value) if value not in (None, "") else default
    except ValueError:
        return default


@router.get("/orders/{order_id}/pricing")
def pricing_form(order_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    order = _assert_order_access(db, order_id, current_user)
    templates_data = db.scalars(select(FenceTemplate).where(FenceTemplate.is_active.is_(True)).order_by(FenceTemplate.name)).all()
    return templates.TemplateResponse(
        "pricing.html",
        {
            "request": request,
            "page_title": f"Wycena zlecenia #{order.order_no}",
            "order": order,
            "templates_data": templates_data,
            "form_data": {},
            "preview_lines": [],
            "subtotal": None,
            "total": None,
            "current_user": request.state.current_user,
        },
    )


@router.post("/orders/{order_id}/pricing")
def pricing_submit(
    order_id: int,
    request: Request,
    margin_percent: str = Form("0"),
    warranty_days: str = Form(""),
    labor_hours_planned: str = Form("0"),
    labor_hours_manual: str = Form(""),
    use_manual_labor: str | None = Form(None),
    labor_rate_per_h: str = Form("0"),
    power_kwh: str = Form("0"),
    power_rate_per_kwh: str = Form("0"),
    installation_cost: str = Form("0"),
    service_cost: str = Form("0"),
    template_id: str = Form(""),
    length_m: str = Form("0"),
    height_m: str = Form("0"),
    span_m: str = Form("2.5"),
    gates_count: str = Form("0"),
    wickets_count: str = Form("0"),
    price_post_each: str = Form("0"),
    price_rail_per_m: str = Form("0"),
    notes: str = Form(""),
    action: str = Form("preview"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    order = _assert_order_access(db, order_id, current_user)
    templates_data = db.scalars(select(FenceTemplate).where(FenceTemplate.is_active.is_(True)).order_by(FenceTemplate.name)).all()

    margin = _to_float(margin_percent)
    labor_planned = _to_float(labor_hours_planned)
    labor_manual = _to_float(labor_hours_manual, default=0.0) if use_manual_labor else None
    labor_rate = _to_float(labor_rate_per_h)
    power_used = _to_float(power_kwh)
    power_rate = _to_float(power_rate_per_kwh)
    install = _to_float(installation_cost)
    service = _to_float(service_cost)

    length = _to_float(length_m)
    height = _to_float(height_m)
    span = _to_float(span_m, default=2.5)
    gates = _to_int(gates_count)
    wickets = _to_int(wickets_count)

    post_price = _to_float(price_post_each)
    rail_price = _to_float(price_rail_per_m)

    generated = generate_basic_fence_lines(length_m=length, span_m=span, gates_count=gates, wickets_count=wickets)
    line_priced = []
    for line in generated:
        unit_price = post_price if line["name"] == "Słupki" else rail_price
        total_price = round(line["qty"] * unit_price, 2)
        line_priced.append({**line, "unit_price": unit_price, "total_price": total_price})

    labor_used = labor_manual if labor_manual is not None else labor_planned
    subtotal, total = calc_totals(
        lines=[line["total_price"] for line in line_priced],
        margin_percent=margin,
        labor_hours_used=labor_used,
        labor_rate_per_h=labor_rate,
        power_kwh=power_used,
        power_rate_per_kwh=power_rate,
        installation_cost=install,
        service_cost=service,
    )

    form_data = {
        "margin_percent": margin_percent,
        "warranty_days": warranty_days,
        "labor_hours_planned": labor_hours_planned,
        "labor_hours_manual": labor_hours_manual,
        "use_manual_labor": bool(use_manual_labor),
        "labor_rate_per_h": labor_rate_per_h,
        "power_kwh": power_kwh,
        "power_rate_per_kwh": power_rate_per_kwh,
        "installation_cost": installation_cost,
        "service_cost": service_cost,
        "template_id": template_id,
        "length_m": length_m,
        "height_m": height_m,
        "span_m": span_m,
        "gates_count": gates_count,
        "wickets_count": wickets_count,
        "price_post_each": price_post_each,
        "price_rail_per_m": price_rail_per_m,
        "notes": notes,
    }

    if action == "save":
        version = (db.scalar(select(func.max(PricingQuote.version_no)).where(PricingQuote.order_id == order_id)) or 0) + 1
        quote = PricingQuote(
            order_id=order_id,
            version_no=version,
            margin_percent=margin,
            labor_hours_planned=labor_planned,
            labor_hours_manual=labor_manual,
            labor_rate_per_h=labor_rate,
            power_kwh=power_used,
            power_rate_per_kwh=power_rate,
            installation_cost=install,
            service_cost=service,
            subtotal_net=subtotal,
            total_net=total,
            warranty_days=_to_int(warranty_days) if warranty_days else None,
            notes=notes or None,
        )
        db.add(quote)
        db.flush()

        selected_template = db.get(FenceTemplate, _to_int(template_id)) if template_id else None
        if selected_template:
            db.add(
                FenceQuoteInput(
                    quote_id=quote.id,
                    template_id=selected_template.id,
                    length_m=length,
                    height_m=height,
                    span_m=span,
                    gates_count=gates,
                    wickets_count=wickets,
                    rounding_mode="ceil_0_1",
                )
            )

        for line in line_priced:
            db.add(
                QuoteLine(
                    quote_id=quote.id,
                    name=line["name"],
                    unit=line["unit"],
                    qty=line["qty"],
                    unit_price=line["unit_price"],
                    total_price=line["total_price"],
                )
            )

        order.status = "priced"
        db.commit()
        return RedirectResponse(url=f"/orders/{order_id}/pricing/history", status_code=303)

    return templates.TemplateResponse(
        "pricing.html",
        {
            "request": request,
            "page_title": f"Wycena zlecenia #{order.order_no}",
            "order": order,
            "templates_data": templates_data,
            "form_data": form_data,
            "preview_lines": line_priced,
            "subtotal": subtotal,
            "total": total,
            "current_user": request.state.current_user,
        },
    )


@router.get("/orders/{order_id}/pricing/history")
def pricing_history(order_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    order = _assert_order_access(db, order_id, current_user)
    quotes = db.scalars(
        select(PricingQuote).where(PricingQuote.order_id == order_id).order_by(PricingQuote.version_no.desc())
    ).all()
    return templates.TemplateResponse(
        "pricing_history.html",
        {
            "request": request,
            "page_title": f"Historia wycen #{order.order_no}",
            "order": order,
            "quotes": quotes,
            "current_user": request.state.current_user,
        },
    )


@router.get("/pricing/{quote_id}/pdf")
def pricing_pdf(quote_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    quote = db.get(PricingQuote, quote_id)
    if not quote:
        raise HTTPException(status_code=404)

    _assert_order_access(db, quote.order_id, current_user)
    order = db.get(Order, quote.order_id)
    lines = db.scalars(select(QuoteLine).where(QuoteLine.quote_id == quote_id).order_by(QuoteLine.id)).all()
    pdf_bytes = generate_quote_pdf(quote=quote, order=order, lines=lines)

    headers = {"Content-Disposition": f'attachment; filename="wycena_zlecenie_{order.order_no}_v{quote.version_no}.pdf"'}
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)
