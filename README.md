# Review Evidence Engine

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

1. Anahtar kelime araması (SQLite FTS5) ile geniş bir aday küme bulunur —
   amaç isabet değil kapsama.
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
                                                    [SQLite + FTS5]
                                                          |
                              [search.keyword_search] -> aday yorumlar
                                                          |
                    [consensus.gemini_batch_classifier] -> toplu, paralel siniflandirma
                                                          |
                              [consensus.build_consensus] -> sayim + celiski + kaynaklar
```

### Kullanılan teknolojiler

Python, FastAPI, SQLite (FTS5 tam metin arama), Google Gemini API
(`gemini-flash-latest`, ücretsiz katman), `ThreadPoolExecutor` ile paralel
toplu sınıflandırma.

### Kurulum

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

`GEMINI_API_KEY` gerekiyor — [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
adresinden ücretsiz alınabilir. `.env.example` dosyasını `.env` olarak
kopyalayıp anahtarını gir.

### Veri yükleme

```powershell
.venv\Scripts\python.exe scripts\fetch_dataset.py
.venv\Scripts\python.exe -c "from pathlib import Path; from review_evidence.db import connect, init_schema; from review_evidence.ingest import load_reviews; from review_evidence.config import DB_PATH; conn = connect(DB_PATH); init_schema(conn); print(load_reviews(conn, Path('data/sample_reviews.json')))"
```

### Çalıştırma

```powershell
.venv\Scripts\python.exe -m uvicorn review_evidence.main:app --reload
```

API dokümanı: http://127.0.0.1:8000/docs

### Test

```powershell
.venv\Scripts\python.exe -m pytest -v
```

20 test, hepsi LLM çağrısını sahte (mock/injectable) bir sınıflandırıcıyla
test ediyor — gerçek API çağrısı gerektirmiyor, hızlı ve ücretsiz.

### Gelecek geliştirmeler

- Docker + PostgreSQL'e taşıma
- Anlamsal arama (embedding) ile hibrit arama, sadece anahtar kelime değil
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

1. Keyword search (SQLite FTS5) casts a wide net for candidates — the goal
   is coverage, not precision.
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
                                                    [SQLite + FTS5]
                                                          |
                              [search.keyword_search] -> candidate reviews
                                                          |
                    [consensus.gemini_batch_classifier] -> parallel batch classification
                                                          |
                              [consensus.build_consensus] -> counts + conflict + citations
```

### Tech stack

Python, FastAPI, SQLite (FTS5 full-text search), Google Gemini API
(`gemini-flash-latest`, free tier), `ThreadPoolExecutor` for parallel batch
classification.

### Setup

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Requires `GEMINI_API_KEY` — get one free at
[aistudio.google.com/apikey](https://aistudio.google.com/apikey). Copy
`.env.example` to `.env` and add your key.

### Loading data

```powershell
.venv\Scripts\python.exe scripts\fetch_dataset.py
.venv\Scripts\python.exe -c "from pathlib import Path; from review_evidence.db import connect, init_schema; from review_evidence.ingest import load_reviews; from review_evidence.config import DB_PATH; conn = connect(DB_PATH); init_schema(conn); print(load_reviews(conn, Path('data/sample_reviews.json')))"
```

### Run

```powershell
.venv\Scripts\python.exe -m uvicorn review_evidence.main:app --reload
```

API docs: http://127.0.0.1:8000/docs

### Test

```powershell
.venv\Scripts\python.exe -m pytest -v
```

20 tests, all exercising the LLM-calling code through an injectable fake
classifier — no live API calls needed, fast and free to run.

### Future work

- Docker + migrate to PostgreSQL
- Hybrid search (keyword + embeddings), not keyword-only
- Time-based sentiment shift detection (product/batch change signal)
- Comparative measurement against a plain-LLM-summary baseline
