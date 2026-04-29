# Plik: core/ednor_paths.py
# Wersja: 0.3.0
from __future__ import annotations

import sys
from pathlib import Path

APP_DATA_DIR_NAME = "Ednor_data"


def app_base_dir() -> Path:
    """Folder bazowy aplikacji.

    Dla EXE/PyInstaller:
        folder, w którym leży Ednor.exe

    Dla uruchomienia z plików .py:
        folder projektu, czyli katalog nadrzędny względem core/
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def app_root() -> Path:
    """Alias zgodności ze starszym kodem."""
    return app_base_dir()


def data_root() -> Path:
    return app_base_dir() / APP_DATA_DIR_NAME


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


def config_file() -> Path:
    return data_root() / "config.json"


def cutting_calculations_dir() -> Path:
    return cutting_dir() / "calculations"


def cutting_stock_bars_file() -> Path:
    return magazyn_dir() / "stock_bars.json"


def cutting_materials_file() -> Path:
    return magazyn_dir() / "cutting_materials.json"


def cutting_stock_moves_file() -> Path:
    return magazyn_dir() / "stock_moves.jsonl"


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
    cfg = config_file()
    if not cfg.exists():
        cfg.write_text(
            "{\n"
            '  "app": "Ednor",\n'
            '  "data_root": "Ednor_data",\n'
            '  "storage": "json",\n'
            '  "portable": true\n'
            "}\n",
            encoding="utf-8",
        )


def get_path(key: str) -> str:
    ensure_data_tree()
    mapping = {
        "app.base_dir": app_base_dir(),
        "cutting.stock_bars_file": cutting_stock_bars_file(),
        "cutting.materials_file": cutting_materials_file(),
        "cutting.stock_moves_file": cutting_stock_moves_file(),
        "cutting.settings_file": cutting_settings_file(),
        "config.file": config_file(),
        "cutting.jobs_dir": cutting_jobs_dir(),
        "cutting.reports_dir": cutting_reports_dir(),
        "cutting.calculations_dir": cutting_calculations_dir(),
        "data.root": data_root(),
        "paths.magazyn_dir": magazyn_dir(),
        "paths.cutting_dir": cutting_dir(),
    }
    if key not in mapping:
        raise KeyError(f"Nieznany klucz ścieżki: {key}")
    return str(mapping[key])
