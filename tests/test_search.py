from review_evidence.db import connect, init_schema
from review_evidence.search import keyword_search


def _seed(conn, rows):
    for product_id, text in rows:
        conn.execute(
            "INSERT INTO reviews (product_id, raw_text, clean_text)"
            " VALUES (?, ?, ?)",
            (product_id, text, text.lower()),
        )
    conn.commit()


def test_keyword_search_finds_matching_word(tmp_path):
    conn = connect(tmp_path / "test.db")
    init_schema(conn)
    _seed(
        conn,
        [
            ("p1", "pil cok iyi dayaniyor"),
            ("p1", "kargo hizli geldi"),
        ],
    )

    results = keyword_search(conn, "p1", "pil")

    assert len(results) == 1
    assert "pil" in results[0]["raw_text"]


def test_keyword_search_scopes_to_product(tmp_path):
    conn = connect(tmp_path / "test.db")
    init_schema(conn)
    _seed(
        conn,
        [
            ("p1", "pil cok iyi"),
            ("p2", "pil cok kotu"),
        ],
    )

    results = keyword_search(conn, "p1", "pil")

    assert len(results) == 1
    assert "iyi" in results[0]["raw_text"]


def test_keyword_search_returns_empty_for_no_match(tmp_path):
    conn = connect(tmp_path / "test.db")
    init_schema(conn)
    _seed(conn, [("p1", "kargo hizli geldi")])

    results = keyword_search(conn, "p1", "pil")

    assert results == []
