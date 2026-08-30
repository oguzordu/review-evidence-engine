from review_evidence.config import DATABASE_URL
from review_evidence.db import connect, init_schema


def test_init_schema_creates_reviews_table():
    conn = connect(DATABASE_URL)
    init_schema(conn)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables"
            " WHERE table_name = 'reviews'"
        )
        tables = cur.fetchall()

    assert len(tables) == 1
    conn.close()


def test_init_schema_is_idempotent():
    conn = connect(DATABASE_URL)
    init_schema(conn)
    init_schema(conn)  # ikinci kez calistirmak hata vermemeli

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM reviews")
        count = cur.fetchone()

    assert count["n"] >= 0
    conn.close()


def test_connection_returns_rows_by_column_name(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO reviews (product_id, raw_text, clean_text)"
            " VALUES (%s, %s, %s)",
            ("p1", "Ürün güzel", "ürün güzel"),
        )
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT product_id FROM reviews")
        row = cur.fetchone()

    assert row["product_id"] == "p1"
