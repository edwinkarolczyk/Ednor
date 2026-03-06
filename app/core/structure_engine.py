import math


def _safe_float(value: float | int | str | None, default: float) -> float:
    if value in (None, ""):
        return default
    return float(value)


def _safe_int(value: int | float | str | None, default: int) -> int:
    if value in (None, ""):
        return default
    return int(float(value))


def calculate_horizontal_fence(params: dict) -> dict:
    length_m = max(_safe_float(params.get("length_m"), 0.0), 0.0)
    height_m = max(_safe_float(params.get("height_m"), 0.0), 0.0)
    span_m = max(_safe_float(params.get("span_m"), 2.5), 0.1)
    rails_count = max(_safe_int(params.get("rails_count"), 2), 1)
    gates_count = max(_safe_int(params.get("gates_count"), 0), 0)
    wickets_count = max(_safe_int(params.get("wickets_count"), 0), 0)

    spans = int(math.ceil(length_m / span_m)) if length_m > 0 else 0
    posts = int(spans + 1 + gates_count * 2 + wickets_count * 2)
    rails_total_m = round(length_m * rails_count, 3)

    fill_step_m = 0.1
    fill_count = int(math.floor(height_m / fill_step_m)) if height_m > 0 else 0
    fill_total_m = round(fill_count * length_m, 3)

    return {
        "spans": spans,
        "posts": posts,
        "rails_total_m": rails_total_m,
        "fill_count": fill_count,
        "fill_total_m": fill_total_m,
        "components": [
            {"component_code": "POST", "qty": posts, "unit": "szt"},
            {"component_code": "RAIL", "qty": rails_total_m, "unit": "mb"},
            {"component_code": "FILL", "qty": fill_total_m, "unit": "mb"},
        ],
    }


def build_horizontal_fence_svg(params: dict, result: dict) -> str:
    length_m = max(_safe_float(params.get("length_m"), 1.0), 1.0)
    height_m = max(_safe_float(params.get("height_m"), 1.2), 0.2)
    posts = max(_safe_int(result.get("posts"), 2), 2)
    rails_count = max(_safe_int(params.get("rails_count"), 2), 1)

    svg_w = 900
    svg_h = 250
    margin_x = 40
    baseline_y = 190
    draw_w = svg_w - 2 * margin_x
    fence_h_px = min(120, max(30, height_m * 80))
    top_y = baseline_y - fence_h_px

    post_xs = []
    for idx in range(posts):
        ratio = idx / (posts - 1) if posts > 1 else 0
        post_xs.append(margin_x + ratio * draw_w)

    rail_lines = []
    for i in range(rails_count):
        y = top_y + ((i + 1) * fence_h_px / (rails_count + 1))
        rail_lines.append(f'<line x1="{margin_x}" y1="{y:.1f}" x2="{margin_x + draw_w}" y2="{y:.1f}" stroke="#a4282b" stroke-width="3"/>')

    posts_svg = []
    for x in post_xs:
        posts_svg.append(
            f'<rect x="{x - 4:.1f}" y="{top_y:.1f}" width="8" height="{fence_h_px + 14:.1f}" fill="#6e1518" rx="1" />'
        )

    fill_rect = (
        f'<rect x="{margin_x}" y="{top_y:.1f}" width="{draw_w}" height="{fence_h_px:.1f}" '
        'fill="rgba(164,40,43,0.12)" stroke="rgba(164,40,43,0.4)" stroke-dasharray="3 3" />'
    )

    description = (
        f'Długość: {length_m:.2f} m | Wysokość: {height_m:.2f} m | '
        f'Słupki: {result.get("posts", 0)} | Przęsła: {result.get("spans", 0)}'
    )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_w} {svg_h}" role="img" '
        f'aria-label="Wizualizacja konstrukcji" style="max-width:100%;height:auto;">'
        f'<line x1="{margin_x}" y1="{baseline_y + 12}" x2="{margin_x + draw_w}" y2="{baseline_y + 12}" '
        'stroke="#6b7280" stroke-width="2" />'
        f"{fill_rect}"
        f"{''.join(rail_lines)}"
        f"{''.join(posts_svg)}"
        f'<text x="{margin_x}" y="28" fill="#e5e7eb" font-size="14" font-family="Arial, sans-serif">{description}</text>'
        "</svg>"
    )
