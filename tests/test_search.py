from review_evidence.search import keyword_search


def _seed(conn, rows):
    with conn.cursor() as cur:
        for product_id, text in rows:
            cur.execute(
                "INSERT INTO reviews (product_id, raw_text, clean_text)"
                " VALUES (%s, %s, %s)",
                (product_id, text, text.lower()),
            )
    conn.commit()


def test_keyword_search_finds_matching_word(db_conn):
    _seed(
        db_conn,
        [
            ("p1", "pil cok iyi dayaniyor"),
            ("p1", "kargo hizli geldi"),
        ],
    )

    results = keyword_search(db_conn, "p1", "pil")

    assert len(results) == 1
    assert "pil" in results[0]["raw_text"]


def test_keyword_search_scopes_to_product(db_conn):
    _seed(
        db_conn,
        [
            ("p1", "pil cok iyi"),
            ("p2", "pil cok kotu"),
        ],
    )

    results = keyword_search(db_conn, "p1", "pil")

    assert len(results) == 1
    assert "iyi" in results[0]["raw_text"]


def test_keyword_search_returns_empty_for_no_match(db_conn):
    _seed(db_conn, [("p1", "kargo hizli geldi")])

    results = keyword_search(db_conn, "p1", "pil")

    assert results == []
