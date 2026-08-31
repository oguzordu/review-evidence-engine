import json

from review_evidence.demo import any_for_product, load_demo_qa, lookup

SAMPLE = {
    "generated_at": "2026-08-31",
    "model": "x",
    "items": [
        {"product_id": "p1", "question": "ürün kaliteli mi", "answer": {"relevant_count": 5}},
        {"product_id": "p1", "question": "kargo hızlı mı", "answer": {"relevant_count": 2}},
    ],
}


def test_load_indexes_by_product_and_normalized_question(tmp_path):
    f = tmp_path / "demo_qa.json"
    f.write_text(json.dumps(SAMPLE), encoding="utf-8")

    qa = load_demo_qa(f)

    assert set(qa["p1"]) == {"ürün kaliteli mi", "kargo hızlı mı"}


def test_load_missing_file_returns_empty():
    assert load_demo_qa("yok/byle/dosya.json") == {}


def test_lookup_matches_via_normalize(tmp_path):
    f = tmp_path / "demo_qa.json"
    f.write_text(json.dumps(SAMPLE), encoding="utf-8")
    qa = load_demo_qa(f)

    assert lookup(qa, "p1", "  ÜRÜN   Kaliteli  mi ") == {"relevant_count": 5}
    assert lookup(qa, "p1", "alakasiz soru") is None
    assert lookup(qa, "p9", "ürün kaliteli mi") is None


def test_any_for_product_returns_some_answer(tmp_path):
    f = tmp_path / "demo_qa.json"
    f.write_text(json.dumps(SAMPLE), encoding="utf-8")
    qa = load_demo_qa(f)

    assert any_for_product(qa, "p1") in ({"relevant_count": 5}, {"relevant_count": 2})
    assert any_for_product(qa, "p9") is None
