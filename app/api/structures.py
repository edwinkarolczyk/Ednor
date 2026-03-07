import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.order_materials_engine import (
    auto_reserve_order_material,
    determine_material_status,
    estimate_material_weight,
    get_latest_material_unit_price,
    summarize_config_reservation_status,
    update_order_gate_status,
)
from app.core.structure_engine import build_horizontal_fence_svg, calculate_horizontal_fence
from app.db import Material, Order, OrderMaterial, OrderStructureConfig, StructureTemplate, get_db
from app.security import get_current_user

router = APIRouter(tags=["structures"])


def set_templates(templates_obj: Jinja2Templates):
    globals()["templates"] = templates_obj


def _find_component_qty(result: dict, component_code: str) -> float:
    for component in result.get("components", []):
        if component.get("component_code") == component_code:
            return float(component.get("qty") or 0)
    return 0.0


@router.get("/orders/{order_id}/structures/new")
def new_structure_config_form(
    order_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Nie znaleziono zlecenia.")

    structure_templates = db.scalars(
        select(StructureTemplate).where(StructureTemplate.is_active.is_(True)).order_by(StructureTemplate.name)
    ).all()
    raw_materials = db.scalars(
        select(Material).where(Material.category == "surowce", Material.is_active.is_(True)).order_by(Material.name)
    ).all()

    return templates.TemplateResponse(
        "structure_config_new.html",
        {
            "request": request,
            "page_title": "Nowa konfiguracja konstrukcji",
            "order": order,
            "structure_templates": structure_templates,
            "post_materials": raw_materials,
            "rail_materials": raw_materials,
            "fill_materials": raw_materials,
            "current_user": request.state.current_user,
        },
    )


@router.post("/orders/{order_id}/structures/new")
def create_structure_config(
    order_id: int,
    template_id: int = Form(...),
    name: str = Form(...),
    length_m: float = Form(...),
    height_m: float = Form(...),
    span_m: float = Form(2.5),
    rails_count: int = Form(2),
    gates_count: int = Form(0),
    wickets_count: int = Form(0),
    post_material_id: int = Form(...),
    rail_material_id: int = Form(...),
    fill_material_id: int = Form(...),
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Nie znaleziono zlecenia.")

    structure_template = db.get(StructureTemplate, template_id)
    if not structure_template:
        raise HTTPException(status_code=404, detail="Nie znaleziono szablonu konstrukcji.")

    params = {
        "length_m": length_m,
        "height_m": height_m,
        "span_m": span_m,
        "rails_count": rails_count,
        "gates_count": gates_count,
        "wickets_count": wickets_count,
        "fill_orientation": "horizontal",
    }
    result = calculate_horizontal_fence(params)
    svg_preview = build_horizontal_fence_svg(params, result)

    config = OrderStructureConfig(
        order_id=order_id,
        template_id=template_id,
        name=name.strip(),
        length_m=length_m,
        height_m=height_m,
        span_m=span_m,
        rails_count=rails_count,
        gates_count=gates_count,
        wickets_count=wickets_count,
        raw_result_json=json.dumps(result, ensure_ascii=False),
        svg_preview=svg_preview,
    )
    db.add(config)
    db.flush()

    generated_lines = [
        (post_material_id, _find_component_qty(result, "POST")),
        (rail_material_id, _find_component_qty(result, "RAIL")),
        (fill_material_id, _find_component_qty(result, "FILL")),
    ]

    created_materials: list[OrderMaterial] = []
    total_materials_cost = 0.0
    total_estimated_weight = 0.0

    for material_id, qty_required in generated_lines:
        if qty_required <= 0:
            continue

        material = db.get(Material, material_id)
        if not material:
            continue

        unit_price = get_latest_material_unit_price(db, material)
        total_cost = qty_required * unit_price if unit_price is not None else None

        order_material = OrderMaterial(
            order_id=order_id,
            material_id=material_id,
            qty_required=qty_required,
            qty_reserved=0,
            unit_price=unit_price,
            total_cost=total_cost,
            material_status="missing",
            source_config_id=config.id,
            note=f"Wygenerowano z konfiguracji: {config.name}",
        )
        db.add(order_material)
        db.flush()

        auto_reserve_order_material(db, order_material)
        order_material.total_cost = order_material.qty_required * order_material.unit_price if order_material.unit_price is not None else None

        if order_material.total_cost is not None:
            total_materials_cost += float(order_material.total_cost)

        estimated_weight = estimate_material_weight(material, order_material.qty_required)
        if estimated_weight is not None:
            total_estimated_weight += float(estimated_weight)

        created_materials.append(order_material)

    config.materials_cost = total_materials_cost if created_materials else None
    config.estimated_weight_kg = total_estimated_weight if created_materials else None
    config.reservation_status = summarize_config_reservation_status(created_materials)

    for order_material in order.order_materials:
        order_material.material_status = determine_material_status(order_material.qty_required, order_material.qty_reserved)
    update_order_gate_status(order, order.order_materials)

    db.commit()
    return RedirectResponse(url=f"/orders/{order_id}", status_code=303)
