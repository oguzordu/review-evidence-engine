"""Veri setinden veritabanina yukleme."""

import json
from pathlib import Path

import psycopg

from review_evidence.embedding import EncoderFn, sentence_transformer_encoder
from review_evidence.text import normalize


def load_reviews(
    conn: psycopg.Connection,
    path: Path,
    encode: EncoderFn | None = None,
) -> int:
    """JSON dosyasindaki yorumlari veritabanina yukler.

    Metni bos veya eksik olan kayitlar atlanir. Her yorum icin raw_text'ten
    bir embedding uretilir; encode verilmezse lokal model kullanilir. Embedding
    uretimi basarisiz olursa satirlar embedding'siz (NULL) yuklenir.
    Eklenen satir sayisini doner.
    """
    records = json.loads(path.read_text(encoding="utf-8"))

    prepared = []
    for record in records:
        raw = record.get("text", "")
        if not raw.strip():
            continue
        prepared.append((record["product_id"], raw, record.get("created_at")))

    if not prepared:
        return 0

    if encode is None:
        encode = sentence_transformer_encoder()

    raw_texts = [raw for _, raw, _ in prepared]
    try:
        embeddings = encode(raw_texts)
    except Exception as exc:  # model yok / indirilemedi -> embedding'siz devam
        print(f"[ingest] embedding uretilemedi, NULL ile yukleniyor: {exc}")
        embeddings = [None] * len(prepared)

    rows = [
        (product_id, raw, normalize(raw), created_at, emb)
        for (product_id, raw, created_at), emb in zip(prepared, embeddings)
    ]

    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO reviews (product_id, raw_text, clean_text, created_at, embedding)"
            " VALUES (%s, %s, %s, %s, %s)",
            rows,
        )
    conn.commit()
    return len(rows)
