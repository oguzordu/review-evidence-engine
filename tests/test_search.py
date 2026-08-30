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


def _seed_with_embeddings(conn, rows):
    """rows: (product_id, text, embedding_list) uclulleri."""
    with conn.cursor() as cur:
        for product_id, text, emb in rows:
            cur.execute(
                "INSERT INTO reviews (product_id, raw_text, clean_text, embedding)"
                " VALUES (%s, %s, %s, %s)",
                (product_id, text, text.lower(), emb),
            )
    conn.commit()


def _vec(*first):
    """Ilk birkac boyutu verilen, kalani 0 olan 384-boyutlu vektor."""
    return list(first) + [0.0] * (384 - len(first))


def test_vector_search_orders_by_cosine_distance(db_conn):
    from review_evidence.search import vector_search

    _seed_with_embeddings(
        db_conn,
        [
            ("p1", "yakin", _vec(1.0, 0.0)),
            ("p1", "orta", _vec(0.7, 0.7)),
            ("p1", "uzak", _vec(0.0, 1.0)),
        ],
    )

    results = vector_search(db_conn, "p1", _vec(1.0, 0.0), limit=3)

    assert [r["raw_text"] for r in results] == ["yakin", "orta", "uzak"]


def test_vector_search_excludes_null_embeddings(db_conn):
    from review_evidence.search import vector_search

    _seed(db_conn, [("p1", "embedding yok")])
    _seed_with_embeddings(db_conn, [("p1", "embedding var", _vec(1.0))])

    results = vector_search(db_conn, "p1", _vec(1.0), limit=10)

    assert [r["raw_text"] for r in results] == ["embedding var"]


def test_hybrid_search_without_encoder_is_keyword_only(db_conn):
    from review_evidence.search import hybrid_search

    _seed(db_conn, [("p1", "pil kotu"), ("p1", "kargo hizli")])

    results = hybrid_search(db_conn, "p1", "pil", encode=None)

    assert [r["raw_text"] for r in results] == ["pil kotu"]


def test_hybrid_search_surfaces_semantic_match_keyword_misses(db_conn):
    from review_evidence.search import hybrid_search

    _seed_with_embeddings(
        db_conn,
        [
            ("p1", "urun berbat cikti", _vec(1.0, 0.0)),
            ("p1", "kargo suresi uzun", _vec(0.0, 1.0)),
        ],
    )
    _seed(db_conn, [("p1", "urun kotu geldi")])

    def fake_encode(texts):
        return [_vec(1.0, 0.0) for _ in texts]

    results = hybrid_search(db_conn, "p1", "urun kotu", encode=fake_encode)
    texts = [r["raw_text"] for r in results]

    assert "urun berbat cikti" in texts
    assert "urun kotu geldi" in texts


def test_hybrid_search_respects_limit(db_conn):
    from review_evidence.search import hybrid_search

    _seed(db_conn, [("p1", f"pil yorum {i}") for i in range(10)])

    results = hybrid_search(db_conn, "p1", "pil", encode=None, limit=3)

    assert len(results) == 3


@pytest.mark.slow
def test_hybrid_search_real_model_ranks_negative_for_negative_query(db_conn):
    from review_evidence.embedding import sentence_transformer_encoder
    from review_evidence.search import hybrid_search

    encode = sentence_transformer_encoder()
    texts = [
        "urun berbat, paramin hakkini vermedi",
        "urun harika, cok memnunum",
        "kargo hizli geldi",
    ]
    vectors = encode(texts)
    with db_conn.cursor() as cur:
        for text, emb in zip(texts, vectors):
            cur.execute(
                "INSERT INTO reviews (product_id, raw_text, clean_text, embedding)"
                " VALUES (%s, %s, %s, %s)",
                ("p1", text, text.lower(), emb),
            )
    db_conn.commit()

    results = hybrid_search(db_conn, "p1", "urun kotu mu", encode=encode, limit=3)

    assert results[0]["raw_text"].startswith("urun berbat")
