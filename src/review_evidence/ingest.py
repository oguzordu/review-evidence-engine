"""Veri setinden veritabanina yukleme."""

import json
from pathlib import Path

import psycopg

from review_evidence.text import normalize


def load_reviews(conn: psycopg.Connection, path: Path) -> int:
    """JSON dosyasindaki yorumlari veritabanina yukler.

    Metni bos veya eksik olan kayitlar atlanir. Eklenen satir sayisini doner.
    """
    records = json.loads(path.read_text(encoding="utf-8"))

    rows = []
    for record in records:
        raw = record.get("text", "")
        if not raw.strip():
            continue
        rows.append(
            (
                record["product_id"],
                raw,
                normalize(raw),
                record.get("created_at"),
            )
        )

    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO reviews (product_id, raw_text, clean_text, created_at)"
            " VALUES (%s, %s, %s, %s)",
            rows,
        )
    conn.commit()
    return len(rows)
