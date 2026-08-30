import pytest

from review_evidence.search import _rrf_fuse, keyword_search


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


def test_rrf_fuse_ranks_items_appearing_in_both_lists_higher():
    list_a = [{"id": 1}, {"id": 2}, {"id": 3}]
    list_b = [{"id": 3}, {"id": 2}, {"id": 9}]

    fused = _rrf_fuse([list_a, list_b])

    top_two = {row["id"] for row in fused[:2]}
    assert top_two == {2, 3}
    assert {row["id"] for row in fused} == {1, 2, 3, 9}


def test_rrf_fuse_handles_empty_list():
    only = [{"id": 5}, {"id": 6}]

    fused = _rrf_fuse([only, []])

    assert [row["id"] for row in fused] == [5, 6]


def test_rrf_fuse_preserves_first_seen_row_payload():
    fused = _rrf_fuse([[{"id": 1, "raw_text": "a"}], [{"id": 1, "raw_text": "b"}]])

    assert fused[0]["raw_text"] == "a"


def test_keyword_search_orders_by_relevance(db_conn):
    rows = [("p1", f"pil dayanikli urun {i}") for i in range(30)]
    rows.append(("p1", "pil pil pil cok kotu hemen bitiyor"))
    _seed(db_conn, rows)

    results = keyword_search(db_conn, "p1", "pil kotu", limit=5)

    assert "kotu" in results[0]["raw_text"]
