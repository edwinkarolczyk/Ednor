# Plik: config/paths.py
from __future__ import annotations

import os
from typing import Dict

_PATHS = None


def _default_paths() -> Dict[str, str]:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    data_base = os.path.join(root, "data")
    return {
        "paths.data_dir": data_base,
        "paths.products_dir": os.path.join(data_base, "produkty"),
        "paths.tools_dir": os.path.join(data_base, "narzedzia"),
        "paths.layout_dir": os.path.join(data_base, "layout"),
        "paths.orders_dir": os.path.join(data_base, "zlecenia"),
        "paths.cutting_dir": os.path.join(data_base, "rozkrój"),
        "warehouse.stock_source": os.path.join(data_base, "magazyn", "magazyn.json"),
        "warehouse.reservations_file": os.path.join(data_base, "magazyn", "rezerwacje.json"),
        "bom.file": os.path.join(data_base, "produkty", "bom.json"),
        # Rozkrój / cięcie sztang, profili, prętów, płaskowników.
        # Celowo osobny plik, żeby nie zmieniać obecnego formatu magazyn/magazyn.json.
        "cutting.stock_bars_file": os.path.join(data_base, "magazyn", "stock_bars.json"),
        "cutting.jobs_dir": os.path.join(data_base, "rozkrój", "jobs"),
        "cutting.reports_dir": os.path.join(data_base, "rozkrój", "reports"),
        "tools.types_file": os.path.join(data_base, "narzedzia", "typy_narzedzi.json"),
        "tools.statuses_file": os.path.join(data_base, "narzedzia", "statusy_narzedzi.json"),
    }


def ensure_core_tree() -> None:
    defaults = _default_paths()
    dirs = [
        "paths.data_dir",
        "paths.products_dir",
        "paths.tools_dir",
        "paths.layout_dir",
        "paths.orders_dir",
        "paths.cutting_dir",
    ]
    for dkey in dirs:
        try:
            os.makedirs(defaults[dkey], exist_ok=True)
        except Exception:
            pass

    for fkey in ("cutting.jobs_dir", "cutting.reports_dir"):
        try:
            os.makedirs(defaults[fkey], exist_ok=True)
        except Exception:
            pass


def get_base_dir() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def get_path(key: str) -> str:
    global _PATHS
    if _PATHS is None:
        _PATHS = _default_paths()
        ensure_core_tree()
    return _PATHS.get(key, "")
