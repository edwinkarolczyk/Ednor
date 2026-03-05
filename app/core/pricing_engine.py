from collections.abc import Sequence


def calc_totals(
    lines: Sequence[float],
    margin_percent: float,
    labor_hours_used: float,
    labor_rate_per_h: float,
    power_kwh: float,
    power_rate_per_kwh: float,
    installation_cost: float,
    service_cost: float,
) -> tuple[float, float]:
    lines_sum = sum(lines)
    labor_cost = labor_hours_used * labor_rate_per_h
    power_cost = power_kwh * power_rate_per_kwh
    subtotal = lines_sum + labor_cost + power_cost + installation_cost + service_cost
    total = subtotal * (1 + (margin_percent / 100.0))
    return round(subtotal, 2), round(total, 2)
