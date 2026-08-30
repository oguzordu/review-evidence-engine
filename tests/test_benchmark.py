import json as _json
from pathlib import Path

from review_evidence.benchmark import (
    baseline_rag,
    format_report,
    ground_truth,
    run_case,
)


def _case(reviews):
    return {"product_id": "bench_x", "question": "pil nasil", "reviews": reviews}


def _seed(conn, rows):
    with conn.cursor() as cur:
        for product_id, text in rows:
            cur.execute(
                "INSERT INTO reviews (product_id, raw_text, clean_text)"
                " VALUES (%s, %s, %s)",
                (product_id, text, text.lower()),
            )
    conn.commit()


def test_ground_truth_sums_only_relevant_labels():
    case = _case(
        [
            {"text": "a", "relevant": True, "sentiment": "negative"},
            {"text": "b", "relevant": True, "sentiment": "negative"},
            {"text": "c", "relevant": True, "sentiment": "positive"},
            {"text": "d", "relevant": False, "sentiment": "positive"},
            {"text": "e", "relevant": True, "sentiment": "unclear"},
        ]
    )

    gt = ground_truth(case)

    assert gt == {"relevant": 4, "positive": 1, "negative": 2, "unclear": 1}


def test_baseline_rag_only_sees_k_reviews(db_conn):
    _seed(db_conn, [("bench_x", f"pil kotu dayanmiyor {i}") for i in range(30)])

    def fake_count_summary(question, texts):
        return {"positive": 0, "negative": len(texts), "unclear": 0}

    result = baseline_rag(db_conn, "bench_x", "pil nasil", fake_count_summary, k=8)

    assert result["reviews_seen"] == 8
    assert result["negative_count"] == 8
    assert result["error"] is False


def test_baseline_rag_marks_error_when_summary_raises(db_conn):
    _seed(db_conn, [("bench_x", "pil kotu")])

    def broken_summary(question, texts):
        raise RuntimeError("api patladi")

    result = baseline_rag(db_conn, "bench_x", "pil", broken_summary, k=8)

    assert result["error"] is True
    assert result["positive_count"] == 0


def test_run_case_computes_errors():
    case = _case(
        [{"text": f"n{i}", "relevant": True, "sentiment": "negative"} for i in range(20)]
        + [{"text": f"p{i}", "relevant": True, "sentiment": "positive"} for i in range(8)]
    )

    def perfect_our_method():
        return {"relevant_count": 28, "positive_count": 8, "negative_count": 20}

    def weak_baseline():
        return {"reviews_seen": 8, "positive_count": 3, "negative_count": 5}

    result = run_case(None, case, perfect_our_method, weak_baseline)

    assert result["ground_truth"] == {
        "relevant": 28,
        "positive": 8,
        "negative": 20,
        "unclear": 0,
    }
    assert result["ours"]["abs_error_positive"] == 0
    assert result["ours"]["abs_error_negative"] == 0
    assert result["baseline"]["abs_error_negative"] == 15
    assert result["baseline"]["missed_relevant"] == 20


def test_format_report_contains_key_numbers():
    case = _case([{"text": "n", "relevant": True, "sentiment": "negative"}])
    result = run_case(
        None,
        case,
        lambda: {"relevant_count": 1, "positive_count": 0, "negative_count": 1},
        lambda: {"reviews_seen": 1, "positive_count": 0, "negative_count": 0},
    )

    report = format_report([result], model_name="test-model", k=8)

    assert "test-model" in report
    assert "|" in report
    assert "pil nasil" in report


def test_benchmark_fixture_is_valid():
    data = _json.loads(Path("data/benchmark.json").read_text(encoding="utf-8"))

    assert isinstance(data["cases"], list) and len(data["cases"]) >= 2
    for case in data["cases"]:
        assert case["product_id"].startswith("bench_")
        assert isinstance(case["question"], str) and case["question"]
        assert len(case["reviews"]) >= 25
        gt = ground_truth(case)
        assert gt["relevant"] > 8
        assert gt["negative"] > 0 and gt["positive"] > 0
        for r in case["reviews"]:
            assert set(r) == {"text", "relevant", "sentiment"}
            assert isinstance(r["relevant"], bool)
            assert r["sentiment"] in {"positive", "negative", "unclear"}
