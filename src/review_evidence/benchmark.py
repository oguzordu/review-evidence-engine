"""Sayim-tabanli yontem ile klasik RAG baseline'ini kontrollu bir set
uzerinde karsilastiran olcum harness'i.

Ground truth elle etiketlenmis fixture'dan (data/benchmark.json) gelir.
Baseline, bizim yontemle AYNI hibrit aramayi kullanir; tek fark top-K kesme
ve tek LLM cagrisiyla ozetleme. Enjekte edilebilir siniflandirici deseni
consensus.py ile ayni.
"""

import json
import time
from collections import Counter
from datetime import date
from typing import Callable, TypedDict

import psycopg

from review_evidence.consensus import MAX_RETRIES, RETRY_DELAY_SECONDS
from review_evidence.embedding import EncoderFn
from review_evidence.search import hybrid_search


class LabeledReview(TypedDict):
    text: str
    relevant: bool
    sentiment: str  # "positive" | "negative" | "unclear"


class Case(TypedDict):
    product_id: str
    question: str
    reviews: list[LabeledReview]


SummaryCounterFn = Callable[[str, list[str]], dict]
# (question, review_texts) -> {"positive": int, "negative": int, "unclear": int}


def ground_truth(case: Case) -> dict:
    """Fixture etiketlerinden gercek sayilari cikarir. Yalnizca relevant=True
    yorumlar, sentiment'lerine gore sayilir."""
    counts = Counter(r["sentiment"] for r in case["reviews"] if r["relevant"])
    return {
        "relevant": sum(counts.values()),
        "positive": counts.get("positive", 0),
        "negative": counts.get("negative", 0),
        "unclear": counts.get("unclear", 0),
    }


def gemini_summary_counter(
    client, model_name: str = "gemini-flash-lite-latest"
) -> SummaryCounterFn:
    """Klasik RAG baseline'i: verilen yorumlari TEK LLM cagrisiyla ozetleyip
    olumlu/olumsuz/belirsiz sayilarini dondurur. 429'da retry."""

    def count_summary(question: str, review_texts: list[str]) -> dict:
        if not review_texts:
            return {"positive": 0, "negative": 0, "unclear": 0}

        numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(review_texts))
        prompt = (
            "Soru: " + question + "\n\n"
            "Asagida bir urunun yorumlari var. Soruyla ilgili olanlardan kac "
            "tanesi olumlu, kac tanesi olumsuz, kac tanesi belirsiz?\n\n"
            + numbered
            + '\n\nSADECE su JSON: {"positive": 0, "negative": 0, "unclear": 0}'
        )

        for attempt in range(MAX_RETRIES):
            try:
                response = client.models.generate_content(
                    model=model_name, contents=prompt
                )
                text = (response.text or "").strip()
                text = (
                    text.removeprefix("```json")
                    .removeprefix("```")
                    .removesuffix("```")
                    .strip()
                )
                data = json.loads(text)
                return {
                    "positive": int(data.get("positive", 0)),
                    "negative": int(data.get("negative", 0)),
                    "unclear": int(data.get("unclear", 0)),
                }
            except Exception as exc:
                is_rate_limit = "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc)
                if is_rate_limit and attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY_SECONDS)
                    continue
                break

        return {"positive": 0, "negative": 0, "unclear": 0}

    return count_summary


def baseline_rag(
    conn: psycopg.Connection,
    product_id: str,
    question: str,
    count_summary: SummaryCounterFn,
    encode: EncoderFn | None = None,
    k: int = 8,
) -> dict:
    """Klasik RAG: bizim yontemle AYNI hibrit aramadan top-K aday, tek LLM
    cagrisiyla ozetle+say. reviews_seen K ile sinirli -- ilgili yorum sayisi
    K'dan fazlaysa gerisini goremiyor."""
    candidates = hybrid_search(conn, product_id, question, encode, limit=k)
    texts = [row["raw_text"] for row in candidates]

    try:
        counts = count_summary(question, texts)
        error = counts == {"positive": 0, "negative": 0, "unclear": 0} and bool(texts)
    except Exception:
        counts = {"positive": 0, "negative": 0, "unclear": 0}
        error = True

    return {
        "method": "baseline_rag",
        "reviews_seen": len(texts),
        "positive_count": counts["positive"],
        "negative_count": counts["negative"],
        "unclear_count": counts["unclear"],
        "error": error,
    }


def run_case(
    conn,
    case: Case,
    our_method: Callable[[], dict],
    baseline_method: Callable[[], dict],
) -> dict:
    """Bir vaka icin iki yontemi de calistirir, ground truth'a gore hatalari
    hesaplar. our_method / baseline_method: () -> sayim sozlugu."""
    gt = ground_truth(case)
    ours = our_method()
    base = baseline_method()

    return {
        "question": case["question"],
        "product_id": case["product_id"],
        "ground_truth": gt,
        "ours": {
            "relevant_count": ours.get("relevant_count", 0),
            "positive_count": ours["positive_count"],
            "negative_count": ours["negative_count"],
            "abs_error_positive": abs(ours["positive_count"] - gt["positive"]),
            "abs_error_negative": abs(ours["negative_count"] - gt["negative"]),
        },
        "baseline": {
            "reviews_seen": base.get("reviews_seen", 0),
            "positive_count": base["positive_count"],
            "negative_count": base["negative_count"],
            "abs_error_positive": abs(base["positive_count"] - gt["positive"]),
            "abs_error_negative": abs(base["negative_count"] - gt["negative"]),
            "missed_relevant": max(0, gt["relevant"] - base.get("reviews_seen", 0)),
        },
        "error": bool(base.get("error", False)),
    }


def format_report(results: list[dict], *, model_name: str, k: int) -> str:
    """Karsilastirma tablosunu Markdown olarak uretir."""
    lines = [
        "# Baseline Karşılaştırma Ölçümü",
        "",
        f"> Ölçüm tarihi: {date.today().isoformat()} · "
        f"Model: `{model_name}` · Baseline K: {k}",
        "",
        "| Soru | Ground truth (ilgili/olumlu/olumsuz) | "
        "Bizim yöntem (olumlu/olumsuz, ±hata) | "
        "Baseline (gördüğü/olumlu/olumsuz, kaçırılan ilgili) |",
        "|---|---|---|---|",
    ]
    for r in results:
        gt, ours, base = r["ground_truth"], r["ours"], r["baseline"]
        flag = " ⚠️" if r["error"] else ""
        lines.append(
            f"| {r['question']}{flag} "
            f"| {gt['relevant']}/{gt['positive']}/{gt['negative']} "
            f"| {ours['positive_count']}/{ours['negative_count']} "
            f"(±{ours['abs_error_positive']}/±{ours['abs_error_negative']}) "
            f"| {base['reviews_seen']}/{base['positive_count']}/{base['negative_count']} "
            f"({base['missed_relevant']} kaçtı) |"
        )
    lines += ["", "## Yorum", ""]
    for r in results:
        base = r["baseline"]
        lines.append(
            f"- **{r['question']}**: baseline yalnızca {base['reviews_seen']} "
            f"yorum gördü, {base['missed_relevant']} ilgili yorumu hiç "
            f"değerlendirmedi; olumsuz sayısını {base['abs_error_negative']} "
            f"birim yanlış raporladı."
        )
    if any(r["error"] for r in results):
        lines += ["", "⚠️ = baseline LLM çağrısı başarısız (kota/hata)."]
    return "\n".join(lines) + "\n"
