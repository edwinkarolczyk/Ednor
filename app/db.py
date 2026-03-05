from pathlib import Path
import sqlite3

from app.config import DATA_DIR

DB_PATH = DATA_DIR / "ednor.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(Path(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn
