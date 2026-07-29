from review_evidence.db import connect, init_schema


def test_init_schema_creates_reviews_table(tmp_path):
    conn = connect(tmp_path / "test.db")
    init_schema(conn)

    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()

    assert "reviews" in [row["name"] for row in tables]


def test_init_schema_is_idempotent(tmp_path):
    conn = connect(tmp_path / "test.db")
    init_schema(conn)
    init_schema(conn)  # ikinci kez calistirmak hata vermemeli

    count = conn.execute("SELECT COUNT(*) AS n FROM reviews").fetchone()
    assert count["n"] == 0


def test_connection_returns_rows_by_column_name(tmp_path):
    conn = connect(tmp_path / "test.db")
    init_schema(conn)
    conn.execute(
        "INSERT INTO reviews (product_id, raw_text, clean_text)"
        " VALUES ('p1', 'Ürün güzel', 'ürün güzel')"
    )

    row = conn.execute("SELECT product_id FROM reviews").fetchone()

    assert row["product_id"] == "p1"