# Hibrit Arama Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/ask` akışındaki aday yorum aramasını, anahtar kelime (ts_rank) ve lokal embedding benzerliğini RRF ile birleştiren hibrit aramayla değiştirmek.

**Architecture:** Keyword kolu (`to_tsquery` OR + `ts_rank` sıralama) ve vektör kolu (`pgvector` cosine) bağımsız çalışır, `_rrf_fuse` saf fonksiyonu id bazında Reciprocal Rank Fusion (k=60) uygular, ilk 200 satır LLM sınıflandırmasına gider. Embedding modeli lokal `sentence-transformers` (kota yok). Encoder enjekte edilebilir; model yalnızca `slow` testlerde ve çalışan uygulamada yüklenir. Model yüklenemezse sistem keyword-only'ye düşer, 503 vermez.

**Tech Stack:** Python 3.12, FastAPI, psycopg 3, PostgreSQL 16 + pgvector, sentence-transformers (MiniLM), pytest (gerçek Postgres'e karşı).

**Spec:** `docs/superpowers/specs/2026-08-31-hibrit-arama-design.md`

## Global Constraints

- Python `>=3.12`.
- Testler gerçek PostgreSQL'e bağlanır (docker compose `db` servisi); SQLite yok.
- Postgres imajı: `pgvector/pgvector:pg16` (hem local compose hem CI).
- Embedding modeli: `paraphrase-multilingual-MiniLM-L12-v2`, **384 boyut**, `normalize_embeddings=True`.
- Embedding kaynağı metin: `raw_text` (clean_text değil).
- Enjekte edilebilir bağımlılık deseni mevcut `gemini_batch_classifier` ile aynı olmalı.
- Mevcut 23 test değişmeden geçmeli (imza değişiklikleri geriye dönük uyumlu: yeni parametreler opsiyonel kwarg).
- Commit mesajları: kısa, gündelik, Türkçe, birinci şahıs, AI attribution YOK, feature-dump YOK. Örn: `hibrit arama icin rrf fonksiyonunu ekledim`.
- Modül sabitleri: `KEYWORD_K = 100`, `VECTOR_K = 100`, `CANDIDATE_LIMIT = 200`, `RRF_K = 60` (search.py).
- `venv` mevcut: komutlar `.venv\Scripts\python.exe` ile çalışır (Windows) veya `.venv/bin/python` (POSIX). Aşağıda `python` yazan yerde projenin venv'i kastedilir.

---

## Dosya Yapısı

| Dosya | Sorumluluk | İşlem |
|---|---|---|
| `pyproject.toml` | bağımlılıklar, pytest markers | Modify |
| `docker-compose.yml` | `db` servisi imajı | Modify |
| `src/review_evidence/db.py` | şema + pgvector kaydı | Modify |
| `src/review_evidence/embedding.py` | lokal encoder (enjekte edilebilir) | Create |
| `src/review_evidence/search.py` | keyword + vector + hybrid + RRF | Modify |
| `src/review_evidence/consensus.py` | `build_consensus` → hybrid_search | Modify |
| `src/review_evidence/ingest.py` | yüklerken embedding üretimi | Modify |
| `src/review_evidence/main.py` | encoder singleton + wiring | Modify |
| `scripts/backfill_embeddings.py` | mevcut satırlar için embedding | Create |
| `tests/test_db.py` | şema testleri | Modify |
| `tests/test_search.py` | rrf / vector / hybrid testleri | Modify |
| `tests/test_consensus.py` | encode entegrasyonu | Modify |
| `tests/test_ingest.py` | embedding kolonu | Modify |
| `tests/test_embedding.py` | encoder (slow) | Create |
| `.github/workflows/ci.yml` | CI | Create |
| `README.md` | CI rozeti | Modify |

---

## Task 1: Bağımlılıklar, pytest markers, pgvector imajı

**Files:**
- Modify: `pyproject.toml`
- Modify: `docker-compose.yml`

**Interfaces:**
- Consumes: yok
- Produces: `sentence-transformers`, `pgvector`, `numpy` (transitif) kurulu; `slow` pytest marker'ı; `pgvector/pgvector:pg16` çalışan DB.

- [ ] **Step 1: `pyproject.toml` bağımlılıklarını güncelle**

`[project].dependencies` listesine ekle:

```toml
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "google-genai>=1.0",
    "python-dotenv>=1.0",
    "psycopg[binary]>=3.1",
    "pgvector>=0.3",
    "sentence-transformers>=3.0",
]
```

- [ ] **Step 2: `pyproject.toml` pytest yapılandırmasını güncelle**

`[tool.pytest.ini_options]` bloğunu şu hale getir:

```toml
[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
addopts = ["-m", "not slow"]
markers = [
    "slow: gercek embedding modelini yukler; varsayilan kosuda atlanir",
]
```

- [ ] **Step 3: `docker-compose.yml` imajını değiştir**

`services.db.image` satırını değiştir:

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
```

(Diğer `db` alanları — environment, ports, volumes, healthcheck — aynı kalır.)

- [ ] **Step 4: Bağımlılıkları kur ve DB'yi ayağa kaldır**

Run:
```
docker compose down
docker compose up -d db
python -m pip install -e ".[dev]"
```
Expected: pip kurulumu `sentence-transformers`, `pgvector`, `torch`, `numpy` çeker (birkaç dakika sürebilir). `docker compose up` pgvector imajını indirip başlatır.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml docker-compose.yml
git commit -m "pgvector ve sentence-transformers bagimliliklarini ekledim"
```

---

## Task 2: Şema — vector extension, embedding kolonu, hnsw index

**Files:**
- Modify: `src/review_evidence/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: Task 1 (pgvector paketi, pgvector imajı)
- Produces: `reviews.embedding vector(384)` kolonu; `connect()` çağrısı `register_vector` uygular; `init_schema()` extension + kolon + hnsw index kurar.

- [ ] **Step 1: Failing test yaz — `tests/test_db.py` sonuna ekle**

```python
def test_init_schema_adds_embedding_column(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT data_type, udt_name FROM information_schema.columns"
            " WHERE table_name = 'reviews' AND column_name = 'embedding'"
        )
        row = cur.fetchone()

    assert row is not None
    assert row["udt_name"] == "vector"


def test_vector_roundtrips_as_python_list(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO reviews (product_id, raw_text, clean_text, embedding)"
            " VALUES (%s, %s, %s, %s)",
            ("p1", "x", "x", [0.1] * 384),
        )
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT embedding FROM reviews")
        row = cur.fetchone()

    assert len(list(row["embedding"])) == 384
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `python -m pytest tests/test_db.py -v`
Expected: yeni iki test FAIL (kolon yok / `vector` tipi tanınmıyor).

- [ ] **Step 3: `db.py` — import ve `SCHEMA`**

Dosyanın başındaki importlara ekle:

```python
from pgvector.psycopg import register_vector
```

`SCHEMA` sabitini şu hale getir:

```python
SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS reviews (
    id         SERIAL PRIMARY KEY,
    product_id TEXT NOT NULL,
    raw_text   TEXT NOT NULL,
    clean_text TEXT NOT NULL,
    created_at TEXT
);

ALTER TABLE reviews ADD COLUMN IF NOT EXISTS embedding vector(384);

CREATE INDEX IF NOT EXISTS idx_reviews_product ON reviews (product_id);

CREATE INDEX IF NOT EXISTS idx_reviews_fts
    ON reviews USING GIN (to_tsvector('turkish', clean_text));

CREATE INDEX IF NOT EXISTS idx_reviews_embedding
    ON reviews USING hnsw (embedding vector_cosine_ops);
"""
```

- [ ] **Step 4: `db.py` — `connect()` ve `init_schema()`**

```python
def connect(database_url: str) -> psycopg.Connection:
    """Veritabani baglantisi acar. Satirlar sozluk (dict) olarak okunabilir olur."""
    conn = psycopg.connect(database_url, row_factory=dict_row)
    try:
        register_vector(conn)
    except psycopg.ProgrammingError:
        # vector extension henuz kurulmamis; init_schema sonrasi tekrar denenir
        conn.rollback()
    return conn


def init_schema(conn: psycopg.Connection) -> None:
    """Tablolari, vector extension'i ve index'leri olusturur. Idempotent."""
    with conn.cursor() as cur:
        cur.execute(SCHEMA)
    conn.commit()
    register_vector(conn)
```

- [ ] **Step 5: Testlerin geçtiğini doğrula**

Run: `python -m pytest tests/test_db.py -v`
Expected: tüm test_db testleri PASS.

- [ ] **Step 6: Tüm suite'i çalıştır (regresyon)**

Run: `python -m pytest -v`
Expected: mevcut 23 + yeni 2 test PASS.

- [ ] **Step 7: Commit**

```bash
git add src/review_evidence/db.py tests/test_db.py
git commit -m "reviews tablosuna embedding kolonu ve pgvector kurulumu ekledim"
```

---

## Task 3: `_rrf_fuse` saf fonksiyonu

**Files:**
- Modify: `src/review_evidence/search.py`
- Test: `tests/test_search.py`

**Interfaces:**
- Consumes: yok
- Produces: `_rrf_fuse(ranked_lists: list[list[dict]], k: int = 60) -> list[dict]` — her dict `id` anahtarı içerir; birleşik RRF skoruna göre azalan sırada, her `id` bir kez, ilk görülen dict korunur.

- [ ] **Step 1: Failing test yaz — `tests/test_search.py` sonuna ekle**

```python
from review_evidence.search import _rrf_fuse


def test_rrf_fuse_ranks_items_appearing_in_both_lists_higher():
    list_a = [{"id": 1}, {"id": 2}, {"id": 3}]
    list_b = [{"id": 3}, {"id": 2}, {"id": 9}]

    fused = _rrf_fuse([list_a, list_b])

    assert [row["id"] for row in fused[:2]] == [2, 3]
    assert {row["id"] for row in fused} == {1, 2, 3, 9}


def test_rrf_fuse_handles_empty_list():
    only = [{"id": 5}, {"id": 6}]

    fused = _rrf_fuse([only, []])

    assert [row["id"] for row in fused] == [5, 6]


def test_rrf_fuse_preserves_first_seen_row_payload():
    fused = _rrf_fuse([[{"id": 1, "raw_text": "a"}], [{"id": 1, "raw_text": "b"}]])

    assert fused[0]["raw_text"] == "a"
```

Not: `test_rrf_fuse_ranks_...` — id 2 her iki listede rank 1 (0-index), id 3 bir listede rank 2 bir listede rank 0. RRF k=60: id2 = 1/61+1/61 ≈ 0.0328, id3 = 1/62+1/60 ≈ 0.0328. Yakınlar; test sadece ikisinin ilk ikide olmasını ve id1/id9'un altında olmasını doğruluyorsa daha sağlam olur. Testi şu şekilde güncelle:

```python
def test_rrf_fuse_ranks_items_appearing_in_both_lists_higher():
    list_a = [{"id": 1}, {"id": 2}, {"id": 3}]
    list_b = [{"id": 3}, {"id": 2}, {"id": 9}]

    fused = _rrf_fuse([list_a, list_b])

    top_two = {row["id"] for row in fused[:2]}
    assert top_two == {2, 3}
    assert {row["id"] for row in fused} == {1, 2, 3, 9}
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `python -m pytest tests/test_search.py -k rrf -v`
Expected: FAIL — `_rrf_fuse` tanımlı değil.

- [ ] **Step 3: `search.py` — `_rrf_fuse` implementasyonu**

Dosya başına sabitleri ekle (varsa güncelle):

```python
KEYWORD_K = 100
VECTOR_K = 100
CANDIDATE_LIMIT = 200
RRF_K = 60
```

Fonksiyonu ekle:

```python
def _rrf_fuse(ranked_lists: list[list[dict]], k: int = RRF_K) -> list[dict]:
    """Reciprocal Rank Fusion: birden fazla sirali listeyi id bazinda birlestirir.

    Skor = toplam(1 / (k + rank)); rank her listede 0'dan baslar. Skorlari
    normalize etmeye gerek yok, sadece sira pozisyonu sayilir.
    """
    scores: dict = {}
    rows: dict = {}
    for ranked in ranked_lists:
        for rank, row in enumerate(ranked):
            rid = row["id"]
            scores[rid] = scores.get(rid, 0.0) + 1.0 / (k + rank)
            rows.setdefault(rid, row)
    ordered_ids = sorted(scores, key=lambda rid: scores[rid], reverse=True)
    return [rows[rid] for rid in ordered_ids]
```

- [ ] **Step 4: Testlerin geçtiğini doğrula**

Run: `python -m pytest tests/test_search.py -k rrf -v`
Expected: 3 test PASS.

- [ ] **Step 5: Commit**

```bash
git add src/review_evidence/search.py tests/test_search.py
git commit -m "hibrit arama icin rrf fonksiyonunu ekledim"
```

---

## Task 4: `keyword_search` — ts_rank sıralaması

**Files:**
- Modify: `src/review_evidence/search.py`
- Test: `tests/test_search.py`

**Interfaces:**
- Consumes: Task 3 sabitleri
- Produces: `keyword_search(conn, product_id, query, limit=KEYWORD_K) -> list[dict]` — `ts_rank` DESC sıralı, `id/raw_text/created_at` alanlı.

- [ ] **Step 1: Failing test yaz — `tests/test_search.py` sonuna ekle**

```python
def test_keyword_search_orders_by_relevance(db_conn):
    rows = [("p1", f"pil dayanikli urun {i}") for i in range(30)]
    rows.append(("p1", "pil pil pil cok kotu hemen bitiyor"))
    _seed(db_conn, rows)

    results = keyword_search(db_conn, "p1", "pil kotu", limit=5)

    assert "kotu" in results[0]["raw_text"]
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `python -m pytest tests/test_search.py -k orders_by_relevance -v`
Expected: FAIL — sıralama yok, alakasız satır ilk gelebilir.

- [ ] **Step 3: `search.py` — `keyword_search` gövdesini güncelle**

`limit` varsayılanını `KEYWORD_K` yap ve SQL'i değiştir:

```python
def keyword_search(
    conn: psycopg.Connection,
    product_id: str,
    query: str,
    limit: int = KEYWORD_K,
) -> list[dict]:
    """PostgreSQL tam metin aramasiyla sorudaki kelimelerden herhangi birini
    iceren yorumlari, alaka (ts_rank) sirasina gore getirir (OR mantigi,
    Turkce dil yapilandirmasiyla)."""
    tokens = [t for t in normalize(query).split() if t]
    if not tokens:
        return []

    tsquery_str = " | ".join(tokens)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, raw_text, created_at
            FROM reviews
            WHERE product_id = %s
              AND to_tsvector('turkish', clean_text) @@ to_tsquery('turkish', %s)
            ORDER BY ts_rank(
                to_tsvector('turkish', clean_text),
                to_tsquery('turkish', %s)
            ) DESC
            LIMIT %s
            """,
            (product_id, tsquery_str, tsquery_str, limit),
        )
        return cur.fetchall()
```

- [ ] **Step 4: Testlerin geçtiğini doğrula**

Run: `python -m pytest tests/test_search.py -v`
Expected: yeni test + mevcut keyword_search testleri PASS.

- [ ] **Step 5: Commit**

```bash
git add src/review_evidence/search.py tests/test_search.py
git commit -m "keyword aramasini ts_rank ile alaka sirasina soktum"
```

---

## Task 5: `embedding.py` — lokal encoder

**Files:**
- Create: `src/review_evidence/embedding.py`
- Create: `tests/test_embedding.py`

**Interfaces:**
- Consumes: Task 1 (`sentence-transformers`)
- Produces:
  - `EncoderFn = Callable[[list[str]], list[list[float]]]`
  - `sentence_transformer_encoder(model_name: str = "paraphrase-multilingual-MiniLM-L12-v2") -> EncoderFn` — döndürülen fonksiyon batch metni 384-boyutlu L2-normalize vektör listesine çevirir. Model ilk çağrıda yüklenip modül seviyesinde cache'lenir.

- [ ] **Step 1: Failing test yaz — `tests/test_embedding.py` oluştur**

```python
import pytest

from review_evidence.embedding import sentence_transformer_encoder


@pytest.mark.slow
def test_encoder_returns_384_dim_normalized_vectors():
    encode = sentence_transformer_encoder()

    vectors = encode(["urun cok kotu", "urun harika"])

    assert len(vectors) == 2
    assert all(len(v) == 384 for v in vectors)
    norm = sum(x * x for x in vectors[0]) ** 0.5
    assert abs(norm - 1.0) < 1e-3


@pytest.mark.slow
def test_encoder_places_synonyms_closer_than_antonyms():
    encode = sentence_transformer_encoder()
    kotu, berbat, harika = encode(["urun kotu", "urun berbat", "urun harika"])

    def dot(a, b):
        return sum(x * y for x, y in zip(a, b))

    assert dot(kotu, berbat) > dot(kotu, harika)
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `python -m pytest tests/test_embedding.py -m slow -v`
Expected: FAIL — `review_evidence.embedding` modülü yok.

- [ ] **Step 3: `src/review_evidence/embedding.py` oluştur**

```python
"""Lokal cumle embedding'i (anlamsal arama icin).

Model lokal calisir; API cagrisi ve kota yoktur. Enjekte edilebilir tasarim:
consensus.gemini_batch_classifier ile ayni desen -- testler sahte encoder verir,
gercek model yalnizca 'slow' testlerde ve calisan uygulamada yuklenir.

Bu modul HTTP katmanini ve veritabanini bilmez.
"""

from typing import Callable

EncoderFn = Callable[[list[str]], list[list[float]]]

DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

_model_cache: dict = {}


def _get_model(model_name: str):
    if model_name not in _model_cache:
        from sentence_transformers import SentenceTransformer

        _model_cache[model_name] = SentenceTransformer(model_name)
    return _model_cache[model_name]


def sentence_transformer_encoder(model_name: str = DEFAULT_MODEL) -> EncoderFn:
    """Batch metni L2-normalize edilmis 384-boyutlu vektor listesine ceviren
    bir fonksiyon doner. Model ilk cagrida yuklenir ve cache'lenir."""

    def encode(texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = _get_model(model_name)
        vectors = model.encode(
            texts, normalize_embeddings=True, convert_to_numpy=True
        )
        return vectors.tolist()

    return encode
```

- [ ] **Step 4: Testlerin geçtiğini doğrula**

Run: `python -m pytest tests/test_embedding.py -m slow -v`
Expected: 2 test PASS (ilk çalıştırmada model indirilir, ~1-2 dk).

- [ ] **Step 5: Varsayılan koşuda atlandığını doğrula**

Run: `python -m pytest tests/test_embedding.py -v`
Expected: 2 test SKIPPED (deselected by `-m "not slow"`).

- [ ] **Step 6: Commit**

```bash
git add src/review_evidence/embedding.py tests/test_embedding.py
git commit -m "lokal sentence-transformers encoder modulunu ekledim"
```

---

## Task 6: `vector_search`

**Files:**
- Modify: `src/review_evidence/search.py`
- Test: `tests/test_search.py`

**Interfaces:**
- Consumes: Task 2 (`embedding` kolonu, `register_vector`), Task 3 sabitleri
- Produces: `vector_search(conn, product_id, query_embedding: list[float], limit: int = VECTOR_K) -> list[dict]` — cosine mesafesine göre artan sıralı (`<=>`), `embedding IS NULL` satırları hariç.

- [ ] **Step 1: Failing test yaz — `tests/test_search.py` sonuna ekle**

`_seed` yardımcı fonksiyonu embedding kabul etmiyor; yeni bir yardımcı ekle:

```python
def _seed_with_embeddings(conn, rows):
    """rows: (product_id, text, embedding_list) uclulleri."""
    with conn.cursor() as cur:
        for product_id, text, emb in rows:
            cur.execute(
                "INSERT INTO reviews (product_id, raw_text, clean_text, embedding)"
                " VALUES (%s, %s, %s, %s)",
                (product_id, text, text.lower(), emb),
            )
    conn.commit()


def _vec(*first):
    """Ilk birkac boyutu verilen, kalani 0 olan 384-boyutlu vektor."""
    v = list(first) + [0.0] * (384 - len(first))
    return v


def test_vector_search_orders_by_cosine_distance(db_conn):
    _seed_with_embeddings(
        db_conn,
        [
            ("p1", "yakin", _vec(1.0, 0.0)),
            ("p1", "orta", _vec(0.7, 0.7)),
            ("p1", "uzak", _vec(0.0, 1.0)),
        ],
    )
    from review_evidence.search import vector_search

    results = vector_search(db_conn, "p1", _vec(1.0, 0.0), limit=3)

    assert [r["raw_text"] for r in results] == ["yakin", "orta", "uzak"]


def test_vector_search_excludes_null_embeddings(db_conn):
    _seed(db_conn, [("p1", "embedding yok")])  # eski _seed embedding vermez
    _seed_with_embeddings(db_conn, [("p1", "embedding var", _vec(1.0))])
    from review_evidence.search import vector_search

    results = vector_search(db_conn, "p1", _vec(1.0), limit=10)

    assert [r["raw_text"] for r in results] == ["embedding var"]
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `python -m pytest tests/test_search.py -k vector_search -v`
Expected: FAIL — `vector_search` tanımlı değil.

- [ ] **Step 3: `search.py` — `vector_search` ekle**

```python
def vector_search(
    conn: psycopg.Connection,
    product_id: str,
    query_embedding: list[float],
    limit: int = VECTOR_K,
) -> list[dict]:
    """Embedding benzerligine (cosine) gore en yakin yorumlari getirir.
    embedding'i olmayan satirlar haric."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, raw_text, created_at
            FROM reviews
            WHERE product_id = %s
              AND embedding IS NOT NULL
            ORDER BY embedding <=> %s
            LIMIT %s
            """,
            (product_id, query_embedding, limit),
        )
        return cur.fetchall()
```

- [ ] **Step 4: Testlerin geçtiğini doğrula**

Run: `python -m pytest tests/test_search.py -v`
Expected: yeni testler + mevcut testler PASS.

- [ ] **Step 5: Commit**

```bash
git add src/review_evidence/search.py tests/test_search.py
git commit -m "pgvector ile vector_search ekledim"
```

---

## Task 7: `hybrid_search`

**Files:**
- Modify: `src/review_evidence/search.py`
- Test: `tests/test_search.py`

**Interfaces:**
- Consumes: `keyword_search`, `vector_search`, `_rrf_fuse`, `EncoderFn` (Task 5)
- Produces: `hybrid_search(conn, product_id, query, encode: EncoderFn | None = None, k_each: int = KEYWORD_K, limit: int = CANDIDATE_LIMIT) -> list[dict]` — `encode` None ise sadece `keyword_search`; aksi halde iki kolun RRF birleşimi, ilk `limit` satır.

- [ ] **Step 1: Failing test yaz — `tests/test_search.py` sonuna ekle**

```python
def test_hybrid_search_without_encoder_is_keyword_only(db_conn):
    _seed(db_conn, [("p1", "pil kotu"), ("p1", "kargo hizli")])
    from review_evidence.search import hybrid_search

    results = hybrid_search(db_conn, "p1", "pil", encode=None)

    assert [r["raw_text"] for r in results] == ["pil kotu"]


def test_hybrid_search_surfaces_semantic_match_keyword_misses(db_conn):
    # "berbat" sorgudaki "kotu" token'ini icermiyor -> keyword bulamaz.
    # Sahte encoder onu sorguya yakin konumlandirir.
    _seed_with_embeddings(
        db_conn,
        [
            ("p1", "urun berbat cikti", _vec(1.0, 0.0)),
            ("p1", "kargo suersi uzun", _vec(0.0, 1.0)),
        ],
    )
    _seed(db_conn, [("p1", "urun kotu geldi")])  # keyword eslesmesi, embedding yok

    def fake_encode(texts):
        return [_vec(1.0, 0.0) for _ in texts]  # sorgu "berbat" satirina yakin

    from review_evidence.search import hybrid_search

    results = hybrid_search(db_conn, "p1", "urun kotu", encode=fake_encode)
    texts = [r["raw_text"] for r in results]

    assert "urun berbat cikti" in texts  # vektor kolundan geldi
    assert "urun kotu geldi" in texts    # keyword kolundan geldi


def test_hybrid_search_respects_limit(db_conn):
    _seed(db_conn, [("p1", f"pil yorum {i}") for i in range(10)])
    from review_evidence.search import hybrid_search

    results = hybrid_search(db_conn, "p1", "pil", encode=None, limit=3)

    assert len(results) == 3
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `python -m pytest tests/test_search.py -k hybrid -v`
Expected: FAIL — `hybrid_search` tanımlı değil.

- [ ] **Step 3: `search.py` — `hybrid_search` ekle**

Dosya başına import ekle:

```python
from review_evidence.embedding import EncoderFn
```

Fonksiyon:

```python
def hybrid_search(
    conn: psycopg.Connection,
    product_id: str,
    query: str,
    encode: EncoderFn | None = None,
    k_each: int = KEYWORD_K,
    limit: int = CANDIDATE_LIMIT,
) -> list[dict]:
    """Anahtar kelime (ts_rank) ve embedding (cosine) aramalarini RRF ile
    birlestirir. encode None ise sadece anahtar kelime aramasi calisir
    (model yuklenememis durumdaki fallback)."""
    keyword_rows = keyword_search(conn, product_id, query, limit=k_each)

    if encode is None:
        return keyword_rows[:limit]

    query_embedding = encode([query])[0]
    vector_rows = vector_search(conn, product_id, query_embedding, limit=k_each)

    fused = _rrf_fuse([keyword_rows, vector_rows])
    return fused[:limit]
```

- [ ] **Step 4: Testlerin geçtiğini doğrula**

Run: `python -m pytest tests/test_search.py -v`
Expected: tüm test_search testleri PASS.

- [ ] **Step 5: Slow entegrasyon testi ekle — gerçek modelle uçtan uca**

`tests/test_search.py` sonuna:

```python
@pytest.mark.slow
def test_hybrid_search_real_model_ranks_negative_for_negative_query(db_conn):
    import pytest as _pytest  # noqa
    from review_evidence.embedding import sentence_transformer_encoder
    from review_evidence.search import hybrid_search

    encode = sentence_transformer_encoder()
    texts = [
        "urun berbat, paramin hakkini vermedi",
        "urun harika, cok memnunum",
        "kargo hizli geldi",
    ]
    vectors = encode(texts)
    with db_conn.cursor() as cur:
        for text, emb in zip(texts, vectors):
            cur.execute(
                "INSERT INTO reviews (product_id, raw_text, clean_text, embedding)"
                " VALUES (%s, %s, %s, %s)",
                ("p1", text, text.lower(), emb),
            )
    db_conn.commit()

    results = hybrid_search(db_conn, "p1", "urun kotu mu", encode=encode, limit=3)

    assert results[0]["raw_text"].startswith("urun berbat")
```

`tests/test_search.py` başında `import pytest` olduğundan emin ol.

- [ ] **Step 6: Slow testi doğrula**

Run: `python -m pytest tests/test_search.py -m slow -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/review_evidence/search.py tests/test_search.py
git commit -m "keyword ve vektor aramasini rrf ile birlestiren hybrid_search ekledim"
```

---

## Task 8: `build_consensus` — hybrid_search entegrasyonu

**Files:**
- Modify: `src/review_evidence/consensus.py`
- Test: `tests/test_consensus.py`

**Interfaces:**
- Consumes: `hybrid_search`, `EncoderFn`
- Produces: `build_consensus(conn, product_id, question, classify_batch, encode: EncoderFn | None = None) -> dict` — dönen dict'e `"search_mode": "hybrid" | "keyword_only"` eklenir.

- [ ] **Step 1: Failing test yaz — `tests/test_consensus.py` sonuna ekle**

```python
def test_build_consensus_reports_keyword_only_mode_without_encoder(db_conn):
    _seed(db_conn, [("p1", "pil cok iyi")])
    classify_batch = _fake_batch_classifier(
        {"pil cok iyi": {"relevant": True, "sentiment": "positive"}}
    )

    result = build_consensus(db_conn, "p1", "pil", classify_batch)

    assert result["search_mode"] == "keyword_only"


def test_build_consensus_reports_hybrid_mode_with_encoder(db_conn):
    _seed(db_conn, [("p1", "pil cok iyi")])
    classify_batch = _fake_batch_classifier(
        {"pil cok iyi": {"relevant": True, "sentiment": "positive"}}
    )

    def fake_encode(texts):
        return [[0.0] * 384 for _ in texts]

    result = build_consensus(db_conn, "p1", "pil", classify_batch, encode=fake_encode)

    assert result["search_mode"] == "hybrid"
    assert result["relevant_count"] == 1
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `python -m pytest tests/test_consensus.py -k search_mode -v`
Expected: FAIL — `search_mode` anahtarı yok.

- [ ] **Step 3: `consensus.py` — importu değiştir**

```python
from review_evidence.search import hybrid_search
from review_evidence.embedding import EncoderFn
```

(`from review_evidence.search import keyword_search` satırını kaldır.)

- [ ] **Step 4: `consensus.py` — `build_consensus` imza ve gövde**

```python
def build_consensus(
    conn: psycopg.Connection,
    product_id: str,
    question: str,
    classify_batch: BatchClassifierFn,
    encode: EncoderFn | None = None,
) -> dict:
    """Bir urun+soru icin sayim tabanli mutabakat raporu uretir."""
    candidates = hybrid_search(conn, product_id, question, encode)
```

Fonksiyonun `return` sözlüğüne alan ekle:

```python
    return {
        "question": question,
        "product_id": product_id,
        "search_mode": "hybrid" if encode is not None else "keyword_only",
        "candidates_checked": len(candidates),
        ...
    }
```

(Kalan alanlar aynı.)

- [ ] **Step 5: Testlerin geçtiğini doğrula**

Run: `python -m pytest tests/test_consensus.py -v`
Expected: yeni 2 test + mevcut 5 test PASS.

- [ ] **Step 6: Tüm suite (regresyon)**

Run: `python -m pytest -v`
Expected: hepsi PASS (slow hariç).

- [ ] **Step 7: Commit**

```bash
git add src/review_evidence/consensus.py tests/test_consensus.py
git commit -m "build_consensus artik hibrit aramayi kullaniyor"
```

---

## Task 9: `ingest.py` — yüklerken embedding üretimi

**Files:**
- Modify: `src/review_evidence/ingest.py`
- Test: `tests/test_ingest.py`

**Interfaces:**
- Consumes: `EncoderFn`, `sentence_transformer_encoder`
- Produces: `load_reviews(conn, path, encode: EncoderFn | None = None) -> int` — `encode` None ise modül-varsayılan encoder lazy oluşturulur; encode hata fırlatırsa satırlar NULL embedding ile yüklenir.

- [ ] **Step 1: Failing test yaz — `tests/test_ingest.py` sonuna ekle**

```python
def test_load_reviews_stores_embeddings(db_conn, tmp_path):
    source = tmp_path / "reviews.json"
    source.write_text(
        json.dumps([{"product_id": "p1", "text": "urun guzel"}]),
        encoding="utf-8",
    )

    def fake_encode(texts):
        return [[0.5] * 384 for _ in texts]

    load_reviews(db_conn, source, encode=fake_encode)

    with db_conn.cursor() as cur:
        cur.execute("SELECT embedding FROM reviews")
        row = cur.fetchone()

    assert row["embedding"] is not None
    assert len(list(row["embedding"])) == 384


def test_load_reviews_survives_encoder_failure(db_conn, tmp_path):
    source = tmp_path / "reviews.json"
    source.write_text(
        json.dumps([{"product_id": "p1", "text": "urun guzel"}]),
        encoding="utf-8",
    )

    def broken_encode(texts):
        raise RuntimeError("model yok")

    inserted = load_reviews(db_conn, source, encode=broken_encode)

    assert inserted == 1
    with db_conn.cursor() as cur:
        cur.execute("SELECT embedding FROM reviews")
        assert cur.fetchone()["embedding"] is None
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `python -m pytest tests/test_ingest.py -k embedding -v`
Expected: FAIL — `load_reviews` `encode` parametresi kabul etmiyor.

- [ ] **Step 3: `ingest.py` — güncelle**

```python
"""Veri setinden veritabanina yukleme."""

import json
from pathlib import Path

import psycopg

from review_evidence.embedding import EncoderFn, sentence_transformer_encoder
from review_evidence.text import normalize


def load_reviews(
    conn: psycopg.Connection,
    path: Path,
    encode: EncoderFn | None = None,
) -> int:
    """JSON dosyasindaki yorumlari veritabanina yukler.

    Metni bos veya eksik olan kayitlar atlanir. Her yorum icin raw_text'ten
    bir embedding uretilir; encode verilmezse lokal model kullanilir. Embedding
    uretimi basarisiz olursa satirlar embedding'siz (NULL) yuklenir.
    Eklenen satir sayisini doner.
    """
    records = json.loads(path.read_text(encoding="utf-8"))

    prepared = []
    for record in records:
        raw = record.get("text", "")
        if not raw.strip():
            continue
        prepared.append((record["product_id"], raw, record.get("created_at")))

    if not prepared:
        return 0

    if encode is None:
        encode = sentence_transformer_encoder()

    raw_texts = [raw for _, raw, _ in prepared]
    try:
        embeddings = encode(raw_texts)
    except Exception as exc:  # model yok / indirilemedi -> embedding'siz devam
        print(f"[ingest] embedding uretilemedi, NULL ile yukleniyor: {exc}")
        embeddings = [None] * len(prepared)

    rows = [
        (product_id, raw, normalize(raw), created_at, emb)
        for (product_id, raw, created_at), emb in zip(prepared, embeddings)
    ]

    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO reviews (product_id, raw_text, clean_text, created_at, embedding)"
            " VALUES (%s, %s, %s, %s, %s)",
            rows,
        )
    conn.commit()
    return len(rows)
```

- [ ] **Step 4: Testlerin geçtiğini doğrula**

Run: `python -m pytest tests/test_ingest.py -v`
Expected: yeni 2 test + mevcut 3 test PASS. (Mevcut testler `encode` vermiyor → gerçek model yüklenir. Eğer CI/hız sorunuysa: mevcut testlere `encode=lambda t: [[0.0]*384 for _ in t]` eklenebilir; ama testler zaten `db_conn` gerektiriyor ve az sayıda satır. İlk çalıştırmada model indirilir.)

**Not:** Mevcut `test_load_reviews_*` testleri artık gerçek modeli tetikler. Bunu önlemek için o üç teste de sahte encoder ekle:

```python
_FAKE_ENCODE = lambda texts: [[0.0] * 384 for _ in texts]
```
ve her `load_reviews(db_conn, source)` çağrısını `load_reviews(db_conn, source, encode=_FAKE_ENCODE)` yap.

- [ ] **Step 5: Commit**

```bash
git add src/review_evidence/ingest.py tests/test_ingest.py
git commit -m "ingest sirasinda yorumlarin embedding'ini uretiyorum"
```

---

## Task 10: `scripts/backfill_embeddings.py`

**Files:**
- Create: `scripts/backfill_embeddings.py`

**Interfaces:**
- Consumes: `connect`, `init_schema`, `sentence_transformer_encoder`, `DATABASE_URL`
- Produces: çalıştırılabilir script; `embedding IS NULL` satırlarını doldurur.

- [ ] **Step 1: `scripts/backfill_embeddings.py` oluştur**

```python
"""Mevcut (embedding'i NULL olan) yorumlar icin embedding uretir.

Yuklu veriye pgvector sonradan eklendiginde bir kez calistirilir. Idempotent:
zaten embedding'i olan satirlara dokunmaz.

Kullanim:
    python scripts/backfill_embeddings.py
"""

from review_evidence.config import DATABASE_URL
from review_evidence.db import connect, init_schema
from review_evidence.embedding import sentence_transformer_encoder

BATCH_SIZE = 64


def main() -> None:
    conn = connect(DATABASE_URL)
    init_schema(conn)
    encode = sentence_transformer_encoder()

    with conn.cursor() as cur:
        cur.execute("SELECT id, raw_text FROM reviews WHERE embedding IS NULL ORDER BY id")
        pending = cur.fetchall()

    if not pending:
        print("embedding'i eksik yorum yok.")
        return

    print(f"{len(pending)} yorum icin embedding uretilecek.")
    done = 0
    for start in range(0, len(pending), BATCH_SIZE):
        chunk = pending[start : start + BATCH_SIZE]
        vectors = encode([row["raw_text"] for row in chunk])
        with conn.cursor() as cur:
            cur.executemany(
                "UPDATE reviews SET embedding = %s WHERE id = %s",
                [(vec, row["id"]) for row, vec in zip(chunk, vectors)],
            )
        conn.commit()
        done += len(chunk)
        print(f"  {done}/{len(pending)}")

    conn.close()
    print("bitti.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Script'i çalıştır (yüklü veri üzerinde)**

Run: `python scripts/backfill_embeddings.py`
Expected: ya "embedding'i eksik yorum yok" (veri henüz yüklü değilse tablo boş) ya da 1000 yorum için ilerleme çıktısı. Hata vermemeli.

- [ ] **Step 3: Commit**

```bash
git add scripts/backfill_embeddings.py
git commit -m "mevcut yorumlara embedding dolduran backfill scriptini ekledim"
```

---

## Task 11: `main.py` — encoder singleton + wiring

**Files:**
- Modify: `src/review_evidence/main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `sentence_transformer_encoder`, `build_consensus`
- Produces: modül seviyesinde `_encode` (yüklenemezse `None`); `ask()` `build_consensus(..., encode=_encode)` çağırır.

- [ ] **Step 1: Failing test yaz — `tests/test_main.py` sonuna ekle**

```python
def test_ask_returns_503_without_gemini_key(db_conn, monkeypatch):
    import review_evidence.main as main_module

    monkeypatch.setattr(main_module, "_client", None)

    def override_get_conn():
        yield db_conn

    app.dependency_overrides[get_conn] = override_get_conn
    try:
        response = client.get("/products/p1/ask", params={"question": "pil nasil"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
```

(Bu test `_encode` yolunu doğrudan test etmez ama `main` importunun encoder yükleme denemesiyle çökmediğini garanti eder; `_client=None` olduğu için Gemini çağrısına gidilmez.)

- [ ] **Step 2: Testin durumunu gör**

Run: `python -m pytest tests/test_main.py -v`
Expected: import sırasında `_encode = sentence_transformer_encoder()` henüz yok; yeni test muhtemelen PASS ama Step 3 sonrası da PASS kalmalı. Asıl amaç regresyon.

- [ ] **Step 3: `main.py` — güncelle**

Importlara ekle:

```python
from review_evidence.embedding import sentence_transformer_encoder
```

`_client` tanımının altına:

```python
try:
    _encode = sentence_transformer_encoder()
except Exception as exc:  # model yok / indirilemedi -> keyword-only calisma
    print(f"[main] embedding modeli yuklenemedi, arama keyword-only: {exc}")
    _encode = None
```

`ask()` içindeki `build_consensus` çağrısı:

```python
    classify_batch = gemini_batch_classifier(_client)
    return build_consensus(conn, product_id, question, classify_batch, encode=_encode)
```

- [ ] **Step 4: Testlerin geçtiğini doğrula**

Run: `python -m pytest tests/test_main.py -v`
Expected: tüm test_main testleri PASS.

- [ ] **Step 5: Tüm suite (regresyon)**

Run: `python -m pytest -v`
Expected: hepsi PASS (slow hariç). Toplam test sayısı ~23 + yeni ≈ 35+.

- [ ] **Step 6: Manuel duman testi — uygulama ayağa kalkıyor mu**

Run:
```
python -c "import review_evidence.main; print('import ok, encode =', review_evidence.main._encode is not None)"
```
Expected: `import ok, encode = True` (model ilk kez inip yüklenir). Hata yoksa geç.

- [ ] **Step 7: Commit**

```bash
git add src/review_evidence/main.py tests/test_main.py
git commit -m "uygulama acilisinda embedding modelini yukluyorum, /ask hibrit aramayi kullaniyor"
```

---

## Task 12: CI workflow + README rozeti

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `README.md`

**Interfaces:**
- Consumes: `pyproject.toml` (`.[dev]`), `pgvector/pgvector:pg16`
- Produces: her push'ta `pytest -m "not slow"` çalışan CI.

- [ ] **Step 1: `.github/workflows/ci.yml` oluştur**

```yaml
name: CI

on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      db:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_USER: review_evidence
          POSTGRES_PASSWORD: review_evidence
          POSTGRES_DB: review_evidence
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U review_evidence"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10

    env:
      DATABASE_URL: postgresql://review_evidence:review_evidence@localhost:5432/review_evidence

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: Install
        run: pip install -e ".[dev]"

      - name: Test
        run: pytest -m "not slow" -v
```

- [ ] **Step 2: README rozetini ekle**

`README.md` en üst başlığın hemen altına (repo `owner/name` değerini gerçek değerle değiştir — `git remote get-url origin` ile bak):

```markdown
[![CI](https://github.com/<owner>/review-evidence-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/<owner>/review-evidence-engine/actions/workflows/ci.yml)
```

- [ ] **Step 3: Lokalde CI komutunu birebir doğrula**

Run: `python -m pytest -m "not slow" -v`
Expected: tüm testler PASS.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml README.md
git commit -m "github actions ekledim, testler her push'ta calisiyor"
```

---

## Task 13: README — hibrit arama bölümü + doğrulama

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: tüm önceki task'lar
- Produces: güncel README; yeşil suite.

- [ ] **Step 1: README'de aramayı anlatan bölümü güncelle**

Mevcut "FTS5 ile arama" / "anahtar kelime araması" ifadelerini bul ve şununla değiştir (Türkçe ve İngilizce bölümlerin ikisinde de):

- TR: "Aday yorumlar hibrit aramayla bulunur: Türkçe tam metin araması (`ts_rank` ile sıralı) ile lokal çok dilli embedding modelinin (`paraphrase-multilingual-MiniLM-L12-v2`) benzerlik araması, Reciprocal Rank Fusion ile birleştirilir. Embedding modeli yüklenemezse sistem otomatik olarak yalnızca anahtar kelime aramasına düşer."
- EN: "Candidate reviews are found with hybrid search: Turkish full-text search (ranked by `ts_rank`) is fused with a local multilingual embedding model (`paraphrase-multilingual-MiniLM-L12-v2`) via Reciprocal Rank Fusion. If the embedding model fails to load, the system falls back to keyword-only search."

Kurulum bölümüne bir satır ekle: "İlk çalıştırmada embedding modeli (~120 MB) indirilir. Mevcut veriye embedding eklemek için: `python scripts/backfill_embeddings.py`."

- [ ] **Step 2: Tüm doğrulama**

Run:
```
python -m pytest -v
python -m pytest -m slow -v
```
Expected: ilki hepsi PASS/SKIPPED; ikincisi slow testler PASS (model yüklenir).

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "readme'yi hibrit aramayla guncelledim"
```

- [ ] **Step 4: Branch'i birleştirmeye hazırla**

`superpowers:finishing-a-development-branch` skill'ini çağır.

---

## Self-Review

**Spec coverage:**
- Embedding modülü (enjekte edilebilir, lazy singleton) → Task 5 ✓
- `keyword_search` ts_rank → Task 4 ✓
- `vector_search` → Task 6 ✓
- `hybrid_search` + `_rrf_fuse` (RRF k=60) → Task 3, 7 ✓
- `build_consensus` encode param + `search_mode` → Task 8 ✓
- `main.py` fallback (503 değil) → Task 11 ✓
- `ingest.py` embedding + encoder enjeksiyonu + hata toleransı → Task 9 ✓
- `backfill_embeddings.py` → Task 10 ✓
- Şema: extension + `ADD COLUMN IF NOT EXISTS` + hnsw + `register_vector` → Task 2 ✓
- docker-compose pgvector imajı → Task 1 ✓
- pyproject bağımlılıklar + `slow` marker → Task 1 ✓
- Hata yönetimi tablosu: model yok (T11), token yok (T4 erken dönüş korunuyor), NULL embedding (T6 `WHERE embedding IS NOT NULL`), extension yok (T2 net hata), boş RRF kolu (T3 tolere) ✓
- Test planı: rrf birim (T3), keyword sıralama (T4), vector (T6), hybrid + encode=None (T7), consensus (T8), ingest (T9), slow gerçek model (T5, T7) ✓
- CI (T12) ✓
- README (T13) ✓
- Kapsam dışı maddeler: plana hiç girmedi ✓

**Placeholder scan:** `<owner>` (Task 12 Step 2) — bilinçli, executor `git remote` ile dolduracak, talimat net. Başka placeholder yok.

**Type consistency:**
- `EncoderFn = Callable[[list[str]], list[list[float]]]` — Task 5'te tanımlı, Task 6/7/8/9/11'de aynı isimle import ediliyor ✓
- `_rrf_fuse(ranked_lists, k=RRF_K)` → Task 3 tanım, Task 7 çağrısı `_rrf_fuse([keyword_rows, vector_rows])` ✓
- `hybrid_search(conn, product_id, query, encode=None, k_each=KEYWORD_K, limit=CANDIDATE_LIMIT)` → Task 7 tanım, Task 8 çağrısı `hybrid_search(conn, product_id, question, encode)` ✓
- `keyword_search(..., limit=KEYWORD_K)` → Task 4, Task 7'de `limit=k_each` ✓
- `vector_search(conn, product_id, query_embedding, limit=VECTOR_K)` → Task 6, Task 7'de `vector_search(conn, product_id, query_embedding, limit=k_each)` ✓
- `build_consensus(conn, product_id, question, classify_batch, encode=None)` → Task 8, Task 11 çağrısı eşleşiyor ✓
- `load_reviews(conn, path, encode=None)` → Task 9, Task 10 backfill kendi UPDATE'ini yapıyor (load_reviews çağırmıyor) ✓
