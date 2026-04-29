# Plik: core/cutting_storage.py
# Wersja: 0.6.0
from __future__ import annotations

import json
import os
import re
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
    cutting_stock_moves_file,
    transports_file,
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


def _num_clean(value: Any) -> str:
    text = str(value or "").strip().replace(",", ".")
    if not text:
        return ""
    try:
        number = float(text)
        return f"{number:g}"
    except Exception:
        return text


def material_size_from_dims(typ: str, a: Any = "", b: Any = "", c: Any = "") -> str:
    typ_norm = str(typ or "").strip().lower()
    a_txt = _num_clean(a)
    b_txt = _num_clean(b)
    c_txt = _num_clean(c)

    if typ_norm in ("profil", "profil zamknięty", "profil_zamkniety"):
        return "x".join(part for part in (a_txt, b_txt, c_txt) if part)
    if typ_norm == "rura":
        return f"fi{a_txt}x{b_txt}" if b_txt else f"fi{a_txt}"
    if typ_norm in ("pret", "pręt"):
        return f"fi{a_txt}"
    if typ_norm in ("plaskownik", "płaskownik"):
        return "x".join(part for part in (a_txt, b_txt) if part)
    return "x".join(part for part in (a_txt, b_txt, c_txt) if part)


def _slugify_material(value: str) -> str:
    text = str(value or "").strip().lower()
    repl = {
        "ą": "a",
        "ć": "c",
        "ę": "e",
        "ł": "l",
        "ń": "n",
        "ó": "o",
        "ś": "s",
        "ż": "z",
        "ź": "z",
    }
    for src, dst in repl.items():
        text = text.replace(src, dst)
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "material"


def _title_material_type(typ: str) -> str:
    typ = str(typ or "").strip().lower()
    labels = {
        "profil": "Profil",
        "rura": "Rura",
        "pret": "Pręt",
        "pręt": "Pręt",
        "plaskownik": "Płaskownik",
        "płaskownik": "Płaskownik",
        "profil zamknięty": "Profil",
        "profil_zamkniety": "Profil",
    }
    return labels.get(typ, typ.capitalize() if typ else "Surowiec")


def build_material_display_name(typ: str, rozmiar: str) -> str:
    typ_label = _title_material_type(typ)
    rozmiar = str(rozmiar or "").strip()
    return f"{typ_label} {rozmiar}".strip()


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


def _material_stock_mm(data: Dict[str, Any], material_id: str) -> float:
    total = 0.0
    for bucket in ("bars", "offs"):
        for row in data.get(bucket, []):
            if not isinstance(row, dict):
                continue
            if str(row.get("material_id", "")).strip() != material_id:
                continue
            total += float(row.get("length_mm", 0) or 0) * int(row.get("qty", 0) or 0)
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
        item["stock_mb"] = round(_material_stock_mm(stock, material_id) / 1000.0, 3)
        out.append(item)
    return out


def material_label(row: Dict[str, Any]) -> str:
    material_id = str(row.get("material_id", "")).strip()
    typ = str(row.get("typ", "")).strip()
    nazwa = str(row.get("nazwa", "")).strip()
    rozmiar = str(row.get("rozmiar", "")).strip()
    stock_mb = float(row.get("stock_mb", 0) or 0)
    base = nazwa or material_id
    if rozmiar and rozmiar not in base:
        base = f"{base} {rozmiar}".strip()
    return f"{base} (stan {stock_mb:g} mb)"


def upsert_material(payload: Dict[str, Any]) -> str:
    data = load_materials_raw()
    typ = str(payload.get("typ", "")).strip()
    nazwa = str(payload.get("nazwa") or payload.get("display_name") or "").strip()
    rozmiar = str(payload.get("rozmiar", "")).strip()
    wymiary = payload.get("wymiary") if isinstance(payload.get("wymiary"), dict) else {}

    if not rozmiar and wymiary:
        rozmiar = material_size_from_dims(
            typ,
            wymiary.get("a", ""),
            wymiary.get("b", ""),
            wymiary.get("c", ""),
        )

    if not nazwa:
        nazwa = build_material_display_name(typ, rozmiar) if (typ or rozmiar) else "Surowiec"

    material_id = str(payload.get("material_id", "")).strip()
    if not material_id:
        base_for_id = f"{typ} {rozmiar}".strip() or nazwa
        material_id = _slugify_material(base_for_id)

    row = {
        "material_id": material_id,
        "typ": typ,
        "nazwa": nazwa,
        "display_name": str(payload.get("display_name") or nazwa).strip(),
        "rozmiar": rozmiar,
        "domyslna_dlugosc_mm": float(payload.get("domyslna_dlugosc_mm", 6000) or 6000),
        "aktywny": bool(payload.get("aktywny", True)),
        "uwagi": str(payload.get("uwagi", "")).strip(),
    }
    if wymiary:
        row["wymiary"] = wymiary
    if payload.get("cena_za_m") not in (None, ""):
        try:
            row["cena_za_m"] = float(payload.get("cena_za_m"))
        except Exception:
            row["cena_za_m"] = payload.get("cena_za_m")

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
    entry = dict(payload or {})
    entry.setdefault("at", _now_iso())
    ensure_data_tree()
    path = cutting_stock_moves_file()
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return str(path)


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

DEFAULT_TRANSPORTS = {"_opis": {}, "last_seq": 0, "transports": []}

def get_transports_path() -> str:
    ensure_data_tree()
    path = transports_file()
    if not path.exists():
        _write_json(str(path), DEFAULT_TRANSPORTS)
    return str(path)

def load_transports_raw() -> Dict[str, Any]:
    data = _read_json(get_transports_path(), DEFAULT_TRANSPORTS.copy())
    if not isinstance(data, dict):
        data = DEFAULT_TRANSPORTS.copy()
    data.setdefault("last_seq", 0)
    data.setdefault("transports", [])
    return data

def next_transport_id(data: Dict[str, Any] | None = None) -> str:
    data = data if isinstance(data, dict) else load_transports_raw()
    return f"TR-{int(data.get('last_seq',0) or 0)+1:06d}"

def save_transport(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = load_transports_raw()
    seq = int(data.get("last_seq", 0) or 0) + 1
    tid = f"TR-{seq:06d}"
    transport = {
        "transport_id": tid,
        "created_at": _now_iso(),
        "supplier": str(payload.get("supplier", "")).strip(),
        "transport_cost": float(payload.get("transport_cost", 0) or 0),
        "price_mode": str(payload.get("price_mode", "netto") or "netto"),
        "vat_percent": float(payload.get("vat_percent", 23) or 23),
        "lines": list(payload.get("lines", []) or []),
    }
    if not transport["lines"]:
        raise ValueError("Transport musi mieć przynajmniej jedną pozycję.")
    data["last_seq"] = seq
    data["transports"].append(transport)
    _write_json(get_transports_path(), data)
    for idx, line in enumerate(transport["lines"], start=1):
        add_stock_bar(material_id=str(line.get("material_id","")), length_mm=float(line.get("bar_length_mm",0) or 0), qty=int(line.get("qty",0) or 0), name=str(line.get("material_display", "")), location="transport", transport_id=tid, line_id=f"{tid}-{idx:03d}", price_per_m=float(line.get("price_per_m",0) or 0), price_mode=transport["price_mode"], vat_percent=transport["vat_percent"])
    return transport
