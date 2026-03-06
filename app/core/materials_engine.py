from __future__ import annotations


def normalize_price(material, input_price: float, input_unit: str) -> dict[str, float | None]:
    normalized = {
        "normalized_price_per_kg": None,
        "normalized_price_per_mb": None,
        "normalized_price_per_piece": None,
    }

    if input_unit == "kg":
        normalized["normalized_price_per_kg"] = input_price
        if material.weight_per_meter_kg:
            normalized["normalized_price_per_mb"] = input_price * material.weight_per_meter_kg
        if material.weight_per_piece_kg:
            normalized["normalized_price_per_piece"] = input_price * material.weight_per_piece_kg
    elif input_unit == "mb":
        normalized["normalized_price_per_mb"] = input_price
        if material.weight_per_meter_kg and material.weight_per_meter_kg > 0:
            normalized["normalized_price_per_kg"] = input_price / material.weight_per_meter_kg
        if material.trade_length_m:
            normalized["normalized_price_per_piece"] = input_price * material.trade_length_m
    elif input_unit == "szt":
        normalized["normalized_price_per_piece"] = input_price
        if material.trade_length_m and material.trade_length_m > 0:
            normalized["normalized_price_per_mb"] = input_price / material.trade_length_m
        if material.weight_per_piece_kg and material.weight_per_piece_kg > 0:
            normalized["normalized_price_per_kg"] = input_price / material.weight_per_piece_kg
    else:
        raise ValueError("Nieobsługiwana jednostka ceny.")

    return normalized


def normalize_quantity_for_stock(material, qty_input: float, qty_unit: str) -> dict[str, float | str]:
    stock_unit = (material.stock_unit or material.unit or "").strip().lower()
    qty_unit = (qty_unit or "").strip().lower()

    if not stock_unit:
        raise ValueError("Brak jednostki magazynowej materiału.")

    if qty_unit == stock_unit:
        qty_stock = qty_input
    elif qty_unit == "kg" and stock_unit == "mb" and material.weight_per_meter_kg:
        qty_stock = qty_input / material.weight_per_meter_kg
    elif qty_unit == "mb" and stock_unit == "kg" and material.weight_per_meter_kg:
        qty_stock = qty_input * material.weight_per_meter_kg
    elif qty_unit == "szt" and stock_unit == "mb" and material.trade_length_m:
        qty_stock = qty_input * material.trade_length_m
    elif qty_unit == "mb" and stock_unit == "szt" and material.trade_length_m:
        qty_stock = qty_input / material.trade_length_m
    else:
        raise ValueError("Brak danych do przeliczenia jednostek dla materiału")

    return {
        "qty_stock": round(qty_stock, 3),
        "qty_stock_unit": stock_unit,
    }
