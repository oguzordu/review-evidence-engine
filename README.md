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

### Ölçüm

Sayım yönteminin klasik RAG'a karşı farkı kontrollü bir sentetik set üzerinde
ölçüldü: [docs/benchmark-results.md](docs/benchmark-results.md). Kısaca — bilinen
sentiment dağılımına sahip bir sette, klasik RAG (K=8, tek LLM özeti) ilgili
yorumların çoğunu hiç görmediği için olumsuz sayısını sistematik olarak düşük
raporluyor; sayım yöntemi aynı sette hatasız sayıyor. Ölçümü tekrar üretmek için:
`python scripts/run_benchmark.py`.

### Canlı

**<https://92-4-163-43.sslip.io>**

Oracle Cloud Always Free ARM VM'de, Docker + Caddy (otomatik HTTPS) ile canlı;
`main`'e her push GitHub Actions ile otomatik deploy edilir. Kurulum: [docs/deploy.md](docs/deploy.md).

Canlıda **demo modu** açık: 5 ürün için önceden hesaplanmış soru-cevaplar anında
gösterilir (sıfır API maliyeti). Serbest sorular canlı çalışır ama Gemini ücretsiz
kotası (~20/gün) için günde ~15 çağrı + IP başına 2 ile sınırlıdır; kota dolunca
o ürün için hazır bir örnek gösterilir. Sınıflandırma hattının bütünü CI'daki
48 testle doğrulanır.

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

### Nasıl çalıştırılır

**En hızlısı — canlı demo:** yukarıdaki <https://92-4-163-43.sslip.io> linkine
git. "Hazır sorular" çipleri anında yanıt verir (önceden hesaplanmış, kota
harcamaz). Serbest soru da yazabilirsin — canlı çalışır, günlük ~15 çağrıyla
sınırlı.

**Lokalde çalıştırmak için** (Python 3.12+ ve Docker gerekir):

```powershell
# 1. bağımlılıklar
py -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"

# 2. Gemini API anahtarı (aistudio.google.com/apikey — ücretsiz)
copy .env.example .env
notepad .env                # GEMINI_API_KEY= satırını doldur, kaydet

# 3. veritabanı (pgvector'lü PostgreSQL, Docker konteyneri)
docker compose up -d db

# 4. veri setini indir + yükle (1000 Türkçe yorum + embedding — ilk sefer ~5 dk)
.venv\Scripts\python.exe scripts\fetch_dataset.py
.venv\Scripts\python.exe -c "from pathlib import Path; from review_evidence.db import connect, init_schema; from review_evidence.ingest import load_reviews; from review_evidence.config import DATABASE_URL; c = connect(DATABASE_URL); init_schema(c); print(load_reviews(c, Path('data/sample_reviews.json')))"

# 5. uygulamayı başlat
.venv\Scripts\python.exe -m uvicorn review_evidence.main:app --reload
```

Sonra tarayıcıda:

| Ne | Adres |
|---|---|
| Web arayüzü | <http://127.0.0.1:8000> |
| API dokümanı (Swagger) | <http://127.0.0.1:8000/docs> |
| Örnek sorgu | `http://127.0.0.1:8000/products/p1/ask?question=ürün kaliteli mi` |

İlk `/ask` çağrısında embedding modeli (~120 MB) iner. Lokalde `DEMO_MODE`
kapalıdır — her soru canlı Gemini ile çalışır (ücretsiz kota ~15-20/gün).
Ürünler `p1`–`p5`.

**Alternatif — her şeyi tek komutla Docker'da** (uygulama + DB birlikte):

```powershell
copy .env.example .env      # anahtarı doldur
docker compose up -d --build
```
→ <http://localhost:8000> (veriyi yine yukarıdaki 4. adımla yüklemen gerekir).

### Test

```powershell
docker compose up -d db
.venv\Scripts\python.exe -m pytest -v
```

