"""Sayim tabanli mutabakat mantigi.

Standart RAG en benzer birkac yorumu okuyup ozet gecer; ilgili yorum sayisi
okunanlardan fazlaysa gerisini kacirir. Bu modul aday kumedeki HER yorumu
tek tek siniflandirir, sayar ve celiskiyi gizlemeden raporlar.

Performans icin yorumlar tek tek degil, gruplar halinde (batch) tek bir
LLM cagrisinda siniflandirilir.
"""

import json
import sqlite3
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, TypedDict

from review_evidence.search import keyword_search

BATCH_SIZE = 20
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 12

SENTIMENT_MAP = {
    "positive": "positive", "olumlu": "positive",
    "negative": "negative", "olumsuz": "negative",
    "unclear": "unclear", "belirsiz": "unclear",
}


def _normalize_sentiment(value: str) -> str:
    """LLM bazen Turkce (olumlu/olumsuz) bazen Ingilizce doner, tekillestirir."""
    return SENTIMENT_MAP.get(str(value).strip().lower(), "unclear")


class Classification(TypedDict):
    relevant: bool
    sentiment: str  # "positive" | "negative" | "unclear"


BatchClassifierFn = Callable[[str, list[str]], list[Classification]]


def _chunk(items: list, size: int) -> list[list]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def gemini_batch_classifier(client, model_name: str = "gemini-flash-lite-latest") -> BatchClassifierFn:
    """Verilen Gemini client'ini kullanan, birden fazla yorumu tek cagrida
    siniflandiran bir fonksiyon doner. Rate limit (429) hatasinda otomatik
    olarak birkac kez yeniden dener."""

    def classify_batch(question: str, review_texts: list[str]) -> list[Classification]:
        if not review_texts:
            return []

        numbered = "\n".join(f"{i + 1}. {text}" for i, text in enumerate(review_texts))
        example = json.dumps(
            [{"relevant": True, "sentiment": "positive"}, {"relevant": False, "sentiment": "unclear"}]
        )
        prompt = (
            "Soru: " + question + "\n\n"
            "Asagida numarali yorumlar var. Her biri icin: soruyla dogrudan "
            "ilgili mi, ilgiliyse yonu olumlu mu olumsuz mu yoksa belirsiz mi?\n\n"
            + numbered
            + "\n\nSADECE, yorum sayisi kadar elemanli bir JSON dizisi doner, "
            "sirasi yorum sirasiyla ayni olsun, baska hicbir sey yazma:\n"
            + example
        )

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                response = client.models.generate_content(model=model_name, contents=prompt)
                text = (response.text or "").strip()
                text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                data = json.loads(text)
                results = []
                for i in range(len(review_texts)):
                    if i < len(data) and isinstance(data[i], dict):
                        results.append(
                            {
                                "relevant": bool(data[i].get("relevant", False)),
                                "sentiment": _normalize_sentiment(data[i].get("sentiment", "unclear")),
                            }
                        )
                    else:
                        results.append({"relevant": False, "sentiment": "unclear"})
                return results
            except Exception as exc:
                last_error = exc
                is_rate_limit = "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc)
                if is_rate_limit and attempt < MAX_RETRIES - 1:
                    print(
                        f"[consensus] rate limit, {RETRY_DELAY_SECONDS}s bekleyip "
                        f"tekrar deneniyor (deneme {attempt + 1}/{MAX_RETRIES})"
                    )
                    time.sleep(RETRY_DELAY_SECONDS)
                    continue
                break

        print(f"[consensus] siniflandirma basarisiz oldu: {last_error}")
        return [{"relevant": False, "sentiment": "unclear"} for _ in review_texts]

    return classify_batch


def build_consensus(
    conn: sqlite3.Connection,
    product_id: str,
    question: str,
    classify_batch: BatchClassifierFn,
) -> dict:
    """Bir urun+soru icin sayim tabanli mutabakat raporu uretir."""
    candidates = keyword_search(conn, product_id, question)

    batches = _chunk(candidates, BATCH_SIZE)

    def run_batch(batch):
        texts = [row["raw_text"] for row in batch]
        return list(zip(batch, classify_batch(question, texts)))

    relevant_reviews = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for batch_results in pool.map(run_batch, batches):
            for row, result in batch_results:
                if result["relevant"]:
                    relevant_reviews.append(
                        {
                            "id": row["id"],
                            "raw_text": row["raw_text"],
                            "created_at": row["created_at"],
                            "sentiment": result["sentiment"],
                        }
                    )

    counts = Counter(r["sentiment"] for r in relevant_reviews)
    positive = counts.get("positive", 0)
    negative = counts.get("negative", 0)
    unclear = counts.get("unclear", 0)

    return {
        "question": question,
        "product_id": product_id,
        "candidates_checked": len(candidates),
        "relevant_count": len(relevant_reviews),
        "positive_count": positive,
        "negative_count": negative,
        "unclear_count": unclear,
        "conflict": positive > 0 and negative > 0,
        "citations": [
            {"id": r["id"], "text": r["raw_text"], "sentiment": r["sentiment"]}
            for r in relevant_reviews
        ],
    }
