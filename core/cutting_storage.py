# Plik: core/cutting_storage.py
# Wersja: 0.5.0
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from core.cutting_models import CutItem, StockBar
from core.ednor_paths import (
    cutting_calculations_dir,
    cutting_jobs_dir,
    cutting_materials_file,
    cutting_reports_dir,
    cutting_settings_file,
    cutting_stock_bars_file,
    ensure_data_tree,
)

DEFAULT_STOCK = {
    "bars": [],
    "offs": [],
}

DEFAULT_MATERIALS = {
    "_opis": {
        "material_id": "stały identyfikator używany w kalkulacjach, np. profil_40x30x2",
        "typ": "grupa materiału, np. profil/rura/pret/plaskownik",
        "nazwa": "czytelna nazwa na liście",
        "rozmiar": "wymiar handlowy, np. 40x30x2 albo fi 30",
        "domyslna_dlugosc_mm": "standardowa długość sztangi w mm, np. 6000",
        "aktywny": "false ukrywa materiał z listy bez kasowania historii",
        "uwagi": "dowolny opis",
    },
    "materials": [
        {
            "material_id": "profil_40x30x2",
            "typ": "profil",
            "nazwa": "Profil 40x30x2",
            "rozmiar": "40x30x2",
            "domyslna_dlugosc_mm": 6000,
            "aktywny": True,
            "uwagi": "",
        },
        {
            "material_id": "rura_fi30",
            "typ": "rura",
            "nazwa": "Rura fi 30",
            "rozmiar": "fi 30",
            "domyslna_dlugosc_mm": 6000,
            "aktywny": True,
            "uwagi": "",
        },
        {
            "material_id": "rura_fi35",
            "typ": "rura",
            "nazwa": "Rura fi 35",
            "rozmiar": "fi 35",
            "domyslna_dlugosc_mm": 6000,
            "aktywny": True,
            "uwagi": "",
        },
    ],
}


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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


def _stamp_id(prefix: str) -> str:
    return f"{prefix}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


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


def _material_stock_qty(data: Dict[str, Any], material_id: str) -> int:
    total = 0
    for row in data.get("bars", []):
        if not isinstance(row, dict):
            continue
        if str(row.get("material_id", "")).strip() == material_id:
            try:
                total += int(row.get("qty", row.get("ilosc", 0)) or 0)
            except Exception:
                pass
    return total


def get_cutting_stock_path() -> str:
    ensure_data_tree()
    return str(cutting_stock_bars_file())


def get_cutting_jobs_dir() -> str:
    ensure_data_tree()
    path = str(cutting_jobs_dir())
    os.makedirs(path, exist_ok=True)
    return path


def get_cutting_reports_dir() -> str:
    ensure_data_tree()
    path = str(cutting_reports_dir())
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


def load_cutting_settings() -> Dict[str, Any]:
    ensure_data_tree()
    path = cutting_settings_file()
    data = _read_json(str(path), {})
    return data if isinstance(data, dict) else {}


def save_cutting_settings(data: Dict[str, Any]) -> str:
    ensure_data_tree()
    if not isinstance(data, dict):
        data = {}
    return _write_json(str(cutting_settings_file()), data)


def update_cutting_setting(key: str, value: Any) -> str:
    data = load_cutting_settings()
    data[str(key)] = value
    return save_cutting_settings(data)


def get_cutting_materials_path() -> str:
    ensure_data_tree()
    path = cutting_materials_file()
    if not path.exists():
        _write_json(str(path), DEFAULT_MATERIALS)
    return str(path)


def load_materials_raw() -> Dict[str, Any]:
    path = get_cutting_materials_path()
    data = _read_json(path, DEFAULT_MATERIALS.copy())
    if not isinstance(data, dict):
        data = DEFAULT_MATERIALS.copy()
    data.setdefault("materials", [])
    if not isinstance(data["materials"], list):
        data["materials"] = []
    return data


