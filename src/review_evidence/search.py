"""Anahtar kelime tabanli aday bulma (baseline arama).

Amac isabet degil kapsama: ilgili olabilecek yorumlari genis tutarak getirir.
Siniflama/sayim islemi bu modulun disinda (consensus.py) yapilir.
"""

import sqlite3

from review_evidence.text import normalize


def keyword_search(
    conn: sqlite3.Connection,
    product_id: str,
    query: str,
    limit: int = 200,
) -> list[sqlite3.Row]:
    """FTS5 ile sorudaki kelimelerden herhangi birini iceren yorumlari getirir."""
    tokens = [t for t in normalize(query).split() if t]
    if not tokens:
        return []

    match_query = " OR ".join(f"\"{t}\"" for t in tokens)

    rows = conn.execute(
        """
        SELECT r.id, r.raw_text, r.created_at
        FROM reviews_fts f
        JOIN reviews r ON r.id = f.rowid
        WHERE f.reviews_fts MATCH ? AND r.product_id = ?
        LIMIT ?
        """,
        (match_query, product_id, limit),
    ).fetchall()
    return rows
