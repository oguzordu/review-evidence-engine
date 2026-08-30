# Baseline Karşılaştırma Ölçümü — Tasarım Dokümanı

> Tarih: 2026-08-31
> Durum: onaylandı, implementasyona hazır
> Branch: `baseline-olcum` (`hibrit-arama` üzerine kuruludur)

## Problem

Projenin ana iddiası: "örnekleme değil sayım". Klasik RAG en yakın birkaç yorumu
okuyup özet geçer; ilgili yorum sayısı okunanlardan fazlaysa gerisini sessizce
kaçırır. Şu ana kadar bu iddianın somut bir ölçümü yok (DEVİR notu, "dürüst
sınırlar"). Mülakat için en değerli parça bu ölçüm.

## Hedef

Kontrollü sentetik bir set üzerinde iki yöntemi ölç, farkı commit edilen bir
karşılaştırma tablosuyla göster:

- **Bizim yöntem:** hibrit arama → aday kümedeki HER yorumu batch LLM ile
  sınıflandır → say (`build_consensus`, mevcut).
- **Baseline (klasik RAG):** aynı hibrit aramadan top-K aday → tek LLM çağrısı
  "kaç olumlu kaç olumsuz" → say.

Ground truth = fixture'daki etiketlerin toplamı. Ayrı elle sayım yok.

## Kararlar

| Konu | Karar | Gerekçe |
|---|---|---|
| Baseline tanımı | Klasik RAG: aynı `hybrid_search` retrieval'ından top-K (K=8), tek LLM çağrısıyla özetle+say | Gerçek "AI özeti" özellikleri böyle çalışır. Aynı retrieval → adil karşılaştırma; tek fark toplama yöntemi. |
| Ground truth | Elle yazılmış statik fixture, her yorumda `relevant` + `sentiment` etiketi | Deterministik, offline, repo'da okunabilir. Ground truth = etiket toplamı. |
| Fixture boyutu | 2 vaka, her biri ~35 yorum; ilgili sayısı K=8'i belirgin aşar | Sayım açığını göstermeye yeter; cherry-pick şüphesini azaltmak için 2 vaka. |
| Metrik | Mutlak hata (olumlu/olumsuz sayımda) + baseline'ın kaçırdığı ilgili sayısı | Precision/recall/F1 eğrisi gereksiz; iki sayı hikâyeyi anlatıyor. |
| K taraması | Sadece K=8 | YAGNI. |

## Mimari

### Yeni modül: `src/review_evidence/benchmark.py`

HTTP katmanını bilmez. Enjekte edilebilir sınıflandırıcı deseni (`consensus.py`
ile aynı).

```python
class LabeledReview(TypedDict):
    text: str
    relevant: bool
    sentiment: str  # "positive" | "negative" | "unclear"

class Case(TypedDict):
    product_id: str
    question: str
    reviews: list[LabeledReview]

SummaryCounterFn = Callable[[str, list[str]], dict]
# (question, review_texts) -> {"positive": int, "negative": int, "unclear": int}
```

- `ground_truth(case: Case) -> dict`
  - `{"relevant": N, "positive": P, "negative": Q, "unclear": U}` — sadece
    `relevant=True` yorumlar sayılır, sentiment'lerine göre gruplanır.

- `gemini_summary_counter(client, model_name="gemini-flash-lite-latest") -> SummaryCounterFn`
  - **Tek** `generate_content` çağrısı. Prompt: numaralı yorumlar + "Soru: X.
    Kaç tanesi soruyla ilgili ve olumlu, kaç tanesi ilgili ve olumsuz, kaç
    tanesi belirsiz? SADECE JSON: {\"positive\": n, \"negative\": n,
    \"unclear\": n}".
  - `consensus.py`'deki 429 retry mantığı (MAX_RETRIES, RETRY_DELAY_SECONDS) ve
    ```json fence temizleme + `json.loads` guard'ı aynen kullanılır.
  - Başarısızlıkta `{"positive": 0, "negative": 0, "unclear": 0}` döner
    (çağıran taraf `error` işaretler).

- `baseline_rag(conn, product_id, question, count_summary, encode=None, k=8) -> dict`
  - `candidates = hybrid_search(conn, product_id, question, encode, limit=k)`
  - `texts = [row["raw_text"] for row in candidates]`
  - `counts = count_summary(question, texts)`
  - Döner: `{"method": "baseline_rag", "reviews_seen": len(texts),
    "positive_count": counts["positive"], "negative_count": counts["negative"],
    "unclear_count": counts["unclear"]}`

- `run_case(conn, case, our_method, baseline_method) -> dict`
  - `our_method` ve `baseline_method` imzası: `() -> dict` (çağıran taraf
    `conn/product_id/question`'ı bağlar). İkisi de en az `positive_count`,
    `negative_count` anahtarları döndürür; bizimki ayrıca `relevant_count`,
    baseline ayrıca `reviews_seen`.
  - `gt = ground_truth(case)`
  - Döner:
    ```python
    {
      "question": case["question"],
      "product_id": case["product_id"],
      "ground_truth": gt,
      "ours": {
        "relevant_count", "positive_count", "negative_count",
        "abs_error_positive": abs(ours.pos - gt.pos),
        "abs_error_negative": abs(ours.neg - gt.neg),
      },
      "baseline": {
        "reviews_seen", "positive_count", "negative_count",
        "abs_error_positive", "abs_error_negative",
        "missed_relevant": max(0, gt["relevant"] - reviews_seen),
      },
      "error": bool,  # baseline LLM cagrisi basarisiz olduysa
    }
    ```

- `format_report(results: list[dict], *, model_name: str, k: int) -> str`
  - Markdown başlık (ölçüm tarihi `date.today()`, model, K) + tablo:

    | Soru | Ground truth (ilgili/olumlu/olumsuz) | Bizim yöntem (olumlu/olumsuz, ±hata) | Baseline (gördüğü/olumlu/olumsuz, kaçırılan ilgili) |

  - Her satırın altına 1 cümle yorum (baseline kaç ilgili yorumu görmedi).

### Yeni fixture: `data/benchmark.json`

```json
{
  "cases": [
    {
      "product_id": "bench_pil",
      "question": "pil ömrü yeterli mi",
      "reviews": [
        {"text": "pili sabaha kadar zor dayanıyor, öğlen şarj şart", "relevant": true, "sentiment": "negative"},
        {"text": "tam gün idare ediyor, akşama %20 kalıyor", "relevant": true, "sentiment": "positive"},
        {"text": "kutusu ezikti ama içerik sağlam", "relevant": false, "sentiment": "unclear"}
      ]
    },
    { "product_id": "bench_kargo", "question": "kargo hızlı mı", "reviews": [ ... ] }
  ]
}
```

- Vaka başına ~35 yorum. `bench_pil`: hedef dağılım ~20 negative + ~8 positive
  + ~7 irrelevant. `bench_kargo` benzer.
- Cümleler elle yazılır, gerçek yorum tonunda, tekrar etmeyen. Türkçe.

### Yeni script: `scripts/run_benchmark.py`

1. `connect`, `init_schema`, `sentence_transformer_encoder()`, `genai.Client`.
2. `data/benchmark.json` yükle.
3. Cost uyarısı: "Bu çalışma vaka başına ~3-4 Gemini çağrısı yakar
   (toplam ~8). Günlük ücretsiz kota 20. Devam? [enter]" — `input()` ile.
4. Her vaka için:
   - `DELETE FROM reviews WHERE product_id = %s` (sadece `bench_*`).
   - Yorumları embedding'le yükle (`raw_text` = `text`, `clean_text` =
     `normalize(text)`, `created_at` = None).
   - `our_method = lambda: build_consensus(conn, pid, q,
     gemini_batch_classifier(client), encode)`
   - `baseline_method = lambda: baseline_rag(conn, pid, q,
     gemini_summary_counter(client), encode, k=8)`
   - `run_case(...)` → sonuç listesine ekle.
5. `report = format_report(results, model_name=..., k=8)` → stdout + üzerine
   yaz `docs/benchmark-results.md`.
6. `bench_*` satırlarını temizle (fixture verisi ana veriyle karışmasın —
   ama `bench_` önekiyle zaten izole; temizlik yine de yapılır).

### Test: `tests/test_benchmark.py`

Hepsi sahte (`db_conn` fixture'ı test veritabanı — iş #1'den). Gerçek LLM ve
gerçek embedding modeli yok.

- `test_ground_truth_sums_only_relevant_labels` — karışık etiketli case,
  beklenen `{relevant, positive, negative, unclear}`.
- `test_baseline_rag_only_sees_k_reviews` — 30 ilgili olumsuz seed, `k=8`,
  sahte `count_summary` gördüğü metinleri sayar → `reviews_seen == 8`,
  `negative_count <= 8`.
- `test_baseline_rag_uses_fake_encoder` — `encode` verilmezse keyword-only
  yolu (hybrid_search fallback) yine çalışır.
- `test_run_case_computes_errors` — sahte "mükemmel" our_method (ground
  truth'u aynen döndürür) → `abs_error_* == 0`; sahte "eksik" baseline →
  `abs_error` > 0 ve `missed_relevant > 0`.
- `test_format_report_contains_key_numbers` — çıktı string'i ground truth ve
  baseline sayılarını içeriyor, Markdown tablo işareti (`|`) var.
- `test_benchmark_fixture_is_valid` — `data/benchmark.json` parse oluyor,
  her `case` `product_id/question/reviews` içeriyor, her review
  `text/relevant/sentiment` içeriyor, sentiment ∈ {positive, negative, unclear}.

### Hata yönetimi

| Senaryo | Davranış |
|---|---|
| Baseline özet LLM çağrısı 429 | retry (consensus mantığı), sonra sıfır sayı + `run_case` sonucu `"error": true`; tablo satırı yıldızla işaretlenir, run devam eder |
| Bozuk JSON | `json.loads` guard → sıfır sayı, `error` |
| Bir vakada ilgili ≤ K | `missed_relevant == 0`; tabloda "baseline bu vakada zorlanmadı" notu; yine geçerli veri noktası |
| Bizim yöntem (Gemini batch) hatası | mevcut `consensus` davranışı — ilgisiz döner, değişmedi |

### LLM bütçesi

Vaka başına: bizim yöntem ~2-3 çağrı (35 aday / 20 batch) + baseline 1 çağrı ≈ 4.
2 vaka ≈ 8 çağrı. Bir tam benchmark koşusu günlük 20 kotaya sığar. Sonuç
commit edilir; script sık çalıştırılmaz.

### Çıktı artefaktı

`docs/benchmark-results.md` — commit edilir. README'deki "Gelecek geliştirmeler /
Future work" içindeki baseline maddesi silinip yerine kısa bir "Ölçüm" bölümü +
bu dosyaya link eklenir (TR ve EN).

## Kapsam Dışı (YAGNI)

- Precision / recall / F1 eğrileri, grafik.
- Çoklu K taraması (K=5, 15, ...).
- Baseline için ayrı retrieval varyantı — aynı `hybrid_search` kullanılır.
- LLM-üretilmiş fixture.
- Trend analizi (iş #3, ayrı döngü).

## Mühendislik Hikâyesi (mülakat)

"Sayım-tabanlı yöntemin klasik RAG'a karşı somut faydasını ölçtüm. Bilinen
sentiment dağılımına sahip sentetik bir set kurdum; klasik RAG (K=8, tek LLM
özeti) ilgili yorumların çoğunu fiziksel olarak göremediği için olumsuz sayısını
sistematik olarak düşük raporluyor. Aynı retrieval'ı kullanıp yalnızca toplama
yöntemini değiştirerek farkı izole ettim — sonuçlar `docs/benchmark-results.md`."
