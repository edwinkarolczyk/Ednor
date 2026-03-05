import math


def _ceil_to_tenth(value: float) -> float:
    return math.ceil(value * 10) / 10


def generate_basic_fence_lines(length_m: float, span_m: float, gates_count: int, wickets_count: int) -> list[dict]:
    spans = math.ceil(length_m / span_m)
    posts = spans + 1 + gates_count * 2 + wickets_count * 2
    rails_m = _ceil_to_tenth(length_m * 2)

    return [
        {"name": "Słupki", "unit": "szt", "qty": float(posts)},
        {"name": "Profil poziomy", "unit": "mb", "qty": float(rails_m)},
    ]
