"""Prod demo modu icin onceden hesaplanmis soru-cevaplari uretir.

Kuratorlu soru listesini gercek yuklu veriye karsi calistirir, sonucu
data/demo_qa.json'a yazar. Lokalde BIR KEZ calistirilir; her soru ~1 Gemini
cagrisi yakar (gunluk ucretsiz kota ~20). Cikti commit'lenir.
"""

import json
from datetime import date
from pathlib import Path

from google import genai

from review_evidence.config import DATABASE_URL, GEMINI_API_KEY
from review_evidence.consensus import build_consensus, gemini_batch_classifier
from review_evidence.db import connect, init_schema
from review_evidence.embedding import sentence_transformer_encoder

MODEL_NAME = "gemini-flash-lite-latest"
OUTPUT = Path("data/demo_qa.json")

QUESTIONS = {
    "p1": ["ürün kaliteli mi", "kargo hızlı geldi mi"],
    "p2": ["ürün beklentiyi karşılıyor mu", "tavsiye edilir mi"],
    "p3": ["ürün dayanıklı mı", "malzeme kalitesi nasıl"],
    "p4": ["ürün açıklamaya uygun mu", "sorun yaşayan var mı"],
    "p5": ["ürün işe yarıyor mu", "geri iade eden var mı"],
}


def main() -> None:
    if not GEMINI_API_KEY:
        raise SystemExit("GEMINI_API_KEY yok (.env)")
    conn = connect(DATABASE_URL)
    init_schema(conn)
    encode = sentence_transformer_encoder()
    client = genai.Client(api_key=GEMINI_API_KEY)

    n = sum(len(v) for v in QUESTIONS.values())
    print(f"{n} soru islenecek (~{n} Gemini cagrisi). Gunluk kota ~20.")
    input("Devam icin Enter, iptal icin Ctrl+C... ")

    items = []
    for pid, questions in QUESTIONS.items():
        for q in questions:
            print(f"  [{pid}] {q}")
            ans = build_consensus(
                conn, pid, q, gemini_batch_classifier(client, MODEL_NAME), encode
            )
            items.append({"product_id": pid, "question": q, "answer": ans})

    OUTPUT.write_text(
        json.dumps(
            {
                "generated_at": date.today().isoformat(),
                "model": MODEL_NAME,
                "items": items,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"--> {OUTPUT} ({len(items)} kayit)")


if __name__ == "__main__":
    main()