def save_materials_raw(data: Dict[str, Any]) -> str:
    if not isinstance(data, dict):
        raise ValueError("materials musi być słownikiem")
    data.setdefault("materials", [])
    if "_opis" not in data:
        data["_opis"] = DEFAULT_MATERIALS["_opis"]
    return _write_json(get_cutting_materials_path(), data)


def load_materials() -> List[Dict[str, Any]]:
    data = load_materials_raw()
    stock = load_cutting_stock_raw()
    out: List[Dict[str, Any]] = []
    for row in data.get("materials", []):
        if not isinstance(row, dict):
            continue
        material_id = str(row.get("material_id", "")).strip()
        if not material_id:
            continue
        item = dict(row)
        item["stock_qty"] = _material_stock_qty(stock, material_id)
        out.append(item)
    return out


def material_label(row: Dict[str, Any]) -> str:
    material_id = str(row.get("material_id", "")).strip()
    typ = str(row.get("typ", "")).strip()
    nazwa = str(row.get("nazwa", "")).strip()
    rozmiar = str(row.get("rozmiar", "")).strip()
    qty = row.get("stock_qty", 0)
    base = nazwa or material_id
    suffix = f" ({qty} szt. w stoku)"
    if typ or rozmiar:
        return f"{typ} > {base} {rozmiar}{suffix}".strip()
    return f"{base}{suffix}"


def upsert_material(payload: Dict[str, Any]) -> str:
    data = load_materials_raw()
    material_id = str(payload.get("material_id", "")).strip()
    if not material_id:
        raise ValueError("material_id jest wymagane")

    row = {
        "material_id": material_id,
        "typ": str(payload.get("typ", "")).strip(),
        "nazwa": str(payload.get("nazwa", material_id)).strip() or material_id,
        "rozmiar": str(payload.get("rozmiar", "")).strip(),
        "domyslna_dlugosc_mm": float(payload.get("domyslna_dlugosc_mm", 6000) or 6000),
        "aktywny": bool(payload.get("aktywny", True)),
        "uwagi": str(payload.get("uwagi", "")).strip(),
    }

    updated = False
    out = []
    for old in data.get("materials", []):
        if isinstance(old, dict) and str(old.get("material_id", "")).strip() == material_id:
            out.append(row)
            updated = True
        else:
            out.append(old)
    if not updated:
        out.append(row)
    data["materials"] = out
    return save_materials_raw(data)


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


def log_stock_move(payload: Dict[str, Any]) -> str:
    data = load_cutting_stock_raw()
    moves = data.get("moves", [])
    if not isinstance(moves, list):
        moves = []
    entry = dict(payload or {})
    entry["at"] = _now_iso()
    moves.append(entry)
    data["moves"] = moves
    return save_cutting_stock_raw(data)


def add_remnant(material_id: str, length_mm: float, qty: int = 1) -> str:
    data = load_cutting_stock_raw()
    material_id = str(material_id).strip()
    length_mm = float(length_mm or 0)
    qty = int(qty or 0)
    if not material_id:
        raise ValueError("material_id jest wymagane")
    if length_mm <= 0:
        raise ValueError("długość odpadu musi być > 0")
    if qty <= 0:
        raise ValueError("ilość musi być > 0")
    row_id = f"off_{material_id}_{int(length_mm)}_{int(time.time())}"
    data["offs"].append(
        {
            "id": row_id,
            "material_id": material_id,
            "name": f"Offcut {material_id}",
            "length_mm": length_mm,
            "qty": qty,
            "location": "odpad",
        }
    )
    return save_cutting_stock_raw(data)


