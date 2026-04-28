# Plik: core/ednor_paths.py
# Wersja: 0.2.0
from __future__ import annotations

from pathlib import Path


def app_root() -> Path:
    """Zwraca katalog główny programu EDNOR.

    Program ma działać z pendrive/serwera, więc dane trzymamy zawsze
    w folderze programu, obok plików .py.
    """
    return Path(__file__).resolve().parents[1]


def data_root() -> Path:
    """Główny katalog danych EDNOR — zawsze lokalnie przy programie."""
    return app_root() / "data"
