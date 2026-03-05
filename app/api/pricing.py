from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.fence_engine import generate_basic_fence_components
from app.core.pricing_engine import calc_totals
from app.db import FenceQuoteInput, FenceTemplate, Order, OrderAssignment, PricingQuote, QuoteLine, User, get_db
from app.security import get_current_user
from app.utils.pdf import build_quote_pdf

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


def _build_form_from_quote(quote: PricingQuote | None):
    if not quote:
        return {
            "margin_percent": 0,
            "warranty_days": "",
            "labor_hours_planned": 0,
            "labor_hours_manual": "",
            "use_manual_labor": False,
            "labor_rate_per_h": 0,
            "power_kwh": 0,
            "power_rate_per_kwh": 0,
            "installation_cost": 0,
            "service_cost": 0,
            "notes": "",
            "length_m": 0,
            "height_m": 1.5,
            "span_m": 2.5,
            "gates_count": 0,
            "wickets_count": 0,
            "rounding_mode": "ceil_0_1",
            "fence_template_id": "",
            "price_post_each": 0,
            "price_rail_per_m": 0,
        }

    fence = quote.fence_input
    return {
        "margin_percent": quote.margin_percent,
        "warranty_days": quote.warranty_days or "",
        "labor_hours_planned": quote.labor_hours_planned,
        "labor_hours_manual": quote.labor_hours_manual or "",
        "use_manual_labor": quote.use_manual_labor,
        "labor_rate_per_h": quote.labor_rate_per_h,
        "power_kwh": quote.power_kwh,
        "power_rate_per_kwh": quote.power_rate_per_kwh,
        "installation_cost": quote.installation_cost,
        "service_cost": quote.service_cost,
        "notes": quote.notes or "",
        "length_m": fence.length_m if fence else 0,
        "height_m": fence.height_m if fence else 1.5,
        "span_m": fence.span_m if fence else 2.5,
        "gates_count": fence.gates_count if fence else 0,
        "wickets_count": fence.wickets_count if fence else 0,
        "rounding_mode": fence.rounding_mode if fence else "ceil_0_1",
        "fence_template_id": str(fence.template_id) if fence else "",
        "price_post_each": next((line.unit_price for line in quote.lines if line.name == "Słupki"), 0),
        "price_rail_per_m": next((line.unit_price for line in quote.lines if line.name == "Profil poziomy"), 0),
    }


