"""FastAPI uygulamasi ve HTTP uc noktalari."""

from typing import Iterator

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from google import genai

from review_evidence import demo, quota
from review_evidence.config import (
    DAILY_LIVE_BUDGET,
    DATABASE_URL,
    DEMO_MODE,
    GEMINI_API_KEY,
    PER_IP_LIMIT,
)
from review_evidence.consensus import build_consensus, gemini_batch_classifier
from review_evidence.db import connect
from review_evidence.embedding import sentence_transformer_encoder

app = FastAPI(title="Review Evidence Engine")

_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

try:
    _encode = sentence_transformer_encoder()
except Exception as exc:  # model yok / indirilemedi -> arama keyword-only calisir
    print(f"[main] embedding modeli yuklenemedi, arama keyword-only: {exc}")
    _encode = None

_demo_qa = demo.load_demo_qa()


def get_conn() -> Iterator[psycopg.Connection]:
    """Her istek icin bir veritabani baglantisi acar ve sonunda kapatir."""
    conn = connect(DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """Basit web arayuzunu servis eder."""
    return FileResponse("static/index.html")


@app.get("/health")
def health() -> dict[str, str]:
    """Servisin ayakta olup olmadigini bildirir."""
    return {"status": "ok"}


@app.get("/products/{product_id}/reviews")
def list_reviews(
    product_id: str,
    limit: int = 50,
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    """Bir urune ait yorumlari listeler."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, raw_text, created_at FROM reviews"
            " WHERE product_id = %s ORDER BY id LIMIT %s",
            (product_id, limit),
        )
        rows = cur.fetchall()

    return {
        "product_id": product_id,
        "count": len(rows),
        "reviews": rows,
    }


@app.get("/products/{product_id}/ask")
def ask(
    product_id: str,
    question: str,
    request: Request,
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    """Bir urun hakkinda soru sorar; ilgili yorumlarin tamamini sayarak cevaplar.

    DEMO_MODE'da once onceden hesaplanmis cevaba bakar, sonra gunluk paylasilan
    canli butceyi ve IP limitini kontrol eder. DEMO_MODE kapaliyken (lokal)
    davranis degismez -- her soru canli calisir.
    """

    def live() -> dict:
        classify_batch = gemini_batch_classifier(_client)
        result = build_consensus(
            conn, product_id, question, classify_batch, encode=_encode
        )
        return {**result, "source": "live"}

    if not DEMO_MODE:
        if _client is None:
            raise HTTPException(status_code=503, detail="GEMINI_API_KEY tanimli degil")
        return live()

    hit = demo.lookup(_demo_qa, product_id, question)
    if hit is not None:
        return {**hit, "source": "precomputed"}

    sample = demo.any_for_product(_demo_qa, product_id) or {}
    if _client is None:
        return {**sample, "source": "no_api_key"}

    client_ip = (
        (request.headers.get("x-forwarded-for") or (request.client and request.client.host) or "?")
        .split(",")[0]
        .strip()
    )
    verdict = quota.check_live_quota(
        conn, client_ip, daily_budget=DAILY_LIVE_BUDGET, per_ip_limit=PER_IP_LIMIT
    )
    if verdict != "ok":
        return {**sample, "source": verdict}

    return live()
