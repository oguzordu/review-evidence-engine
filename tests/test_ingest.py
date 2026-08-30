import json

from review_evidence.ingest import load_reviews


def test_load_reviews_returns_inserted_count(db_conn, tmp_path):
    source = tmp_path / "reviews.json"
    source.write_text(
        json.dumps(
            [
                {"product_id": "p1", "text": "Ürün güzel", "created_at": "2026-01-15"},
                {"product_id": "p1", "text": "Kargo geç", "created_at": "2026-02-03"},
            ]
        ),
        encoding="utf-8",
    )

    inserted = load_reviews(db_conn, source)

    assert inserted == 2


def test_load_reviews_stores_normalized_text(db_conn, tmp_path):
    source = tmp_path / "reviews.json"
    source.write_text(
        json.dumps([{"product_id": "p1", "text": "  ÜRÜN   ÇOOOK  GÜZEL "}]),
        encoding="utf-8",
    )

    load_reviews(db_conn, source)
    with db_conn.cursor() as cur:
        cur.execute("SELECT raw_text, clean_text FROM reviews")
        row = cur.fetchone()

    assert row["raw_text"] == "  ÜRÜN   ÇOOOK  GÜZEL "
    assert row["clean_text"] == "ürün çook güzel"


def test_load_reviews_skips_records_without_text(db_conn, tmp_path):
    source = tmp_path / "reviews.json"
    source.write_text(
        json.dumps(
            [
                {"product_id": "p1", "text": "Güzel"},
                {"product_id": "p1", "text": "   "},
                {"product_id": "p1"},
            ]
        ),
        encoding="utf-8",
    )

    inserted = load_reviews(db_conn, source)

    assert inserted == 1
