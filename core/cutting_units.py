# Plik: core/cutting_units.py
# Wersja: 0.1.0
from __future__ import annotations

MM_PER_CM = 10.0
CM_PER_M = 100.0
MM_PER_M = 1000.0

MIN_SAW_ANGLE = -60.0
MAX_SAW_ANGLE = 60.0


def mm_to_m(value_mm: float) -> float:
    return float(value_mm or 0) / MM_PER_M


def cm_to_mm(value_cm: float) -> float:
    return float(value_cm or 0) * MM_PER_CM


def m_to_mm(value_m: float) -> float:
    return float(value_m or 0) * MM_PER_M


def format_mm(value_mm: float, *, decimals: int = 3) -> str:
    """Format: 1500 mm (1.5 m).

    Metry w nawiasie są zawsze pokazywane, zgodnie z założeniem:
    1 m = 100 cm = 1000 mm.
    """

    value_mm = float(value_mm or 0)
    value_m = mm_to_m(value_mm)

    mm_txt = f"{value_mm:g}"
    m_txt = f"{value_m:.{decimals}f}".rstrip("0").rstrip(".")
    if not m_txt:
        m_txt = "0"
    return f"{mm_txt} mm ({m_txt} m)"


def parse_length_to_mm(raw: str, default_unit: str = "mm") -> float:
    """Czyta długość i zwraca mm.

    Obsługuje:
      1500
      1500mm
      150cm
      1.5m
      1,5m

    Bez jednostki przyjmujemy default_unit, domyślnie mm.
    """

    text = str(raw or "").strip().lower().replace(",", ".")
    if "(" in text:
        text = text.split("(", 1)[0].strip()
    if not text:
        raise ValueError("pusta długość")

    try:
        return float(text)
    except ValueError:
        pass

    unit = default_unit.lower().strip() or "mm"
    for suffix in ("mm", "cm", "m"):
        if text.endswith(suffix):
            unit = suffix
            text = text[: -len(suffix)].strip()
            break

    value = float(text)
    if unit == "mm":
        return value
    if unit == "cm":
        return cm_to_mm(value)
    if unit == "m":
        return m_to_mm(value)
    raise ValueError(f"nieznana jednostka długości: {unit}")


def clamp_saw_angle(value: float) -> float:
    """Kąt techniczny w UI: -60 do 60 stopni.

    Piła fizycznie ma zakres 0–60, ale znak oznacza stronę ukosu:
    +45 = /
    -45 = \\
    0 = |
    """

    value = float(value or 0)
    if value < MIN_SAW_ANGLE:
        return MIN_SAW_ANGLE
    if value > MAX_SAW_ANGLE:
        return MAX_SAW_ANGLE
    return value


def validate_saw_angle(value: float) -> float:
    value = float(value or 0)
    if value < MIN_SAW_ANGLE or value > MAX_SAW_ANGLE:
        raise ValueError("Kąt piły musi być w zakresie -60° do 60°")
    return value
