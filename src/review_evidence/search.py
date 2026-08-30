"""Anahtar kelime tabanli aday bulma (baseline arama).

Amac isabet degil kapsama: ilgili olabilecek yorumlari genis tutarak getirir.
Siniflama/sayim islemi bu modulun disinda (consensus.py) yapilir.
"""

import psycopg

from review_evidence.text import normalize

KEYWORD_K = 100
VECTOR_K = 100
CANDIDATE_LIMIT = 200
RRF_K = 60


def _rrf_fuse(ranked_lists: list[list[dict]], k: int = RRF_K) -> list[dict]:
    """Reciprocal Rank Fusion: birden fazla sirali listeyi id bazinda birlestirir.

    Skor = toplam(1 / (k + rank)); rank her listede 0'dan baslar. Skorlari
    normalize etmeye gerek yok, sadece sira pozisyonu sayilir.
    """
    scores: dict = {}
    rows: dict = {}
    for ranked in ranked_lists:
        for rank, row in enumerate(ranked):
            rid = row["id"]
            scores[rid] = scores.get(rid, 0.0) + 1.0 / (k + rank)
            rows.setdefault(rid, row)
    ordered_ids = sorted(scores, key=lambda rid: scores[rid], reverse=True)
    return [rows[rid] for rid in ordered_ids]


def keyword_search(
    conn: psycopg.Connection,
    product_id: str,
    query: str,
    limit: int = KEYWORD_K,
) -> list[dict]:
    """PostgreSQL tam metin aramasiyla sorudaki kelimelerden herhangi birini
    iceren yorumlari, alaka (ts_rank) sirasina gore getirir (OR mantigi,
    Turkce dil yapilandirmasiyla)."""
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
            ORDER BY ts_rank(
                to_tsvector('turkish', clean_text),
                to_tsquery('turkish', %s)
            ) DESC
            LIMIT %s
            """,
            (product_id, tsquery_str, tsquery_str, limit),
        )
        return cur.fetchall()