@router.get("/orders/{order_id}/pricing")
def pricing_form(
    order_id: int,
    request: Request,
    view: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    order = _assert_order_access(db, order_id, current_user)
    fence_templates = db.scalars(select(FenceTemplate).where(FenceTemplate.is_active.is_(True)).order_by(FenceTemplate.name)).all()

    last_quote = None
    if view:
        last_quote = db.scalar(
            select(PricingQuote)
            .options(joinedload(PricingQuote.lines), joinedload(PricingQuote.fence_input))
            .where(PricingQuote.id == view, PricingQuote.order_id == order_id)
        )
    if not last_quote:
        last_quote = db.scalar(
            select(PricingQuote)
            .options(joinedload(PricingQuote.lines), joinedload(PricingQuote.fence_input))
            .where(PricingQuote.order_id == order_id)
            .order_by(PricingQuote.version_no.desc())
        )

    quote_lines = last_quote.lines if last_quote else []
    return templates.TemplateResponse(
        "pricing.html",
        {
            "request": request,
            "page_title": f"Wycena zlecenia #{order.order_no}",
            "order": order,
            "last_quote": last_quote,
            "quote_lines": quote_lines,
            "fence_templates": fence_templates,
            "form_data": _build_form_from_quote(last_quote),
            "current_user": request.state.current_user,
        },
    )


@router.post("/orders/{order_id}/pricing")
def pricing_submit(
    order_id: int,
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
    notes: str = Form(""),
    fence_template_id: str = Form(""),
    length_m: str = Form("0"),
    height_m: str = Form("0"),
    span_m: str = Form("2.5"),
    gates_count: str = Form("0"),
    wickets_count: str = Form("0"),
    rounding_mode: str = Form("ceil_0_1"),
    price_post_each: str = Form("0"),
    price_rail_per_m: str = Form("0"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    order = _assert_order_access(db, order_id, current_user)

    margin = _to_float(margin_percent)
    labor_planned = _to_float(labor_hours_planned)
    use_manual = bool(use_manual_labor)
    labor_manual = _to_float(labor_hours_manual) if labor_hours_manual not in (None, "") else None
    labor_rate = _to_float(labor_rate_per_h)
    power_used = _to_float(power_kwh)
    power_rate = _to_float(power_rate_per_kwh)
    install = _to_float(installation_cost)
    service = _to_float(service_cost)

    template = db.get(FenceTemplate, _to_int(fence_template_id)) if fence_template_id else None
    if not template:
        raise HTTPException(status_code=400, detail="Wybierz szablon ogrodzenia")

    components = generate_basic_fence_components(
        length_m=_to_float(length_m),
        height_m=_to_float(height_m),
        span_m=_to_float(span_m, default=2.5),
        gates_count=_to_int(gates_count),
        wickets_count=_to_int(wickets_count),
        rounding_mode=rounding_mode,
    )

    post_price = _to_float(price_post_each)
    rail_price = _to_float(price_rail_per_m)
    lines_payload: list[dict] = []
    for name, unit, qty in components:
        unit_price = post_price if name == "Słupki" else rail_price
        lines_payload.append(
            {
                "name": name,
                "unit": unit,
                "qty": qty,
                "unit_price": unit_price,
                "total_price": round(qty * unit_price, 2),
            }
        )

    subtotal, total, _, _ = calc_totals(
        lines=lines_payload,
        margin_percent=margin,
        labor_hours_planned=labor_planned,
        labor_hours_manual=labor_manual,
        use_manual_labor=use_manual,
        labor_rate_per_h=labor_rate,
        power_kwh=power_used,
        power_rate_per_kwh=power_rate,
        installation_cost=install,
        service_cost=service,
    )

    version_no = (db.scalar(select(func.max(PricingQuote.version_no)).where(PricingQuote.order_id == order_id)) or 0) + 1
    quote = PricingQuote(
        order_id=order_id,
        version_no=version_no,
        margin_percent=margin,
        warranty_days=_to_int(warranty_days) if warranty_days else None,
        labor_hours_planned=labor_planned,
        labor_hours_manual=labor_manual,
        use_manual_labor=use_manual,
        labor_rate_per_h=labor_rate,
        power_kwh=power_used,
        power_rate_per_kwh=power_rate,
        installation_cost=install,
        service_cost=service,
        subtotal_net=subtotal,
        total_net=total,
        notes=notes or None,
    )
    db.add(quote)
    db.flush()

    for line in lines_payload:
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

    db.add(
        FenceQuoteInput(
            quote_id=quote.id,
            template_id=template.id,
            length_m=_to_float(length_m),
            height_m=_to_float(height_m),
            span_m=_to_float(span_m, default=2.5),
            gates_count=_to_int(gates_count),
            wickets_count=_to_int(wickets_count),
            rounding_mode=rounding_mode,
        )
    )

    order.status = "priced"
    db.commit()
    return RedirectResponse(url=f"/orders/{order_id}/pricing", status_code=303)


@router.get("/orders/{order_id}/pricing/history")
def pricing_history(order_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    order = _assert_order_access(db, order_id, current_user)
    quotes = db.scalars(select(PricingQuote).where(PricingQuote.order_id == order_id).order_by(PricingQuote.version_no.desc())).all()
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
    quote = db.scalar(
        select(PricingQuote)
        .options(joinedload(PricingQuote.order), joinedload(PricingQuote.lines))
        .where(PricingQuote.id == quote_id)
    )
    if not quote:
        raise HTTPException(status_code=404)

    _assert_order_access(db, quote.order_id, current_user)
    pdf_bytes = build_quote_pdf(order=quote.order, quote=quote, lines=quote.lines)
    headers = {"Content-Disposition": f'attachment; filename="wycena_zlecenie_{quote.order.order_no}_v{quote.version_no}.pdf"'}
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)