48 test — metin/mantık testleri sahte (mock/injectable) bir sınıflandırıcı ve
sahte encoder'la çalışır (gerçek API çağrısı ve model indirmesi gerektirmez),
veritabanı testleri ise **ayrı bir test veritabanına** karşı çalışır (Docker'ın
ayakta olması gerekir; testler çalışan uygulamanın verisine dokunmaz).
`pytest -m slow` gerçek embedding modelini yükleyen 3 testi de çalıştırır.
Bilinçli bir tercih: SQLite ile test edip production'da PostgreSQL kullanmak,
tam metin arama ve `pgvector` gibi Postgres'e özgü davranışları gizleyip
yanlış güven verirdi.

### Gelecek geliştirmeler

- Zaman bazlı eğilim değişimi tespiti (ürün/parti değişikliği sinyali)

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

### Measurement

The counting method was measured against classic RAG on a controlled synthetic
set: [docs/benchmark-results.md](docs/benchmark-results.md). In short — on a set
with a known sentiment distribution, classic RAG (K=8, single LLM summary) never
sees most of the relevant reviews and so systematically under-reports the
negative count; the counting method gets the counts exactly right on the same
set. To reproduce: `python scripts/run_benchmark.py`.

### Live

**<https://92-4-163-43.sslip.io>**

Runs live on an Oracle Cloud Always Free ARM VM with Docker + Caddy (automatic
HTTPS); every push to `main` auto-deploys via GitHub Actions. Setup: [docs/deploy.md](docs/deploy.md).

**Demo mode** is on in production: precomputed Q&A for 5 products is served
instantly (zero API cost). Free-form questions run live but are capped at ~15
calls/day plus 2 per IP to fit the Gemini free tier (~20/day); when the cap is
hit, a precomputed sample for that product is shown. The full classification
pipeline is exercised by the 48-test CI suite.

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

### How to run it

**Fastest — the live demo:** open <https://92-4-163-43.sslip.io> above. The
preset question chips answer instantly (precomputed, no quota cost). Free-form
questions run live, capped at ~15 calls/day.

**To run locally** (needs Python 3.12+ and Docker):

```powershell
# 1. dependencies
py -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"

# 2. Gemini API key (aistudio.google.com/apikey — free)
copy .env.example .env
notepad .env                # fill in GEMINI_API_KEY=, save

# 3. database (PostgreSQL with pgvector, Docker container)
docker compose up -d db

# 4. fetch + load the dataset (1000 Turkish reviews + embeddings — ~5 min first time)
.venv\Scripts\python.exe scripts\fetch_dataset.py
.venv\Scripts\python.exe -c "from pathlib import Path; from review_evidence.db import connect, init_schema; from review_evidence.ingest import load_reviews; from review_evidence.config import DATABASE_URL; c = connect(DATABASE_URL); init_schema(c); print(load_reviews(c, Path('data/sample_reviews.json')))"

# 5. start the app
.venv\Scripts\python.exe -m uvicorn review_evidence.main:app --reload
```

Then in the browser:

| What | URL |
|---|---|
| Web UI | <http://127.0.0.1:8000> |
| API docs (Swagger) | <http://127.0.0.1:8000/docs> |
| Example query | `http://127.0.0.1:8000/products/p1/ask?question=ürün kaliteli mi` |

The first `/ask` call downloads the embedding model (~120 MB). Locally
`DEMO_MODE` is off — every question runs live against Gemini (free tier
~15-20/day). Products are `p1`–`p5`.

**Alternative — everything in Docker** (app + DB in one command):

```powershell
copy .env.example .env      # fill in the key
docker compose up -d --build
```
→ <http://localhost:8000> (still load the data via step 4 above).

### Test

```powershell
docker compose up -d db
.venv\Scripts\python.exe -m pytest -v
```

48 tests — text/logic tests run against an injectable fake classifier and a
fake encoder (no live API calls or model downloads needed), database tests run
against a **separate test database** (requires Docker running; tests never touch
the running app's data). `pytest -m slow` also runs the 3 tests that load the
real embedding model. Deliberate choice: testing against SQLite while running
PostgreSQL in production would hide Postgres-specific behavior (full-text search,
`pgvector`) behind false confidence.

### Future work

- Time-based sentiment shift detection (product/batch change signal)
