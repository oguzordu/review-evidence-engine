# Hibrit Arama — Tasarım Dokümanı

> Tarih: 2026-08-31
> Durum: onaylandı, implementasyona hazır
> Branch: `hibrit-arama`

## Problem

`/products/{id}/ask` akışında aday yorumları bulan `search.keyword_search()` alaka
sıralaması yapmıyor:

- Sorgu token'lara bölünüp `token1 | token2` şeklinde **OR** `tsquery` kuruluyor.
- "ürün" gibi çok geçen kelimeler neredeyse tüm tabloyu getiriyor.
- Sonuç `ORDER BY` olmadan keyfi `LIMIT 200` ile kesiliyor.
- İçinde asıl aranan niteleyici ("kötü", "berbat") geçen ilgili yorumlar bu 200'e
  girmeyebiliyor; `consensus.build_consensus()` kirli aday kümesini LLM'e veriyor.
- Belirti: "ürün kötü" arayınca "ürün çok güzel" yorumları dönüyor.

Ek olarak, tamamen sözlüksel arama semantik yakın ama farklı kelimeli yorumları
("berbat", "rezalet", "pişman oldum") hiç bulamıyor.

## Hedef

Anahtar kelime araması (recall) + embedding benzerliği (precision) birleştiren
hibrit arama. Aday kümesi alaka sırasına göre dolsun; projenin "her ilgili yorumu
say" kimliği korunsun (cömert cap, sabit küçük top-N değil).

## Kararlar

| Konu | Karar | Gerekçe |
|---|---|---|
| Embedding modeli | Lokal `sentence-transformers` (`paraphrase-multilingual-MiniLM-L12-v2`, 384 boyut) | Ücretsiz, kota yok, deploy + CI + offline test'te tam çalışır. Bedel: torch bağımlılığı, büyük imaj. |
| Füzyon | Reciprocal Rank Fusion (RRF), k=60 | Skor normalize etmeye gerek yok; ts_rank ve cosine farklı ölçekte. Standart teknik (ES/Weaviate). İki kol bağımsız test edilebilir. |
| Aday kümesi | keyword hits ∪ vector top-K → RRF → ilk 200 | Cap korunuyor ama artık alaka sırasına göre doluyor. p1–p5'te ürün başına ~200 yorum var, cap pratikte desteği kesmiyor. Keyword'ün kaçırdığı semantik eşleşmeler union sayesinde giriyor. |
| Embedding kaynağı | `raw_text` | Çok dilli model doğal metinde, ascii-fold edilmiş `clean_text`'ten iyi. |
| Fallback | Model yoksa keyword-only, 503 değil | Mevcut "sessiz hata yerine görünür fallback" çizgisi. |

## Mimari

### Yeni modül: `src/review_evidence/embedding.py`

- `EncoderFn = Callable[[list[str]], list[list[float]]]` — batch metin → normalize
  edilmiş vektör listesi (L2-normalized, cosine = dot).
- `sentence_transformer_encoder(model_name="paraphrase-multilingual-MiniLM-L12-v2") -> EncoderFn`
  - Modeli lazy singleton olarak yükler (ilk çağrıda, modül seviyesinde cache).
  - `model.encode(texts, normalize_embeddings=True)` sonucu `list[list[float]]`.
- Enjekte edilebilir — `gemini_batch_classifier` ile aynı desen. Testler sahte
  encoder verir; gerçek model yalnızca `@pytest.mark.slow` testte yüklenir.
- HTTP katmanını bilmez.

### `src/review_evidence/search.py`

