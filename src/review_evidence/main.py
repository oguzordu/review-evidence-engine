"""FastAPI uygulamasi ve HTTP uc noktalari."""

from typing import Iterator

import psycopg
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from google import genai

from review_evidence.config import DATABASE_URL, GEMINI_API_KEY
from review_evidence.consensus import build_consensus, gemini_batch_classifier
from review_evidence.db import connect

app = FastAPI(title="Review Evidence Engine")

_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


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
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    """Bir urun hakkinda soru sorar; ilgili yorumlarin tamamini sayarak cevaplar."""
    if _client is None:
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY tanimli degil")

    classify_batch = gemini_batch_classifier(_client)
    return build_consensus(conn, product_id, question, classify_batch)
