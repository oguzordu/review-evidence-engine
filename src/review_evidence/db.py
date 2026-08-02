"""SQLite baglantisi ve sema yonetimi.

Bu modul HTTP katmanini bilmez.
"""

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS reviews (
    id         INTEGER PRIMARY KEY,
    product_id TEXT NOT NULL,
    raw_text   TEXT NOT NULL,
    clean_text TEXT NOT NULL,
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_reviews_product ON reviews (product_id);

CREATE VIRTUAL TABLE IF NOT EXISTS reviews_fts USING fts5(
    clean_text,
    content="reviews",
    content_rowid="id"
);

CREATE TRIGGER IF NOT EXISTS reviews_ai AFTER INSERT ON reviews BEGIN
    INSERT INTO reviews_fts(rowid, clean_text) VALUES (new.id, new.clean_text);
END;
"""


def connect(db_path: Path) -> sqlite3.Connection:
    """Veritabani baglantisi acar. Satirlar sutun adiyla okunabilir olur."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Tablolari olusturur. Zaten varsa hicbir sey yapmaz."""
    conn.executescript(SCHEMA)
    conn.commit()