def accept_cutting_calculation(job_id: str, result: Dict[str, Any]) -> str:
    """Akceptuje kalkulację: zmniejsza stan sztang w magazynie.

    Minimalna wersja rozchodu:
    - odejmuje 1 sztangę z `bars` dla każdej użytej sztangi typu stock,
    - nie rozlicza jeszcze dokładnie odpadów użytkowych,
    - zabezpiecza przed podwójną akceptacją po `accepted_at`.
    """

    if not isinstance(result, dict):
        raise ValueError("Brak wyniku kalkulacji do akceptacji")
    if result.get("accepted_at"):
        raise ValueError("Ta kalkulacja została już zaakceptowana")

    stock = load_cutting_stock_raw()
    bars = stock.get("bars", [])
    if not isinstance(bars, list):
        bars = []

    used = result.get("bars_used", [])
    if not isinstance(used, list):
        used = []

    errors: List[str] = []
    for used_bar in used:
        if not isinstance(used_bar, dict):
            continue
        if used_bar.get("source") != "stock":
            continue
        material_id = str(used_bar.get("material_id", "")).strip()
        length = float(used_bar.get("bar_length_mm", 0) or 0)
        if not material_id or length <= 0:
            continue

        deducted = False
        for row in bars:
            if not isinstance(row, dict):
                continue
            row_mid = str(row.get("material_id", "")).strip()
            row_len = float(row.get("length_mm", row.get("dlugosc_mm", 0)) or 0)
            row_qty = int(row.get("qty", row.get("ilosc", 0)) or 0)
            if row_mid == material_id and abs(row_len - length) < 0.001 and row_qty > 0:
                row["qty"] = row_qty - 1
                deducted = True
                break
        if not deducted:
            errors.append(f"{material_id} / {length:g} mm")

    if errors:
        raise ValueError("Brak stanu do rozchodu: " + ", ".join(errors))

    stock["bars"] = bars
    save_cutting_stock_raw(stock)
    result["accepted_at"] = _now_iso()
    result["status"] = "accepted"
    return save_cut_result(job_id, result)


def save_cut_job(job_id: str, payload: Dict[str, Any]) -> str:
    job_id = _safe_name(job_id or f"JOB-{int(time.time())}")
    path = os.path.join(get_cutting_jobs_dir(), f"{job_id}.json")
    return _write_json(path, payload)


def save_cutting_calculation(job_id: str, payload: Dict[str, Any], result: Dict[str, Any]) -> str:
    calc_id = _safe_name(job_id or _stamp_id("KALK"))
    data = {
        "calculation_id": calc_id,
        "created_at": _now_iso(),
        "status": result.get("status", "draft") if isinstance(result, dict) else "draft",
        "job": payload,
        "result": result,
    }
    path = os.path.join(str(cutting_calculations_dir()), f"{calc_id}.json")
    return _write_json(path, data)


def list_cutting_calculations() -> List[Dict[str, Any]]:
    ensure_data_tree()
    out: List[Dict[str, Any]] = []
    calc_dir = cutting_calculations_dir()
    calc_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(calc_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        data = _read_json(str(path), {})
        if not isinstance(data, dict):
            continue
        result = data.get("result") if isinstance(data.get("result"), dict) else {}
        job = data.get("job") if isinstance(data.get("job"), dict) else {}
        summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
        out.append(
            {
                "calculation_id": data.get("calculation_id") or path.stem,
                "created_at": data.get("created_at", ""),
                "status": result.get("status") or data.get("status", "draft"),
                "job_id": job.get("job_id") or result.get("job_id") or path.stem,
                "bars_count": summary.get("bars_count", 0),
                "usage_percent": summary.get("usage_percent", 0),
                "path": str(path),
            }
        )
    return out


def load_cutting_calculation(calculation_id: str) -> Dict[str, Any]:
    calculation_id = _safe_name(calculation_id)
    path = os.path.join(str(cutting_calculations_dir()), f"{calculation_id}.json")
    data = _read_json(path, {})
    return data if isinstance(data, dict) else {}


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


def get_cutting_debug_paths() -> Dict[str, str]:
    return {
        "stock_bars": str(Path(get_cutting_stock_path())),
        "materials": str(Path(get_cutting_materials_path())),
        "settings": str(cutting_settings_file()),
        "jobs_dir": str(Path(get_cutting_jobs_dir())),
        "reports_dir": str(Path(get_cutting_reports_dir())),
        "calculations_dir": str(cutting_calculations_dir()),
    }
