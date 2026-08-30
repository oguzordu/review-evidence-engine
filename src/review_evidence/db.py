"""PostgreSQL baglantisi ve sema yonetimi.

Bu modul HTTP katmanini bilmez.
"""

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS reviews (
    id         SERIAL PRIMARY KEY,
    product_id TEXT NOT NULL,
    raw_text   TEXT NOT NULL,
    clean_text TEXT NOT NULL,
    created_at TEXT
);

ALTER TABLE reviews ADD COLUMN IF NOT EXISTS embedding vector(384);

CREATE INDEX IF NOT EXISTS idx_reviews_product ON reviews (product_id);

CREATE INDEX IF NOT EXISTS idx_reviews_fts
    ON reviews USING GIN (to_tsvector('turkish', clean_text));

CREATE INDEX IF NOT EXISTS idx_reviews_embedding
    ON reviews USING hnsw (embedding vector_cosine_ops);
"""


def connect(database_url: str) -> psycopg.Connection:
    """Veritabani baglantisi acar. Satirlar sozluk (dict) olarak okunabilir olur."""
    conn = psycopg.connect(database_url, row_factory=dict_row)
    try:
        register_vector(conn)
    except psycopg.ProgrammingError:
        # vector extension henuz kurulmamis; init_schema sonrasi tekrar denenir
        conn.rollback()
    return conn


def init_schema(conn: psycopg.Connection) -> None:
    """Tablolari, vector extension'i ve index'leri olusturur. Idempotent."""
    with conn.cursor() as cur:
        cur.execute(SCHEMA)
    conn.commit()
    register_vector(conn)
