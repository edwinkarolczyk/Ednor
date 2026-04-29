# Plik: core/ednor_paths.py
# Wersja: 0.3.0
from __future__ import annotations

from pathlib import Path


def app_root() -> Path:
    """Folder programu EDNOR.

    Program ma działać z pendrive/serwera, więc dane są zawsze obok programu.
    """
    return Path(__file__).resolve().parents[1]


def data_root() -> Path:
    return app_root() / "data"


def magazyn_dir() -> Path:
    return data_root() / "magazyn"


def cutting_dir() -> Path:
    return data_root() / "rozkroj"


def cutting_jobs_dir() -> Path:
    return cutting_dir() / "jobs"


def cutting_reports_dir() -> Path:
    return cutting_dir() / "reports"


def cutting_settings_file() -> Path:
    return cutting_dir() / "settings.json"


def cutting_calculations_dir() -> Path:
    return cutting_dir() / "calculations"


def cutting_stock_bars_file() -> Path:
    return magazyn_dir() / "stock_bars.json"


def cutting_materials_file() -> Path:
    return magazyn_dir() / "cutting_materials.json"


def ensure_data_tree() -> None:
    for path in (
        data_root(),
        magazyn_dir(),
        cutting_dir(),
        cutting_jobs_dir(),
        cutting_reports_dir(),
        cutting_calculations_dir(),
    ):
        path.mkdir(parents=True, exist_ok=True)


def get_path(key: str) -> str:
    ensure_data_tree()
    mapping = {
        "cutting.stock_bars_file": cutting_stock_bars_file(),
        "cutting.materials_file": cutting_materials_file(),
        "cutting.settings_file": cutting_settings_file(),
        "cutting.jobs_dir": cutting_jobs_dir(),
        "cutting.reports_dir": cutting_reports_dir(),
        "cutting.calculations_dir": cutting_calculations_dir(),
        "paths.data_root": data_root(),
        "paths.magazyn_dir": magazyn_dir(),
        "paths.cutting_dir": cutting_dir(),
    }
    if key not in mapping:
        raise KeyError(f"Nieznany klucz ścieżki: {key}")
    return str(mapping[key])
