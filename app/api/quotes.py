from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.fence_engine import generate_basic_fence_components
from app.core.pricing_engine import calc_totals
from app.db import (
    FenceTemplate,
    Order,
    Payment,
    Quote,
    QuoteAcceptance,
    QuoteLine,
    QuoteVersion,
    User,
    get_db,
)
from app.security import get_current_user
from app.utils.pdf import build_quote_pdf

router = APIRouter(tags=["quotes"])


def set_templates(templates_obj: Jinja2Templates):
    globals()["templates"] = templates_obj


def _is_admin(user: User) -> bool:
    return "admin" in {role.code for role in user.roles}


def _require_admin(user: User):
    if not _is_admin(user):
        raise HTTPException(status_code=403)


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


def _build_form_from_quote_version(quote_version: QuoteVersion | None):
    if not quote_version:
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

    return {
        "margin_percent": quote_version.margin_percent,
        "warranty_days": quote_version.warranty_days or "",
        "labor_hours_planned": quote_version.labor_hours_planned,
        "labor_hours_manual": quote_version.labor_hours_manual or "",
        "use_manual_labor": quote_version.use_manual_labor,
        "labor_rate_per_h": quote_version.labor_rate_per_h,
        "power_kwh": quote_version.power_kwh,
        "power_rate_per_kwh": quote_version.power_rate_per_kwh,
        "installation_cost": quote_version.installation_cost,
        "service_cost": quote_version.service_cost,
        "notes": quote_version.notes or "",
        "length_m": 0,
        "height_m": 1.5,
        "span_m": 2.5,
        "gates_count": 0,
        "wickets_count": 0,
        "rounding_mode": "ceil_0_1",
        "fence_template_id": "",
        "price_post_each": next((line.unit_price for line in quote_version.lines if line.name == "Słupki"), 0),
        "price_rail_per_m": next((line.unit_price for line in quote_version.lines if line.name == "Profil poziomy"), 0),
    }


def _next_quote_no(db: Session) -> str:
    year = datetime.utcnow().year
    prefix = f"{year}/Q/"
    existing = db.scalars(select(Quote.quote_no).where(Quote.quote_no.like(f"{prefix}%"))).all()
    next_idx = 1
    for value in existing:
        try:
            next_idx = max(next_idx, int(value.split("/")[-1]) + 1)
        except Exception:
            continue
    return f"{prefix}{next_idx:03d}"


def _next_order_no(db: Session) -> int:
    current_max = db.scalar(select(func.max(Order.order_no)))
    return (current_max or 0) + 1


@router.get("/quotes")
def quotes_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_admin(current_user)

    quotes = db.scalars(select(Quote).order_by(Quote.id.desc())).all()

    return templates.TemplateResponse(
        "quotes.html",
        {"request": request, "page_title": "Wyceny", "quotes": quotes, "current_user": request.state.current_user},
    )


@router.get("/quotes/new")
def new_quote_form(request: Request, current_user: User = Depends(get_current_user)):
    _require_admin(current_user)
    return templates.TemplateResponse(
        "quote_new.html",
        {
            "request": request,
            "page_title": "Nowa wycena",
            "current_user": request.state.current_user,
        },
    )


@router.post("/quotes/new")
def create_quote(
    customer_name: str = Form(...),
    site_address: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)

    quote = Quote(
        quote_no=_next_quote_no(db),
        customer_name=customer_name,
        site_address_text=site_address or None,
        status="draft",
        created_by_user_id=current_user.id,
    )
    db.add(quote)
    db.flush()

    db.commit()
    return RedirectResponse(url=f"/quotes/{quote.id}", status_code=303)


