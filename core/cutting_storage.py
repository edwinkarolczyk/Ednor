# Plik: core/cutting_storage.py
# Wersja: 0.1.0
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List

from core.cutting_models import CutItem, StockBar

try:
    from config.paths import get_path as _wm_get_path
except Exception:
    _wm_get_path = None


DEFAULT_STOCK = {
    "bars": [],
    "offs": [],
}


def _local_data_root() -> Path:
    """Fallback, gdy moduł rozkroju działa poza Warsztat-Menager.

    Przykład: Ednor-main albo samodzielny test przez:
        py gui_cutting.py
    """

    return Path(__file__).resolve().parents[1] / "data"


def _get_path(key: str) -> str:
    if _wm_get_path is not None:
        try:
            value = _wm_get_path(key)
            if value:
                return value
        except Exception:
            pass

    data_base = _local_data_root()
    fallback = {
        "cutting.stock_bars_file": data_base / "magazyn" / "stock_bars.json",
        "cutting.jobs_dir": data_base / "rozkrój" / "jobs",
        "cutting.reports_dir": data_base / "rozkrój" / "reports",
    }
    return str(fallback[key])


def _ensure_parent(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _read_json(path: str, default: Any) -> Any:
    if not path:
        return default
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def _write_json(path: str, data: Any) -> str:
    _ensure_parent(path)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


def get_cutting_stock_path() -> str:
    return _get_path("cutting.stock_bars_file")


def get_cutting_jobs_dir() -> str:
    path = _get_path("cutting.jobs_dir")
    os.makedirs(path, exist_ok=True)
    return path


def get_cutting_reports_dir() -> str:
    path = _get_path("cutting.reports_dir")
    os.makedirs(path, exist_ok=True)
    return path


def load_cutting_stock_raw() -> Dict[str, Any]:
    path = get_cutting_stock_path()
    data = _read_json(path, DEFAULT_STOCK.copy())
    if not isinstance(data, dict):
        return DEFAULT_STOCK.copy()
    data.setdefault("bars", [])
    data.setdefault("offs", [])
    if not isinstance(data["bars"], list):
        data["bars"] = []
    if not isinstance(data["offs"], list):
        data["offs"] = []
    return data


def save_cutting_stock_raw(data: Dict[str, Any]) -> str:
    if not isinstance(data, dict):
        raise ValueError("cutting stock musi być słownikiem")
    data.setdefault("bars", [])
    data.setdefault("offs", [])
    return _write_json(get_cutting_stock_path(), data)


def load_stock_bars() -> List[StockBar]:
    data = load_cutting_stock_raw()
    bars: List[StockBar] = []

    for row in data.get("bars", []):
        if isinstance(row, dict):
            bar = StockBar.from_dict(row, source="stock")
            if bar.material_id and bar.length_mm > 0 and bar.qty > 0:
                bars.append(bar)

    for row in data.get("offs", []):
        if isinstance(row, dict):
            bar = StockBar.from_dict(row, source="offcut")
            if bar.material_id and bar.length_mm > 0 and bar.qty > 0:
                bars.append(bar)

    return bars


def add_stock_bar(
    *,
    material_id: str,
    length_mm: float,
    qty: int,
    name: str = "",
    location: str = "",
) -> str:
    data = load_cutting_stock_raw()
    material_id = str(material_id).strip()
    if not material_id:
        raise ValueError("material_id jest wymagane")
    length_mm = float(length_mm or 0)
    qty = int(qty or 0)
    if length_mm <= 0:
        raise ValueError("długość sztangi musi być > 0")
    if qty <= 0:
        raise ValueError("ilość musi być > 0")

    row_id = f"{material_id}_{int(length_mm)}_{int(time.time())}"
    data["bars"].append(
        {
            "id": row_id,
            "material_id": material_id,
            "name": name or material_id,
            "length_mm": length_mm,
            "qty": qty,
            "location": location,
        }
    )
    return save_cutting_stock_raw(data)


def save_cut_job(job_id: str, payload: Dict[str, Any]) -> str:
    job_id = _safe_name(job_id or f"JOB-{int(time.time())}")
    path = os.path.join(get_cutting_jobs_dir(), f"{job_id}.json")
    return _write_json(path, payload)


def load_cut_job(job_id: str) -> Dict[str, Any]:
    job_id = _safe_name(job_id)
    path = os.path.join(get_cutting_jobs_dir(), f"{job_id}.json")
    data = _read_json(path, {})
    return data if isinstance(data, dict) else {}


def save_cut_result(job_id: str, result: Dict[str, Any]) -> str:
    job_id = _safe_name(job_id or f"JOB-{int(time.time())}")
    path = os.path.join(get_cutting_reports_dir(), f"{job_id}_result.json")
    return _write_json(path, result)


def parse_cut_items(payload: Dict[str, Any]) -> List[CutItem]:
    arr = payload.get("items", [])
    if not isinstance(arr, list):
        return []
    out: List[CutItem] = []
    for row in arr:
        if not isinstance(row, dict):
            continue
        try:
            item = CutItem.from_dict(row)
        except Exception:
            continue
        if item.material_id and item.length_mm > 0 and item.qty > 0:
            out.append(item)
    return out


def _safe_name(value: str) -> str:
    value = str(value or "").strip()
    keep = []
    for ch in value:
        if ch.isalnum() or ch in ("-", "_", "."):
            keep.append(ch)
        else:
            keep.append("_")
    safe = "".join(keep).strip("._")
    return safe or f"JOB-{int(time.time())}"


def get_cutting_debug_paths() -> Dict[str, str]:
    return {
        "stock_bars": str(Path(get_cutting_stock_path())),
        "jobs_dir": str(Path(get_cutting_jobs_dir())),
        "reports_dir": str(Path(get_cutting_reports_dir())),
    }
