"""Turkish product reviews veri setinden ornek cekip sentetik urunlere boler.

Kaynak veri setinde urun ayrimi yok (sadece sentence+sentiment var), bu yuzden
duz yorumlari N sentetik urun grubuna (p1..pN) boluyoruz. Bu bilinen ve
belgelenen bir muhendislik karari -- gercek urun meta verisi yok.
"""

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

import httpx

DATASET = "fthbrmnby/turkish_product_reviews"
TOTAL_ROWS = 1000
PRODUCT_COUNT = 5
OUTPUT = Path(__file__).resolve().parent.parent / "data" / "sample_reviews.json"

random.seed(42)


def fetch_rows(total: int) -> list[dict]:
    rows = []
    page_size = 100
    with httpx.Client(timeout=30) as client:
        for offset in range(0, total, page_size):
            resp = client.get(
                "https://datasets-server.huggingface.co/rows",
                params={
                    "dataset": DATASET,
                    "config": "default",
                    "split": "train",
                    "offset": offset,
                    "length": page_size,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            rows.extend(r["row"] for r in data["rows"])
    return rows[:total]


def synthesize_date(base: datetime, i: int, n: int) -> str:
    days_back = int((n - i) / n * 180)
    return (base - timedelta(days=days_back)).strftime("%Y-%m-%d")


def main() -> None:
    raw_rows = fetch_rows(TOTAL_ROWS)
    per_product = len(raw_rows) // PRODUCT_COUNT
    base = datetime(2026, 7, 30)

    records = []
    for idx, row in enumerate(raw_rows):
        product_id = f"p{(idx // per_product) + 1}"
        if product_id > f"p{PRODUCT_COUNT}":
            product_id = f"p{PRODUCT_COUNT}"
        records.append(
            {
                "product_id": product_id,
                "text": row["sentence"],
                "created_at": synthesize_date(base, idx % per_product, per_product),
            }
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(records)} yorum yazildi -> {OUTPUT}")


if __name__ == "__main__":
    main()