- `keyword_search(conn, product_id, query, limit=100) -> list[dict]`
  - OR `tsquery` korunur (recall kolu bilerek geniş).
  - Eklenir: `ORDER BY ts_rank(to_tsvector('turkish', clean_text),
    to_tsquery('turkish', %s)) DESC LIMIT %s`.
  - `limit` varsayılanı 200 → 100 (RRF'e giren kol boyutu).
- `vector_search(conn, product_id, query_embedding, limit=100) -> list[dict]` — yeni
  - `SELECT id, raw_text, created_at FROM reviews
     WHERE product_id = %s AND embedding IS NOT NULL
     ORDER BY embedding <=> %s LIMIT %s`
  - `query_embedding` psycopg'ye `pgvector.psycopg` adaptörüyle geçirilir.
- `hybrid_search(conn, product_id, query, encode=None, k_each=100, limit=200) -> list[dict]` — yeni
  - `encode` None ise → sadece `keyword_search` (fallback yolu).
  - Aksi halde: `keyword_search(...k_each)` ve `vector_search(conn, pid,
    encode([query])[0], k_each)` çalıştır.
  - `_rrf_fuse([kw_rows, vec_rows], k=60)` ile id bazında birleştir.
  - Birleşik sıradan ilk `limit` satırı (tam dict, `id/raw_text/created_at`) döndür.
- `_rrf_fuse(ranked_lists: list[list[dict]], k: int = 60) -> list[dict]` — saf fonksiyon
  - `score[id] += 1 / (k + rank)` (rank 0-index veya 1-index tutarlı olsun).
  - Satırın ilk görüldüğü dict'i saklar; skora göre azalan sırada döndürür.
  - Boş liste girişini tolere eder.

Modül sabitleri: `KEYWORD_K = 100`, `VECTOR_K = 100`, `CANDIDATE_LIMIT = 200`,
`RRF_K = 60`.

### `src/review_evidence/consensus.py`

- `build_consensus(conn, product_id, question, classify_batch, encode=None) -> dict`
  - Tek değişiklik: `candidates = keyword_search(conn, product_id, question)` →
    `candidates = hybrid_search(conn, product_id, question, encode)`.
  - `encode` opsiyonel kwarg — mevcut testler (pozisyonel `classify_batch`) bozulmaz.
  - Rapor sözlüğüne alan eklenir: `"search_mode": "hybrid" if encode else "keyword_only"`.

### `src/review_evidence/main.py`

- Modül yüklenirken:
  ```python
  try:
      _encode = sentence_transformer_encoder()
  except Exception as exc:
      print(f"[main] embedding modeli yuklenemedi, keyword-only: {exc}")
      _encode = None
  ```
- `ask()`: `build_consensus(conn, product_id, question, classify_batch, encode=_encode)`.
- `_client is None` kontrolü aynen kalır (Gemini yoksa 503).

### `src/review_evidence/ingest.py`

- `load_reviews`: satırlar hazırlandıktan sonra `raw_text` listesi batch encode
  edilir (varsayılan encoder), INSERT'e `embedding` kolonu eklenir.
- Encoder enjekte edilebilir olsun: `load_reviews(conn, path, encode=None)`;
  `None` ise modül-varsayılan encoder lazy oluşturulur. Testler sahte verebilir.
- Encode başarısızsa: satırlar embedding olmadan yüklenir (NULL), uyarı loglanır;
  ingest tamamen çökmez.

### Yeni script: `scripts/backfill_embeddings.py`

- `embedding IS NULL` satırlarını çeker, batch encode eder, `UPDATE ... SET
  embedding = %s WHERE id = %s`.
- Idempotent; yüklü 1000 yorum için bir kez elle çalıştırılır.
- Batch boyutu 64; ilerleme stdout'a yazılır.

### Şema — `src/review_evidence/db.py`

`SCHEMA` idempotent migration olarak:

```sql
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
```

`connect()` içinde `pgvector.psycopg.register_vector(conn)` çağrılır (vektörleri
Python listesi olarak geçebilmek için).

## Veri Akışı (`/ask`)

1. `encode([question])` → sorgu vektörü (model sıcak).
2. `hybrid_search`:
   - keyword kolu: OR tsquery, `ORDER BY ts_rank DESC LIMIT 100`
   - vektör kolu: `WHERE embedding IS NOT NULL ORDER BY embedding <=> qvec LIMIT 100`
   - `_rrf_fuse` → ilk 200 satır
3. 20'lik batch'ler → `ThreadPoolExecutor` → Gemini sınıflandırma → sayım →
   mutabakat raporu (**bu kısım değişmedi**).

## Hata Yönetimi

| Senaryo | Davranış |
|---|---|
| `sentence-transformers` yok / model indirilemedi | `_encode=None`, log, `/ask` keyword-only (`search_mode: keyword_only`), 503 yok |
| Sorguda keyword token yok | keyword kolu boş, vektör kolu çalışır → vektör-only |
| NULL embedding'li satır | vektör kolundan düşer, keyword kolundan erişilebilir; backfill kapatır |
| pgvector extension yok | `init_schema` → `CREATE EXTENSION` başlangıçta net hata (sessiz değil) |
| Bir RRF kolu boş | diğer kolun sırası aynen geçer (saf fonksiyon tolere eder) |
| Gemini kota / 503 | mevcut retry + fallback davranışı, değişmedi |

## Test Planı

Mevcut stil: gerçek PostgreSQL (docker compose `db`), enjekte edilebilir sahteler.

- `tests/test_search.py`
  - `_rrf_fuse()` birim testleri (DB'siz): boş liste, çakışan id, sıra korunması,
    tek kol.
  - `keyword_search` — ts_rank sıralaması alakalıyı öne alıyor (seed: bir "pil kötü",
    çok sayıda alakasız "pil" içeren satır; "pil kötü" ilk sırada).
  - `vector_search` — sahte encoder + satırlara elle yazılmış embedding; en yakın
    vektör ilk sırada, `embedding IS NULL` satır dışlanıyor.
  - `hybrid_search` — ana test: keyword'ün bulamadığı ("berbat", token "kötü" yok)
    ama vektörce yakın satır sonuç kümesinde; `encode=None` → keyword-only.
- `tests/test_consensus.py`
  - `build_consensus`'a sahte `encode` + sahte `classify_batch`.
  - `encode=None` yolu keyword-only çalışıyor, `search_mode` alanı doğru.
  - Mevcut testler (pozisyonel `classify_batch`) değişmeden geçmeli.
- `tests/test_ingest.py`
  - `load_reviews(conn, path, encode=fake)` embedding kolonunu dolduruyor.
  - encode hata fırlatırsa satırlar NULL embedding ile yükleniyor, çökmüyor.
- `@pytest.mark.slow` (yeni marker, `pyproject.toml`'a eklenir; varsayılan/CI'da
  `-m "not slow"`)
  - Gerçek MiniLM yüklenir; "ürün kötü" sorgusunda "berbat" yorumu "harika"
    yorumunun üstünde sıralanır.
- `tests/conftest.py` — `init_schema` zaten extension + kolonu kuruyor, ek iş yok.
  `TRUNCATE ... RESTART IDENTITY` embedding kolonunu da temizler.

## CI

`.github/workflows/ci.yml` yok (önceki oturum eklediğini sanmış, commit'lememiş).
Bu tasarımın parçası olarak eklenir:

- `services.postgres` → `pgvector/pgvector:pg16`, healthcheck.
- `DATABASE_URL` env → CI postgres.
- `pip install -e ".[dev]"` (sentence-transformers dahil; torch indirir).
- `pytest -m "not slow" -v` (model indirme yok, sadece torch kurulumu).
- HF cache adımı opsiyonel (slow testler CI'da koşmadığı için gerekmez).
- README'ye CI rozeti.

## Altyapı Değişiklikleri

- `docker-compose.yml`: `image: postgres:16-alpine` → `image: pgvector/pgvector:pg16`.
  Aynı PG16, `pgdata` volume uyumlu. `init_schema` extension'ı kurar.
- `pyproject.toml`:
  - `dependencies` += `sentence-transformers>=3.0`, `pgvector>=0.3`
  - `[tool.pytest.ini_options].markers` += `slow: gercek embedding modeli yukler`
- `Dockerfile`: zorunlu değişiklik yok. Opsiyonel: model'i build sırasında indiren
  `RUN python -c "from sentence_transformers import SentenceTransformer;
  SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"` katmanı — imaj
  şişer ama ilk istek hızlanır. İmplementasyonda karar verilir.

## Kapsam Dışı (YAGNI)

- Cross-encoder reranker (bi-encoder demo için yeterli).
- Ayarlanabilir RRF ağırlığı (RRF'de yok).
- HNSW parametre tuning (varsayılan).
- Sorgu sonucu cache'i.
- Baseline karşılaştırma ölçümü (iş #2, ayrı döngü).
- Trend analizi (iş #3, ayrı döngü).
- Deploy / CD (ayrı planlandı).

## Mühendislik Hikâyesi (mülakat)

"Sözlüksel FTS alaka sıralaması yapmıyordu; 'ürün kötü' sorgusu olumlu yorumları
getiriyordu. OR tsquery + sıralamasız LIMIT kombinasyonunu, lokal çok dilli
embedding modeliyle RRF üzerinden birleştiren hibrit aramayla değiştirdim.
Skorları normalize etme derdi olmadan sözlüksel recall'u semantik precision'la
birleştiriyor; lokal model deploy'da API kotasına takılmıyor."
