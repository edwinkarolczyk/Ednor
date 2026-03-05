import math


def generate_basic_fence_components(
    length_m: float,
    height_m: float,
    span_m: float,
    gates_count: int,
    wickets_count: int,
    rounding_mode: str = "ceil_0_1",
) -> list[tuple[str, str, float]]:
    if span_m <= 0:
        raise ValueError("span_m musi być większe od 0")

    spans = math.ceil(length_m / span_m)
    posts = spans + 1 + gates_count * 2 + wickets_count * 2
    rails_m = length_m * 2

    if rounding_mode == "ceil_0_1":
        rails_m = math.ceil(rails_m * 10) / 10.0

    return [
        ("Słupki", "szt", float(posts)),
        ("Profil poziomy", "mb", float(rails_m)),
    ]
