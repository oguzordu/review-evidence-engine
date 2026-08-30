"""Anahtar kelime tabanli aday bulma (baseline arama).

Amac isabet degil kapsama: ilgili olabilecek yorumlari genis tutarak getirir.
Siniflama/sayim islemi bu modulun disinda (consensus.py) yapilir.
"""

import psycopg

from review_evidence.text import normalize


def keyword_search(
    conn: psycopg.Connection,
    product_id: str,
    query: str,
    limit: int = 200,
) -> list[dict]:
    """PostgreSQL tam metin aramasiyla sorudaki kelimelerden herhangi birini
    iceren yorumlari getirir (OR mantigi, Turkce dil yapilandirmasiyla)."""
    tokens = [t for t in normalize(query).split() if t]
    if not tokens:
        return []

    tsquery_str = " | ".join(tokens)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, raw_text, created_at
            FROM reviews
            WHERE product_id = %s
              AND to_tsvector('turkish', clean_text) @@ to_tsquery('turkish', %s)
            LIMIT %s
            """,
            (product_id, tsquery_str, limit),
        )
        return cur.fetchall()
