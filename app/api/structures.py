import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

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

    generated_lines = [
        (post_material_id, _find_component_qty(result, "POST"), "Wygenerowano z konfiguracji konstrukcji (słupki)."),
        (rail_material_id, _find_component_qty(result, "RAIL"), "Wygenerowano z konfiguracji konstrukcji (profile poziome)."),
        (fill_material_id, _find_component_qty(result, "FILL"), "Wygenerowano z konfiguracji konstrukcji (wypełnienie)."),
    ]
    for material_id, qty_required, note in generated_lines:
        if qty_required <= 0:
            continue
        db.add(
            OrderMaterial(
                order_id=order_id,
                material_id=material_id,
                qty_required=qty_required,
                qty_reserved=0,
                note=note,
            )
        )

    db.commit()
    return RedirectResponse(url=f"/orders/{order_id}", status_code=303)
