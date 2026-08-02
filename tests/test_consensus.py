from review_evidence.consensus import _normalize_sentiment, build_consensus
from review_evidence.db import connect, init_schema


def test_normalize_sentiment_accepts_turkish_and_english():
    assert _normalize_sentiment("positive") == "positive"
    assert _normalize_sentiment("olumlu") == "positive"
    assert _normalize_sentiment("negative") == "negative"
    assert _normalize_sentiment("olumsuz") == "negative"
    assert _normalize_sentiment("belirsiz") == "unclear"
    assert _normalize_sentiment("garip_bir_deger") == "unclear"
    assert _normalize_sentiment("Olumlu") == "positive"


def _seed(conn, rows):
    for product_id, text in rows:
        conn.execute(
            "INSERT INTO reviews (product_id, raw_text, clean_text)"
            " VALUES (?, ?, ?)",
            (product_id, text, text.lower()),
        )
    conn.commit()


def _fake_batch_classifier(mapping):
    def classify_batch(question, review_texts):
        return [
            mapping.get(text, {"relevant": False, "sentiment": "unclear"})
            for text in review_texts
        ]

    return classify_batch


def test_build_consensus_counts_all_relevant_reviews(tmp_path):
    conn = connect(tmp_path / "test.db")
    init_schema(conn)
    _seed(
        conn,
        [
            ("p1", "pil cok iyi dayaniyor"),
            ("p1", "pil hemen bitiyor"),
            ("p1", "kargo hizli geldi"),
        ],
    )
    classify_batch = _fake_batch_classifier(
        {
            "pil cok iyi dayaniyor": {"relevant": True, "sentiment": "positive"},
            "pil hemen bitiyor": {"relevant": True, "sentiment": "negative"},
        }
    )

    result = build_consensus(conn, "p1", "pil", classify_batch)

    assert result["relevant_count"] == 2
    assert result["positive_count"] == 1
    assert result["negative_count"] == 1
    assert result["conflict"] is True


def test_build_consensus_no_conflict_when_unanimous(tmp_path):
    conn = connect(tmp_path / "test.db")
    init_schema(conn)
    _seed(conn, [("p1", "pil cok iyi")])
    classify_batch = _fake_batch_classifier(
        {"pil cok iyi": {"relevant": True, "sentiment": "positive"}}
    )

    result = build_consensus(conn, "p1", "pil", classify_batch)

    assert result["conflict"] is False
    assert result["positive_count"] == 1


def test_build_consensus_includes_citations(tmp_path):
    conn = connect(tmp_path / "test.db")
    init_schema(conn)
    _seed(conn, [("p1", "pil cok iyi")])
    classify_batch = _fake_batch_classifier(
        {"pil cok iyi": {"relevant": True, "sentiment": "positive"}}
    )

    result = build_consensus(conn, "p1", "pil", classify_batch)

    assert len(result["citations"]) == 1
    assert result["citations"][0]["text"] == "pil cok iyi"


def test_build_consensus_chunks_large_candidate_sets(tmp_path):
    conn = connect(tmp_path / "test.db")
    init_schema(conn)
    _seed(conn, [("p1", f"pil yorumu {i}") for i in range(45)])
    calls = []

    def counting_classify_batch(question, review_texts):
        calls.append(len(review_texts))
        return [{"relevant": True, "sentiment": "positive"} for _ in review_texts]

    result = build_consensus(conn, "p1", "pil", counting_classify_batch)

    assert result["relevant_count"] == 45
    assert calls == [20, 20, 5]
