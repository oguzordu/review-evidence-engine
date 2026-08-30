# Review Evidence Engine

[![CI](https://github.com/oguzordu/review-evidence-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/oguzordu/review-evidence-engine/actions/workflows/ci.yml)

## Türkçe

Ürün yorumları üzerinde **örnekleme değil sayım** yapan, her cevabını
dayandığı yorumları göstererek kuran bir soru-cevap servisi.

### Problem

Bir ürünün altında yüzlerce yorum var. "Pil gerçekten dayanıyor mu?" diye
sormak istiyorsun ama hepsini okuyamıyorsun.

Standart yorum özeti sistemleri — büyük e-ticaret sitelerinin kendi "AI
özeti" özellikleri dahil — birkaç benzer yorumu okuyup kendinden emin bir
cevap üretir. İlgili yorum sayısı okunanlardan fazlaysa, geri kalanı sessizce
görmezden gelinir. Amazon'un kendi AI özet özelliğinin, yorumların küçük bir
kesitine bakıp genel tabloyu yanlış yansıttığı raporlanmıştır.

### Yaklaşım

Bu servis ilgili yorumların **tamamını** tek tek değerlendirir, örnekleme
yapmaz:

1. Hibrit aramayla geniş bir aday küme bulunur — amaç isabet değil kapsama.
   PostgreSQL'in `turkish` tam metin araması (`ts_rank` ile alaka sırasına
   dizilir) ile lokal çok dilli embedding modelinin
   (`paraphrase-multilingual-MiniLM-L12-v2`) benzerlik araması, Reciprocal
   Rank Fusion (RRF) ile birleştirilir. Böylece sözlüksel eşleşmenin
   kaçırdığı ("berbat", "rezalet" gibi) yorumlar da girer. Embedding modeli
   yüklenemezse sistem otomatik olarak yalnızca anahtar kelime aramasına
   düşer.
2. Aday yorumlar gruplar hâlinde (paralel, toplu istekle) bir LLM'e
   (Gemini) gönderilip ilgili/ilgisiz ve olumlu/olumsuz olarak
   sınıflandırılır.
3. Sonuçlar sayılır, çelişki varsa gizlenmeden raporlanır, her sayı kaynak
   yorumlarla birlikte döner.

Gerçek örnek (canlı API'den, gerçek veriyle ölçüldü):

```
GET /products/p2/ask?question=urun kaliteli mi

102 aday bulundu, 35'i gercekten ilgili
   29 yorum: olumlu
    5 yorum: olumsuz
    1 yorum: belirsiz

   conflict: true  (goruslar celisiyor, sistem taraf tutmuyor)
```

### Veri kaynağı ve dürüst bir not

Kullanılan veri seti (`fthbrmnby/turkish_product_reviews`, HuggingFace,
235.165 gerçek Türkçe yorum) ürün ayrımı içermiyor — sadece düz
yorum+duygu etiketi var. `scripts/fetch_dataset.py` bu yorumlardan 1000
tanesini alıp **5 sentetik ürün grubuna** böler (`p1`..`p5`). Bu bilinçli
bir mühendislik kararı: gerçek ürün meta verisi olmadan, sistemin "ürün
başına toplu değerlendirme" mantığını gerçek, büyük ölçekli Türkçe yorum
metniyle göstermek için.

### Mimari

```
[fetch_dataset.py] -> [data/sample_reviews.json] -> [ingest.load_reviews]
                                                          |
                                                 [PostgreSQL + turkish FTS]
                                                          |
                              [search.keyword_search] -> aday yorumlar
                                                          |
                    [consensus.gemini_batch_classifier] -> toplu, paralel siniflandirma
                                                          |
                              [consensus.build_consensus] -> sayim + celiski + kaynaklar
```

### Kullanılan teknolojiler

Python, FastAPI, PostgreSQL (yerleşik `turkish` tam metin arama), Google Gemini API
(`gemini-flash-lite-latest`, ücretsiz katman), `ThreadPoolExecutor` ile paralel
toplu sınıflandırma.

### Kurulum

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

`GEMINI_API_KEY` gerekiyor — [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
adresinden ücretsiz alınabilir. `.env.example` dosyasını `.env` olarak
kopyalayıp anahtarını gir.

Veritabanı olarak **PostgreSQL** kullanılıyor (Türkçe tam metin arama için
yerleşik `turkish` dil yapılandırmasıyla). Yerel geliştirme için Docker
Compose ile ayağa kaldırılır:

```powershell
docker compose up -d db
```

### Docker ile tamamı (uygulama + veritabanı)

```powershell
docker compose up -d --build
```

Sonra `http://localhost:8000` adresinden erişilebilir.

İlk çalıştırmada embedding modeli (~120 MB) indirilir ve önbelleğe alınır.
pgvector sonradan eklendiği için, zaten yüklü yorumlara embedding üretmek
gerekirse:

```powershell
python scripts/backfill_embeddings.py
```

### Veri yükleme

```powershell
.venv\Scripts\python.exe scripts\fetch_dataset.py
.venv\Scripts\python.exe -c "from pathlib import Path; from review_evidence.db import connect, init_schema; from review_evidence.ingest import load_reviews; from review_evidence.config import DATABASE_URL; conn = connect(DATABASE_URL); init_schema(conn); print(load_reviews(conn, Path('data/sample_reviews.json')))"
```

### Çalıştırma (Docker'sız, sadece veritabanı konteynerle)

```powershell
docker compose up -d db
.venv\Scripts\python.exe -m uvicorn review_evidence.main:app --reload
```

API dokümanı: http://127.0.0.1:8000/docs

### Test

```powershell
docker compose up -d db
.venv\Scripts\python.exe -m pytest -v
```

23 test — metin/mantık testleri sahte (mock/injectable) bir sınıflandırıcıyla
çalışır (gerçek API çağrısı gerektirmez), veritabanı testleri ise **gerçek
PostgreSQL'e** karşı çalışır (Docker'ın ayakta olması gerekir). Bilinçli bir
tercih: SQLite ile test edip production'da PostgreSQL kullanmak, ikisi
arasındaki sözdizimi farklarını (örn. `?` vs `%s`, FTS5 vs `tsvector`)
gizleyip yanlış güven verirdi.

### Gelecek geliştirmeler

- Zaman bazlı eğilim değişimi tespiti (ürün/parti değişikliği sinyali)
- Baseline (düz LLM özeti) ile karşılaştırmalı ölçüm seti

---

## English

A Q&A service over product reviews that **counts instead of samples**, and
grounds every answer in the reviews it's based on.

### The problem

A product has hundreds of reviews. You want to ask "does the battery
actually last?" but you can't read them all.

Standard review-summary systems — including the "AI summary" features
shipped by major e-commerce platforms — read a handful of similar reviews
and generate a confident-sounding answer. When the relevant reviews outnumber
what the system actually reads, the rest are silently ignored. Amazon's own
AI review summaries have been reported to draw conclusions from a small
fraction of the available reviews, misrepresenting the overall picture.

### The approach

This service evaluates **every** relevant review individually instead of
sampling a handful:

1. Hybrid search casts a wide net for candidates — the goal is coverage, not
   precision. PostgreSQL's `turkish` full-text search (ranked by `ts_rank`) is
   fused with a local multilingual embedding model
   (`paraphrase-multilingual-MiniLM-L12-v2`) via Reciprocal Rank Fusion (RRF),
   so reviews that lexical matching misses ("berbat", "rezalet") are still
   picked up. If the embedding model fails to load, the system falls back to
   keyword-only search.
2. Candidates are sent to an LLM (Gemini) in parallel batches and
   classified as relevant/irrelevant and positive/negative.
3. Results are counted, conflicts are reported honestly, every number comes
   with its source reviews.

Real example (measured live against the actual API and real data):

```
GET /products/p2/ask?question=urun kaliteli mi

102 candidates found, 35 genuinely relevant
   29 reviews: positive
    5 reviews: negative
    1 review: unclear

   conflict: true  (opinions disagree, the system doesn't pick a side)
```

### Data source — an honest note

The dataset used (`fthbrmnby/turkish_product_reviews`, HuggingFace, 235,165
real Turkish reviews) has no product grouping — just flat review text with a
sentiment label. `scripts/fetch_dataset.py` takes 1,000 of these reviews and
buckets them into **5 synthetic product groups** (`p1`..`p5`). This is a
deliberate engineering tradeoff: without real product metadata, it's the
way to demonstrate the "per-product aggregate evaluation" logic against
real, large-scale Turkish review text.

### Architecture

```
[fetch_dataset.py] -> [data/sample_reviews.json] -> [ingest.load_reviews]
                                                          |
                                                 [PostgreSQL + turkish FTS]
                                                          |
                              [search.keyword_search] -> candidate reviews
                                                          |
                    [consensus.gemini_batch_classifier] -> parallel batch classification
                                                          |
                              [consensus.build_consensus] -> counts + conflict + citations
```

### Tech stack

Python, FastAPI, PostgreSQL (built-in `turkish` full-text search
configuration), Google Gemini API (`gemini-flash-lite-latest`, free tier),
`ThreadPoolExecutor` for parallel batch classification, Docker Compose.

### Setup

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Requires `GEMINI_API_KEY` — get one free at
[aistudio.google.com/apikey](https://aistudio.google.com/apikey). Copy
`.env.example` to `.env` and add your key.

Uses **PostgreSQL** (with the built-in `turkish` text search config). Start
it locally with Docker Compose:

```powershell
docker compose up -d db
```

### Full stack with Docker

```powershell
docker compose up -d --build
```

Then it's available at `http://localhost:8000`.

### Loading data

```powershell
.venv\Scripts\python.exe scripts\fetch_dataset.py
.venv\Scripts\python.exe -c "from pathlib import Path; from review_evidence.db import connect, init_schema; from review_evidence.ingest import load_reviews; from review_evidence.config import DATABASE_URL; conn = connect(DATABASE_URL); init_schema(conn); print(load_reviews(conn, Path('data/sample_reviews.json')))"
```

### Run (without Docker, just the DB container)

```powershell
docker compose up -d db
.venv\Scripts\python.exe -m uvicorn review_evidence.main:app --reload
```

API docs: http://127.0.0.1:8000/docs

### Test

```powershell
docker compose up -d db
.venv\Scripts\python.exe -m pytest -v
```

23 tests — text/logic tests run against an injectable fake classifier (no
live API calls needed), database tests run against a **real PostgreSQL**
instance (requires Docker running). Deliberate choice: testing against
SQLite while running PostgreSQL in production would hide real syntax
differences (e.g. `?` vs `%s`, FTS5 vs `tsvector`) behind false confidence.

### Future work

- Time-based sentiment shift detection (product/batch change signal)
- Comparative measurement against a plain-LLM-summary baseline
