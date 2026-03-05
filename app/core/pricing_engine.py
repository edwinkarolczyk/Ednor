def calc_totals(
    lines: list[dict],
    margin_percent: float,
    labor_hours_planned: float,
    labor_hours_manual: float | None,
    use_manual_labor: bool,
    labor_rate_per_h: float,
    power_kwh: float,
    power_rate_per_kwh: float,
    installation_cost: float,
    service_cost: float,
) -> tuple[float, float, float, float]:
    chosen_hours = labor_hours_manual if use_manual_labor and labor_hours_manual is not None else labor_hours_planned
    labor_cost = chosen_hours * labor_rate_per_h
    power_cost = power_kwh * power_rate_per_kwh
    subtotal = sum(line["total_price"] for line in lines) + labor_cost + power_cost + installation_cost + service_cost
    total = subtotal * (1 + margin_percent / 100)
    return round(subtotal, 2), round(total, 2), round(labor_cost, 2), round(power_cost, 2)