@router.get("/quotes/{quote_id}")
def quote_detail(quote_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_admin(current_user)
    quote = db.get(Quote, quote_id)
    if not quote:
        raise HTTPException(status_code=404)

    return templates.TemplateResponse(
        "quote_detail.html",
        {
            "request": request,
            "page_title": "Wycena",
            "quote": quote,
            "current_user": request.state.current_user,
        },
    )


@router.get("/quotes/{quote_id}/pricing")
def quote_pricing_form(quote_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_admin(current_user)
    quote = db.get(Quote, quote_id)
    if not quote:
        raise HTTPException(status_code=404)

    fence_templates = db.scalars(select(FenceTemplate).where(FenceTemplate.is_active.is_(True)).order_by(FenceTemplate.name)).all()
    last_quote = db.scalar(
        select(QuoteVersion)
        .options(joinedload(QuoteVersion.lines))
        .where(QuoteVersion.quote_id == quote_id)
        .order_by(QuoteVersion.version_no.desc())
    )

    quote_lines = last_quote.lines if last_quote else []
    return templates.TemplateResponse(
        "quote_pricing.html",
        {
            "request": request,
            "page_title": f"Wycena {quote.quote_no}",
            "quote": quote,
            "last_quote": last_quote,
            "quote_lines": quote_lines,
            "fence_templates": fence_templates,
            "form_data": _build_form_from_quote_version(last_quote),
            "current_user": request.state.current_user,
        },
    )


@router.post("/quotes/{quote_id}/pricing")
def quote_pricing_submit(
    quote_id: int,
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
    description: str = Form(""),
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
    _require_admin(current_user)
    quote = db.get(Quote, quote_id)
    if not quote:
        raise HTTPException(status_code=404)

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
        line_type = "material" if name in {"Słupki", "Profil poziomy"} else "custom"
        lines_payload.append(
            {
                "line_type": line_type,
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

    version_no = (db.scalar(select(func.max(QuoteVersion.version_no)).where(QuoteVersion.quote_id == quote_id)) or 0) + 1
    quote_version = QuoteVersion(
        quote_id=quote_id,
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
        description=description or None,
    )
    db.add(quote_version)
    db.flush()

    for line in lines_payload:
        db.add(
            QuoteLine(
                quote_version_id=quote_version.id,
                line_type=line["line_type"],
                name=line["name"],
                unit=line["unit"],
                qty=line["qty"],
                unit_price=line["unit_price"],
                total_price=line["total_price"],
            )
        )

    db.commit()
    return RedirectResponse(url=f"/quotes/{quote_id}/pricing", status_code=303)


@router.get("/quotes/{quote_id}/history")
def quote_history(quote_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_admin(current_user)
    quote = db.get(Quote, quote_id)
    if not quote:
        raise HTTPException(status_code=404)

    versions = db.scalars(select(QuoteVersion).where(QuoteVersion.quote_id == quote_id).order_by(QuoteVersion.version_no.desc())).all()
    return templates.TemplateResponse(
        "quote_history.html",
        {
            "request": request,
            "page_title": f"Historia wyceny {quote.quote_no}",
            "quote": quote,
            "versions": versions,
            "current_user": request.state.current_user,
        },
    )


@router.post("/quotes/{quote_id}/accept/{version_id}")
def quote_accept_version(
    quote_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    quote = db.get(Quote, quote_id)
    if not quote:
        raise HTTPException(status_code=404)

    version = db.scalar(select(QuoteVersion).where(QuoteVersion.id == version_id, QuoteVersion.quote_id == quote_id))
    if not version:
        raise HTTPException(status_code=404, detail="Wersja wyceny nie istnieje")

    quote.status = "accepted"

    existing = db.scalar(select(QuoteAcceptance).where(QuoteAcceptance.quote_id == quote_id))
    if existing:
        existing.accepted_version_id = version_id
        existing.accepted_at = datetime.utcnow()
    else:
        db.add(QuoteAcceptance(quote_id=quote_id, accepted_version_id=version_id))

    db.commit()

    return RedirectResponse(f"/quotes/{quote_id}", status_code=303)


@router.post("/quotes/{quote_id}/send")
def quote_send(quote_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_admin(current_user)
    quote = db.get(Quote, quote_id)
    if not quote:
        raise HTTPException(status_code=404)
    quote.status = "sent"
    db.commit()
    return RedirectResponse(url=f"/quotes/{quote_id}", status_code=303)


@router.post("/quotes/{quote_id}/reject")
def quote_reject(quote_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_admin(current_user)
    quote = db.get(Quote, quote_id)
    if not quote:
        raise HTTPException(status_code=404)
    quote.status = "rejected"
    db.commit()
    return RedirectResponse(url=f"/quotes/{quote_id}", status_code=303)


@router.post("/quotes/{quote_id}/create-order")
def quote_create_order(
    quote_id: int,
    deposit_amount: str = Form("0"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    quote = db.get(Quote, quote_id)
    if not quote:
        raise HTTPException(status_code=404)
    if quote.status != "accepted":
        raise HTTPException(status_code=400, detail="Wycena nie jest zaakceptowana")

    acceptance = db.scalar(select(QuoteAcceptance).where(QuoteAcceptance.quote_id == quote_id))
    if not acceptance:
        raise HTTPException(status_code=400, detail="Brak rekordu akceptacji")
    accepted_version_id = acceptance.accepted_version_id

    order = Order(
        order_no=_next_order_no(db),
        title=f"Zlecenie z wyceny {quote.quote_no}",
        client_name=quote.customer_name,
        address=quote.site_address_text,
        status="awaiting_deposit",
        source_quote_id=quote.id,
        accepted_quote_version_id=accepted_version_id,
        deposit_required=True,
        materials_check_required=True,
    )
    db.add(order)
    db.flush()

    db.add(
        Payment(
            order_id=order.id,
            payment_type="deposit",
            amount=_to_float(deposit_amount),
            status="planned",
        )
    )

    db.commit()
    return RedirectResponse(url=f"/orders/{order.id}", status_code=303)


@router.get("/quote-versions/{quote_version_id}/pdf")
def quote_version_pdf(quote_version_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_admin(current_user)
    version = db.scalar(
        select(QuoteVersion)
        .options(joinedload(QuoteVersion.quote), joinedload(QuoteVersion.lines))
        .where(QuoteVersion.id == quote_version_id)
    )
    if not version:
        raise HTTPException(status_code=404)

    pdf_bytes = build_quote_pdf(order=version.quote, quote=version, lines=version.lines)
    headers = {
        "Content-Disposition": f'attachment; filename="wycena_{version.quote.quote_no.replace("/", "-")}_v{version.version_no}.pdf"'
    }
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)
