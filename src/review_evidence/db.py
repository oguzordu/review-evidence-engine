"""PostgreSQL baglantisi ve sema yonetimi.

Bu modul HTTP katmanini bilmez.
"""

import psycopg
from psycopg.rows import dict_row

SCHEMA = """
CREATE TABLE IF NOT EXISTS reviews (
    id         SERIAL PRIMARY KEY,
    product_id TEXT NOT NULL,
    raw_text   TEXT NOT NULL,
    clean_text TEXT NOT NULL,
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_reviews_product ON reviews (product_id);

CREATE INDEX IF NOT EXISTS idx_reviews_fts
    ON reviews USING GIN (to_tsvector('turkish', clean_text));
"""


def connect(database_url: str) -> psycopg.Connection:
    """Veritabani baglantisi acar. Satirlar sozluk (dict) olarak okunabilir olur."""
    conn = psycopg.connect(database_url, row_factory=dict_row)
    return conn


def init_schema(conn: psycopg.Connection) -> None:
    """Tablolari olusturur. Zaten varsa hicbir sey yapmaz."""
    with conn.cursor() as cur:
        cur.execute(SCHEMA)
    conn.commit()
