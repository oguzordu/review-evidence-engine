"""Mevcut (embedding'i NULL olan) yorumlar icin embedding uretir.

Yuklu veriye pgvector sonradan eklendiginde bir kez calistirilir. Idempotent:
zaten embedding'i olan satirlara dokunmaz.

Kullanim:
    python scripts/backfill_embeddings.py
"""

from review_evidence.config import DATABASE_URL
from review_evidence.db import connect, init_schema
from review_evidence.embedding import sentence_transformer_encoder

BATCH_SIZE = 64


def main() -> None:
    conn = connect(DATABASE_URL)
    init_schema(conn)
    encode = sentence_transformer_encoder()

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, raw_text FROM reviews WHERE embedding IS NULL ORDER BY id"
        )
        pending = cur.fetchall()

    if not pending:
        print("embedding'i eksik yorum yok.")
        return

    print(f"{len(pending)} yorum icin embedding uretilecek.")
    done = 0
    for start in range(0, len(pending), BATCH_SIZE):
        chunk = pending[start : start + BATCH_SIZE]
        vectors = encode([row["raw_text"] for row in chunk])
        with conn.cursor() as cur:
            cur.executemany(
                "UPDATE reviews SET embedding = %s WHERE id = %s",
                [(vec, row["id"]) for row, vec in zip(chunk, vectors)],
            )
        conn.commit()
        done += len(chunk)
        print(f"  {done}/{len(pending)}")

    conn.close()
    print("bitti.")


if __name__ == "__main__":
    main()
