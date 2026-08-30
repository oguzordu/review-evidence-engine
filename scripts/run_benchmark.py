"""Sayim-tabanli yontem ile klasik RAG baseline'ini olcer.

data/benchmark.json'daki etiketli vakalari yukler, iki yontemi de calistirir,
sonucu docs/benchmark-results.md'ye yazar.

Kullanim:
    python scripts/run_benchmark.py

DIKKAT: vaka basina ~3-4 Gemini cagrisi yakar (toplam ~8). Gunluk ucretsiz
kota 20.
"""

import json
from pathlib import Path

from google import genai

from review_evidence.benchmark import (
    baseline_rag,
    format_report,
    gemini_summary_counter,
    run_case,
)
from review_evidence.config import DATABASE_URL, GEMINI_API_KEY
from review_evidence.consensus import build_consensus, gemini_batch_classifier
from review_evidence.db import connect, init_schema
from review_evidence.embedding import sentence_transformer_encoder
from review_evidence.text import normalize

MODEL_NAME = "gemini-flash-lite-latest"
K = 8
FIXTURE = Path("data/benchmark.json")
OUTPUT = Path("docs/benchmark-results.md")


def _load_case(conn, case, encode) -> None:
    pid = case["product_id"]
    with conn.cursor() as cur:
        cur.execute("DELETE FROM reviews WHERE product_id = %s", (pid,))
    conn.commit()
    texts = [r["text"] for r in case["reviews"]]
    embeddings = encode(texts)
    rows = [
        (pid, r["text"], normalize(r["text"]), None, emb)
        for r, emb in zip(case["reviews"], embeddings)
    ]
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO reviews (product_id, raw_text, clean_text, created_at, embedding)"
            " VALUES (%s, %s, %s, %s, %s)",
            rows,
        )
    conn.commit()


def main() -> None:
    if not GEMINI_API_KEY:
        raise SystemExit("GEMINI_API_KEY tanimli degil (.env)")

    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
    print(
        f"{len(cases)} vaka calistirilacak. Vaka basina ~3-4 Gemini cagrisi "
        f"(~{len(cases) * 4} toplam). Gunluk kota 20."
    )
    input("Devam etmek icin Enter, iptal icin Ctrl+C... ")

    conn = connect(DATABASE_URL)
    init_schema(conn)
    encode = sentence_transformer_encoder()
    client = genai.Client(api_key=GEMINI_API_KEY)

    results = []
    for case in cases:
        pid, q = case["product_id"], case["question"]
        print(f"\n[{pid}] {q}")
        _load_case(conn, case, encode)

        def our_method(_pid=pid, _q=q):
            return build_consensus(
                conn, _pid, _q, gemini_batch_classifier(client, MODEL_NAME), encode
            )

        def baseline_method(_pid=pid, _q=q):
            return baseline_rag(
                conn, _pid, _q, gemini_summary_counter(client, MODEL_NAME), encode, k=K
            )

        result = run_case(conn, case, our_method, baseline_method)
        results.append(result)
        print(
            f"  ground truth: {result['ground_truth']}\n"
            f"  bizim: +{result['ours']['positive_count']} "
            f"-{result['ours']['negative_count']}\n"
            f"  baseline: +{result['baseline']['positive_count']} "
            f"-{result['baseline']['negative_count']} "
            f"({result['baseline']['missed_relevant']} kacti)"
        )

    with conn.cursor() as cur:
        for case in cases:
            cur.execute(
                "DELETE FROM reviews WHERE product_id = %s", (case["product_id"],)
            )
    conn.commit()
    conn.close()

    report = format_report(results, model_name=MODEL_NAME, k=K)
    OUTPUT.write_text(report, encoding="utf-8")
    print(f"\n{report}\n--> {OUTPUT}")


if __name__ == "__main__":
    main()
