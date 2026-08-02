"""Veri setinden veritabanina yukleme."""

import json
import sqlite3
from pathlib import Path

from review_evidence.text import normalize


def load_reviews(conn: sqlite3.Connection, path: Path) -> int:
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

    conn.executemany(
        "INSERT INTO reviews (product_id, raw_text, clean_text, created_at)"
        " VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return len(rows)