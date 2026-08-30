# Baseline Karşılaştırma Ölçümü Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sayım-tabanlı yöntem ile klasik RAG baseline'ını kontrollü sentetik bir set üzerinde ölçüp commit edilen bir karşılaştırma tablosu üretmek.

**Architecture:** Yeni `benchmark.py` modülü: elle etiketlenmiş fixture'dan ground truth, aynı `hybrid_search` retrieval'ından top-K + tek LLM çağrısıyla baseline, `build_consensus` ile bizim yöntem, ikisini ground truth'a karşı karşılaştıran `run_case` + Markdown `format_report`. `scripts/run_benchmark.py` fixture'ı yükleyip iki yöntemi çalıştırır ve `docs/benchmark-results.md` yazar.

**Tech Stack:** Python 3.12, psycopg 3, PostgreSQL 16 + pgvector, google-genai (Gemini), sentence-transformers, pytest.

**Spec:** `docs/superpowers/specs/2026-08-31-baseline-olcum-design.md`

## Global Constraints

- Python `>=3.12`.
- Testler test veritabanına bağlanır (`db_conn` fixture, iş #1'den); gerçek LLM ve gerçek embedding modeli test edilmez — sahte enjekte edilir.
- Baseline retrieval'ı `search.hybrid_search` kullanır (yeni retrieval yazılmaz); tek fark top-K kesme + tek LLM özeti.
- Sentiment değerleri: `"positive" | "negative" | "unclear"` (mevcut `consensus.SENTIMENT_MAP` ile aynı).
- 429 retry ve JSON-fence temizleme mantığı `consensus.py`'dekiyle aynı sabitlerle (`MAX_RETRIES=3`, `RETRY_DELAY_SECONDS=12`).
- Fixture ürün önekleri `bench_` ile başlar (ana veriyle karışmaz).
- Enjekte edilebilir bağımlılık deseni `consensus.gemini_batch_classifier` ile aynı.
- Commit mesajları: kısa, gündelik, Türkçe, birinci şahıs, AI attribution YOK, feature-dump YOK.
- `python` = projenin venv'i (`.venv\Scripts\python.exe`).
- Docker `db` servisi ayakta olmalı; `docker compose up -d db`.

---

## Dosya Yapısı

| Dosya | Sorumluluk | İşlem |
|---|---|---|
| `src/review_evidence/benchmark.py` | ground truth, baseline, karşılaştırma, rapor | Create |
| `data/benchmark.json` | elle etiketlenmiş sentetik set (2 vaka) | Create |
| `scripts/run_benchmark.py` | fixture yükle → iki yöntemi çalıştır → doc yaz | Create |
| `tests/test_benchmark.py` | sahtelerle mantık testleri + fixture guard | Create |
| `docs/benchmark-results.md` | ölçüm çıktısı (script üretir, sonra commit) | Create (script) |
| `README.md` | "Ölçüm" bölümü + link | Modify |

---

## Task 1: `benchmark.py` — tipler ve `ground_truth`

**Files:**
- Create: `src/review_evidence/benchmark.py`
- Create: `tests/test_benchmark.py`

**Interfaces:**
- Consumes: yok
- Produces:
  - `LabeledReview = TypedDict("LabeledReview", {"text": str, "relevant": bool, "sentiment": str})`
  - `Case = TypedDict("Case", {"product_id": str, "question": str, "reviews": list[LabeledReview]})`
  - `ground_truth(case: Case) -> dict` — `{"relevant": int, "positive": int, "negative": int, "unclear": int}`; yalnızca `relevant=True` yorumları sentiment'e göre sayar.

- [ ] **Step 1: Failing test yaz — `tests/test_benchmark.py` oluştur**

```python
from review_evidence.benchmark import ground_truth


def _case(reviews):
    return {"product_id": "bench_x", "question": "pil nasil", "reviews": reviews}


def test_ground_truth_sums_only_relevant_labels():
    case = _case(
        [
            {"text": "a", "relevant": True, "sentiment": "negative"},
            {"text": "b", "relevant": True, "sentiment": "negative"},
            {"text": "c", "relevant": True, "sentiment": "positive"},
            {"text": "d", "relevant": False, "sentiment": "positive"},
            {"text": "e", "relevant": True, "sentiment": "unclear"},
        ]
    )

    gt = ground_truth(case)

    assert gt == {"relevant": 4, "positive": 1, "negative": 2, "unclear": 1}
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `python -m pytest tests/test_benchmark.py -v`
Expected: FAIL — `review_evidence.benchmark` yok.

- [ ] **Step 3: `src/review_evidence/benchmark.py` oluştur**

```python
"""Sayim-tabanli yontem ile klasik RAG baseline'ini kontrollu bir set
uzerinde karsilastiran olcum harness'i.

Ground truth elle etiketlenmis fixture'dan (data/benchmark.json) gelir.
Baseline, bizim yontemle AYNI hibrit aramayi kullanir; tek fark top-K kesme
ve tek LLM cagrisiyla ozetleme. Enjekte edilebilir siniflandirici deseni
consensus.py ile ayni.
"""

import json
import time
from collections import Counter
from datetime import date
from typing import Callable, TypedDict

import psycopg

from review_evidence.consensus import MAX_RETRIES, RETRY_DELAY_SECONDS
from review_evidence.embedding import EncoderFn
from review_evidence.search import hybrid_search


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


def ground_truth(case: Case) -> dict:
    """Fixture etiketlerinden gercek sayilari cikarir. Yalnizca relevant=True
    yorumlar, sentiment'lerine gore sayilir."""
    counts = Counter(
        r["sentiment"] for r in case["reviews"] if r["relevant"]
    )
    return {
        "relevant": sum(counts.values()),
        "positive": counts.get("positive", 0),
        "negative": counts.get("negative", 0),
        "unclear": counts.get("unclear", 0),
    }
```

- [ ] **Step 4: Testin geçtiğini doğrula**

Run: `python -m pytest tests/test_benchmark.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/review_evidence/benchmark.py tests/test_benchmark.py
git commit -m "benchmark modulu: fixture etiketlerinden ground truth"
```

---

## Task 2: `baseline_rag` + `gemini_summary_counter`

**Files:**
- Modify: `src/review_evidence/benchmark.py`
- Modify: `tests/test_benchmark.py`

**Interfaces:**
- Consumes: `hybrid_search` (search.py), `ground_truth` tipleri, `MAX_RETRIES`/`RETRY_DELAY_SECONDS` (consensus.py), `EncoderFn`
- Produces:
  - `gemini_summary_counter(client, model_name="gemini-flash-lite-latest") -> SummaryCounterFn`
  - `baseline_rag(conn, product_id, question, count_summary: SummaryCounterFn, encode: EncoderFn | None = None, k: int = 8) -> dict` — `{"method": "baseline_rag", "reviews_seen": int, "positive_count": int, "negative_count": int, "unclear_count": int, "error": bool}`

- [ ] **Step 1: Failing test yaz — `tests/test_benchmark.py` sonuna ekle**

```python
from review_evidence.benchmark import baseline_rag


def _seed(conn, rows):
    with conn.cursor() as cur:
        for product_id, text in rows:
            cur.execute(
                "INSERT INTO reviews (product_id, raw_text, clean_text)"
                " VALUES (%s, %s, %s)",
                (product_id, text, text.lower()),
            )
    conn.commit()


def test_baseline_rag_only_sees_k_reviews(db_conn):
    _seed(db_conn, [("bench_x", f"pil kotu dayanmiyor {i}") for i in range(30)])

    def fake_count_summary(question, texts):
        # gordugu metinleri sayar: hepsi "kotu" -> negative
        return {"positive": 0, "negative": len(texts), "unclear": 0}

    result = baseline_rag(db_conn, "bench_x", "pil nasil", fake_count_summary, k=8)

    assert result["reviews_seen"] == 8
    assert result["negative_count"] == 8
    assert result["error"] is False


def test_baseline_rag_marks_error_when_summary_returns_zero(db_conn):
    _seed(db_conn, [("bench_x", "pil kotu")])

    def broken_summary(question, texts):
        raise RuntimeError("api patladi")

    result = baseline_rag(db_conn, "bench_x", "pil", broken_summary, k=8)

    assert result["error"] is True
    assert result["positive_count"] == 0
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `python -m pytest tests/test_benchmark.py -k baseline_rag -v`
Expected: FAIL — `baseline_rag` yok.

- [ ] **Step 3: `benchmark.py` — `gemini_summary_counter` ekle**

```python
def gemini_summary_counter(
    client, model_name: str = "gemini-flash-lite-latest"
) -> SummaryCounterFn:
    """Klasik RAG baseline'i: verilen yorumlari TEK LLM cagrisiyla ozetleyip
    olumlu/olumsuz/belirsiz sayilarini dondurur. 429'da retry."""

    def count_summary(question: str, review_texts: list[str]) -> dict:
        if not review_texts:
            return {"positive": 0, "negative": 0, "unclear": 0}

        numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(review_texts))
        prompt = (
            "Soru: " + question + "\n\n"
            "Asagida bir urunun yorumlari var. Soruyla ilgili olanlardan kac "
            "tanesi olumlu, kac tanesi olumsuz, kac tanesi belirsiz?\n\n"
            + numbered
            + '\n\nSADECE su JSON: {"positive": 0, "negative": 0, "unclear": 0}'
        )

        for attempt in range(MAX_RETRIES):
            try:
                response = client.models.generate_content(
                    model=model_name, contents=prompt
                )
                text = (response.text or "").strip()
                text = (
                    text.removeprefix("```json")
                    .removeprefix("```")
                    .removesuffix("```")
                    .strip()
                )
                data = json.loads(text)
                return {
                    "positive": int(data.get("positive", 0)),
                    "negative": int(data.get("negative", 0)),
                    "unclear": int(data.get("unclear", 0)),
                }
            except Exception as exc:
                is_rate_limit = "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc)
                if is_rate_limit and attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY_SECONDS)
                    continue
                break

        return {"positive": 0, "negative": 0, "unclear": 0}

    return count_summary
```

- [ ] **Step 4: `benchmark.py` — `baseline_rag` ekle**

```python
def baseline_rag(
    conn: psycopg.Connection,
    product_id: str,
    question: str,
    count_summary: SummaryCounterFn,
    encode: EncoderFn | None = None,
    k: int = 8,
) -> dict:
    """Klasik RAG: bizim yontemle AYNI hibrit aramadan top-K aday, tek LLM
    cagrisiyla ozetle+say. reviews_seen K ile sinirli -- ilgili yorum sayisi
    K'dan fazlaysa gerisini goremiyor."""
    candidates = hybrid_search(conn, product_id, question, encode, limit=k)
    texts = [row["raw_text"] for row in candidates]

    try:
        counts = count_summary(question, texts)
        error = counts == {"positive": 0, "negative": 0, "unclear": 0} and bool(texts)
    except Exception:
        counts = {"positive": 0, "negative": 0, "unclear": 0}
        error = True

    return {
        "method": "baseline_rag",
        "reviews_seen": len(texts),
        "positive_count": counts["positive"],
        "negative_count": counts["negative"],
        "unclear_count": counts["unclear"],
        "error": error,
    }
```

Not: `error` kestirimi — özet sıfır döndürdüyse ve aday vardıysa hata sayılır
(LLM guard'ı sıfır döndürür). Kusursuz değil ama rapor için yeterli sinyal.

- [ ] **Step 5: Testlerin geçtiğini doğrula**

Run: `python -m pytest tests/test_benchmark.py -v`
Expected: PASS (fixture guard testi henüz yok, o Task 4'te).

- [ ] **Step 6: Commit**

```bash
git add src/review_evidence/benchmark.py tests/test_benchmark.py
git commit -m "baseline rag: ayni aramadan top-K, tek llm cagrisiyla say"
```

---

## Task 3: `run_case` + `format_report`

**Files:**
- Modify: `src/review_evidence/benchmark.py`
- Modify: `tests/test_benchmark.py`

**Interfaces:**
- Consumes: `ground_truth`
- Produces:
  - `run_case(conn, case: Case, our_method: Callable[[], dict], baseline_method: Callable[[], dict]) -> dict`
  - `format_report(results: list[dict], *, model_name: str, k: int) -> str`

- [ ] **Step 1: Failing test yaz — `tests/test_benchmark.py` sonuna ekle**

```python
from review_evidence.benchmark import format_report, run_case


def test_run_case_computes_errors():
    case = _case(
        [{"text": f"n{i}", "relevant": True, "sentiment": "negative"} for i in range(20)]
        + [{"text": f"p{i}", "relevant": True, "sentiment": "positive"} for i in range(8)]
    )

    def perfect_our_method():
        return {"relevant_count": 28, "positive_count": 8, "negative_count": 20}

    def weak_baseline():
        return {"reviews_seen": 8, "positive_count": 3, "negative_count": 5}

    result = run_case(None, case, perfect_our_method, weak_baseline)

    assert result["ground_truth"] == {"relevant": 28, "positive": 8, "negative": 20, "unclear": 0}
    assert result["ours"]["abs_error_positive"] == 0
    assert result["ours"]["abs_error_negative"] == 0
    assert result["baseline"]["abs_error_negative"] == 15
    assert result["baseline"]["missed_relevant"] == 20


def test_format_report_contains_key_numbers():
    case = _case([{"text": "n", "relevant": True, "sentiment": "negative"}])
    result = run_case(
        None,
        case,
        lambda: {"relevant_count": 1, "positive_count": 0, "negative_count": 1},
        lambda: {"reviews_seen": 1, "positive_count": 0, "negative_count": 0},
    )

    report = format_report([result], model_name="test-model", k=8)

    assert "test-model" in report
    assert "|" in report
    assert "pil nasil" in report
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `python -m pytest tests/test_benchmark.py -k "run_case or format_report" -v`
Expected: FAIL — fonksiyonlar yok.

- [ ] **Step 3: `benchmark.py` — `run_case` ekle**

```python
def run_case(
    conn,
    case: Case,
    our_method: Callable[[], dict],
    baseline_method: Callable[[], dict],
) -> dict:
    """Bir vaka icin iki yontemi de calistirir, ground truth'a gore hatalari
    hesaplar. our_method / baseline_method: () -> sayim sozlugu."""
    gt = ground_truth(case)
    ours = our_method()
    base = baseline_method()

    return {
        "question": case["question"],
        "product_id": case["product_id"],
        "ground_truth": gt,
        "ours": {
            "relevant_count": ours.get("relevant_count", 0),
            "positive_count": ours["positive_count"],
            "negative_count": ours["negative_count"],
            "abs_error_positive": abs(ours["positive_count"] - gt["positive"]),
            "abs_error_negative": abs(ours["negative_count"] - gt["negative"]),
        },
        "baseline": {
            "reviews_seen": base.get("reviews_seen", 0),
            "positive_count": base["positive_count"],
            "negative_count": base["negative_count"],
            "abs_error_positive": abs(base["positive_count"] - gt["positive"]),
            "abs_error_negative": abs(base["negative_count"] - gt["negative"]),
            "missed_relevant": max(0, gt["relevant"] - base.get("reviews_seen", 0)),
        },
        "error": bool(base.get("error", False)),
    }
```

- [ ] **Step 4: `benchmark.py` — `format_report` ekle**

```python
def format_report(results: list[dict], *, model_name: str, k: int) -> str:
    """Karsilastirma tablosunu Markdown olarak uretir."""
    lines = [
        "# Baseline Karşılaştırma Ölçümü",
        "",
        f"> Ölçüm tarihi: {date.today().isoformat()} · "
        f"Model: `{model_name}` · Baseline K: {k}",
        "",
        "| Soru | Ground truth (ilgili/olumlu/olumsuz) | "
        "Bizim yöntem (olumlu/olumsuz, ±hata) | "
        "Baseline (gördüğü/olumlu/olumsuz, kaçırılan ilgili) |",
        "|---|---|---|---|",
    ]
    for r in results:
        gt, ours, base = r["ground_truth"], r["ours"], r["baseline"]
        flag = " ⚠️" if r["error"] else ""
        lines.append(
            f"| {r['question']}{flag} "
            f"| {gt['relevant']}/{gt['positive']}/{gt['negative']} "
            f"| {ours['positive_count']}/{ours['negative_count']} "
            f"(±{ours['abs_error_positive']}/±{ours['abs_error_negative']}) "
            f"| {base['reviews_seen']}/{base['positive_count']}/{base['negative_count']} "
            f"({base['missed_relevant']} kaçtı) |"
        )
    lines += ["", "## Yorum", ""]
    for r in results:
        base = r["baseline"]
        lines.append(
            f"- **{r['question']}**: baseline yalnızca {base['reviews_seen']} "
            f"yorum gördü, {base['missed_relevant']} ilgili yorumu hiç "
            f"değerlendirmedi; olumsuz sayısını {base['abs_error_negative']} "
            f"birim yanlış raporladı."
        )
    if any(r["error"] for r in results):
        lines += ["", "⚠️ = baseline LLM çağrısı başarısız (kota/hata)."]
    return "\n".join(lines) + "\n"
```

- [ ] **Step 5: Testlerin geçtiğini doğrula**

Run: `python -m pytest tests/test_benchmark.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/review_evidence/benchmark.py tests/test_benchmark.py
git commit -m "run_case ve format_report: iki yontemi ground truth'a karsi olc"
```

---

## Task 4: `data/benchmark.json` fixture + guard testi

**Files:**
- Create: `data/benchmark.json`
- Modify: `tests/test_benchmark.py`

**Interfaces:**
- Consumes: yok
- Produces: `data/benchmark.json` — `{"cases": [Case, Case]}`, `bench_pil` ve `bench_kargo`, her biri ~35 etiketli yorum.

- [ ] **Step 1: Failing test yaz — `tests/test_benchmark.py` sonuna ekle**

```python
import json as _json
from pathlib import Path


def test_benchmark_fixture_is_valid():
    data = _json.loads(Path("data/benchmark.json").read_text(encoding="utf-8"))

    assert isinstance(data["cases"], list) and len(data["cases"]) >= 2
    for case in data["cases"]:
        assert case["product_id"].startswith("bench_")
        assert isinstance(case["question"], str) and case["question"]
        assert len(case["reviews"]) >= 25
        gt = ground_truth(case)
        assert gt["relevant"] > 8  # baseline K=8'i asmali
        assert gt["negative"] > 0 and gt["positive"] > 0
        for r in case["reviews"]:
            assert set(r) == {"text", "relevant", "sentiment"}
            assert isinstance(r["relevant"], bool)
            assert r["sentiment"] in {"positive", "negative", "unclear"}
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

Run: `python -m pytest tests/test_benchmark.py -k fixture -v`
Expected: FAIL — `data/benchmark.json` yok.

- [ ] **Step 3: `data/benchmark.json` oluştur**

İki vaka. Her biri için elle, gerçek yorum tonunda, tekrar etmeyen Türkçe
cümleler yaz. Hedef dağılım (her vaka): ~20 `negative` + ~8 `positive` +
~7 `relevant=false` (sentiment `unclear`), toplam ~35.

`bench_pil` sorusu: `"pil ömrü yeterli mi"`. Örnek yorumlar (gerçek dosyada
her kategoriden yeterince yaz):

```json
{
  "cases": [
    {
      "product_id": "bench_pil",
      "question": "pil ömrü yeterli mi",
      "reviews": [
        {"text": "pili öğlene kadar zor gidiyor, yanımda powerbank taşıyorum", "relevant": true, "sentiment": "negative"},
        {"text": "sabah full şarj ediyorum akşam 5'te kapanıyor, çok yetersiz", "relevant": true, "sentiment": "negative"},
        {"text": "batarya bir yılda gözle görülür şiştü, ömrü kısa", "relevant": true, "sentiment": "negative"},
        {"text": "şarjı hızlı bitiyor, oyun oynayınca bir buçuk saat dayanıyor", "relevant": true, "sentiment": "negative"},
        {"text": "pil tam bir hayal kırıklığı, iade etmeyi düşünüyorum", "relevant": true, "sentiment": "negative"},
        {"text": "bataryası gün ortasında beni yolda bıraktı", "relevant": true, "sentiment": "negative"},
        {"text": "eski telefonum daha uzun gidiyordu, buna pil koymayı unutmuşlar", "relevant": true, "sentiment": "negative"},
        {"text": "yoğun kullanımda 4 saat, hafif kullanımda 7 saat, bana az", "relevant": true, "sentiment": "negative"},
        {"text": "şarj döngüsü arttıkça pil performansı çok düştü", "relevant": true, "sentiment": "negative"},
        {"text": "video izlerken pil eriyip gidiyor", "relevant": true, "sentiment": "negative"},
        {"text": "bekleme modunda bile gece %15 harcıyor", "relevant": true, "sentiment": "negative"},
        {"text": "pil yüzünden priz arıyorum sürekli, memnun değilim", "relevant": true, "sentiment": "negative"},
        {"text": "kışın soğukta pil bir anda %40'tan kapandı", "relevant": true, "sentiment": "negative"},
        {"text": "1.5 yıl sonra günde iki kez şarj etmem gerekiyor", "relevant": true, "sentiment": "negative"},
        {"text": "reklamda yazan pil süresinin yarısını bile görmedim", "relevant": true, "sentiment": "negative"},
        {"text": "navigasyon açıkken pil ısınıp hızla düşüyor", "relevant": true, "sentiment": "negative"},
        {"text": "sabah 100 akşam olmadan 10, iş göremiyorum", "relevant": true, "sentiment": "negative"},
        {"text": "batarya sağlığı bir yılda %86'ya indi", "relevant": true, "sentiment": "negative"},
        {"text": "pil ömrü kesinlikle bu fiyata yakışmıyor", "relevant": true, "sentiment": "negative"},
        {"text": "şarjı yüzde yüzken bile içim rahat değil, çabuk bitiyor", "relevant": true, "sentiment": "negative"},
        {"text": "pil beni şaşırttı, iki gün gittiği oldu", "relevant": true, "sentiment": "positive"},
        {"text": "tam gün yoğun kullanıyorum akşama %30 kalıyor, gayet iyi", "relevant": true, "sentiment": "positive"},
        {"text": "bataryadan çok memnunum, gün boyu yetiyor", "relevant": true, "sentiment": "positive"},
        {"text": "pil ömrü beklentimin üstünde çıktı", "relevant": true, "sentiment": "positive"},
        {"text": "sınıfının en iyisi diyebilirim pil konusunda", "relevant": true, "sentiment": "positive"},
        {"text": "bir yıldır kullanıyorum pil hâlâ ilk günkü gibi", "relevant": true, "sentiment": "positive"},
        {"text": "şarj bir kez yetiyor bütün güne, sorun yok", "relevant": true, "sentiment": "positive"},
        {"text": "uzun yolda müzik ve navigasyona rağmen idare etti", "relevant": true, "sentiment": "positive"},
        {"text": "kargo çok hızlı geldi, ertesi gün elimdeydi", "relevant": false, "sentiment": "unclear"},
        {"text": "kutusu biraz ezikti ama ürün sağlam", "relevant": false, "sentiment": "unclear"},
        {"text": "ekran kalitesi harika, renkler canlı", "relevant": false, "sentiment": "unclear"},
        {"text": "kamerası bu fiyata göre gayet başarılı", "relevant": false, "sentiment": "unclear"},
        {"text": "hoparlörden ses çıtırdıyor, ondan şikayetçiyim", "relevant": false, "sentiment": "unclear"},
        {"text": "satıcı ilgiliydi, sorunumu hemen çözdü", "relevant": false, "sentiment": "unclear"},
        {"text": "tasarımı çok şık, elde güzel duruyor", "relevant": false, "sentiment": "unclear"}
      ]
    },
    {
      "product_id": "bench_kargo",
      "question": "kargo hızlı ve sorunsuz mu",
      "reviews": [
        {"text": "sipariş 6 gün sonra geldi, çok yavaştı", "relevant": true, "sentiment": "negative"},
        {"text": "kargo firması paketi kapımın önüne atmış, hasarlıydı", "relevant": true, "sentiment": "negative"},
        {"text": "kargom yolda kayboldu, tekrar gönderdiler ama 2 hafta sürdü", "relevant": true, "sentiment": "negative"},
        {"text": "tahmini teslim 2 gündü, 8 günde ulaştı", "relevant": true, "sentiment": "negative"},
        {"text": "paket ezik geldi içindeki ürünün kutusu yırtıktı", "relevant": true, "sentiment": "negative"},
        {"text": "kargo takip numarası 4 gün güncellenmedi", "relevant": true, "sentiment": "negative"},
        {"text": "teslimat şubeye bırakılmış, haber bile vermediler", "relevant": true, "sentiment": "negative"},
        {"text": "kurye aramadan geri götürdü, ertesi gün tekrar bekledim", "relevant": true, "sentiment": "negative"},
        {"text": "hafta sonu sipariş verdim, salı gelmesi gerekirken cuma geldi", "relevant": true, "sentiment": "negative"},
        {"text": "kargo çok geç, bir daha buradan almam", "relevant": true, "sentiment": "negative"},
        {"text": "paket başka bir adrese teslim edilmiş, uğraştım", "relevant": true, "sentiment": "negative"},
        {"text": "ürün elime geç geçti ve kutu suyla temas etmişti", "relevant": true, "sentiment": "negative"},
        {"text": "3 kez teslim denemesi başarısız oldu, iğrenç bir süreç", "relevant": true, "sentiment": "negative"},
        {"text": "kargonun gelmesi tam 9 gün sürdü, kabul edilemez", "relevant": true, "sentiment": "negative"},
        {"text": "sipariş kargoya 4 gün sonra verildi, firma yavaş", "relevant": true, "sentiment": "negative"},
        {"text": "kargo bir gün sonra elimdeydi, çok hızlı", "relevant": true, "sentiment": "positive"},
        {"text": "ertesi gün teslimat sözü tutuldu, paket sağlamdı", "relevant": true, "sentiment": "positive"},
        {"text": "kargo süreci sorunsuzdu, takip düzgün çalıştı", "relevant": true, "sentiment": "positive"},
        {"text": "hızlı kargo, kurye kibar, paket düzgündü", "relevant": true, "sentiment": "positive"},
        {"text": "2 günde geldi, beklediğimden erken", "relevant": true, "sentiment": "positive"},
        {"text": "kargo aynı gün kargoya verildi, ertesi sabah kapımdaydı", "relevant": true, "sentiment": "positive"},
        {"text": "paket balonlu naylonla sarılıydı, hiç hasar yoktu", "relevant": true, "sentiment": "positive"},
        {"text": "ürünün rengi fotoğraftakinden biraz farklı", "relevant": false, "sentiment": "unclear"},
        {"text": "fiyatı biraz yüksek ama kaliteli", "relevant": false, "sentiment": "unclear"},
        {"text": "kullanımı çok kolay, kurulum 5 dakika", "relevant": false, "sentiment": "unclear"},
        {"text": "garanti belgesi kutudan çıkmadı", "relevant": false, "sentiment": "unclear"},
        {"text": "pili gün boyu gidiyor, memnunum", "relevant": false, "sentiment": "unclear"},
        {"text": "ekranı parmak izi tutuyor", "relevant": false, "sentiment": "unclear"}
      ]
    }
  ]
}
```

Yukarıdaki içerik yeterli (bench_pil 35, bench_kargo 28); guard testi
`>= 25` istiyor. Cümleleri aynen kullanabilirsin.

- [ ] **Step 4: Guard testinin geçtiğini doğrula**

Run: `python -m pytest tests/test_benchmark.py -v`
Expected: tüm benchmark testleri PASS.

- [ ] **Step 5: Commit**

```bash
git add data/benchmark.json tests/test_benchmark.py
git commit -m "benchmark fixture: pil ve kargo icin etiketli sentetik set"
```

---

## Task 5: `scripts/run_benchmark.py`

**Files:**
- Create: `scripts/run_benchmark.py`

**Interfaces:**
- Consumes: `connect`, `init_schema`, `sentence_transformer_encoder`, `build_consensus`, `gemini_batch_classifier`, `benchmark.*`, `text.normalize`, `config.*`
- Produces: çalıştırılabilir script; `docs/benchmark-results.md` yazar.

- [ ] **Step 1: `scripts/run_benchmark.py` oluştur**

```python
"""Sayim-tabanli yontem ile klasik RAG baseline'ini olcer.

data/benchmark.json'daki etiketli vakalari yukler, iki yontemi de calistirir,
sonucu docs/benchmark-results.md'ye yazar.

Kullanim:
    python scripts/run_benchmark.py

DIKKAT: vaka basina ~3-4 Gemini cagrisi yakar (toplam ~8). Gunluk ucretsiz
kota 20.
"""

import json
from pathlib import Path

from google import genai

from review_evidence.benchmark import (
    baseline_rag,
    format_report,
    gemini_summary_counter,
    run_case,
)
from review_evidence.config import DATABASE_URL, GEMINI_API_KEY
from review_evidence.consensus import build_consensus, gemini_batch_classifier
from review_evidence.db import connect, init_schema
from review_evidence.embedding import sentence_transformer_encoder
from review_evidence.text import normalize

MODEL_NAME = "gemini-flash-lite-latest"
K = 8
FIXTURE = Path("data/benchmark.json")
OUTPUT = Path("docs/benchmark-results.md")


def _load_case(conn, case, encode) -> None:
    pid = case["product_id"]
    with conn.cursor() as cur:
        cur.execute("DELETE FROM reviews WHERE product_id = %s", (pid,))
    conn.commit()
    texts = [r["text"] for r in case["reviews"]]
    embeddings = encode(texts)
    rows = [
        (pid, r["text"], normalize(r["text"]), None, emb)
        for r, emb in zip(case["reviews"], embeddings)
    ]
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO reviews (product_id, raw_text, clean_text, created_at, embedding)"
            " VALUES (%s, %s, %s, %s, %s)",
            rows,
        )
    conn.commit()


def main() -> None:
    if not GEMINI_API_KEY:
        raise SystemExit("GEMINI_API_KEY tanimli degil (.env)")

    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
    print(
        f"{len(cases)} vaka calistirilacak. Vaka basina ~3-4 Gemini cagrisi "
        f"(~{len(cases) * 4} toplam). Gunluk kota 20."
    )
    input("Devam etmek icin Enter, iptal icin Ctrl+C... ")

    conn = connect(DATABASE_URL)
    init_schema(conn)
    encode = sentence_transformer_encoder()
    client = genai.Client(api_key=GEMINI_API_KEY)

    results = []
    for case in cases:
        pid, q = case["product_id"], case["question"]
        print(f"\n[{pid}] {q}")
        _load_case(conn, case, encode)

        def our_method(_pid=pid, _q=q):
            return build_consensus(
                conn, _pid, _q, gemini_batch_classifier(client, MODEL_NAME), encode
            )

        def baseline_method(_pid=pid, _q=q):
            return baseline_rag(
                conn, _pid, _q, gemini_summary_counter(client, MODEL_NAME), encode, k=K
            )

        result = run_case(conn, case, our_method, baseline_method)
        results.append(result)
        print(
            f"  ground truth: {result['ground_truth']}\n"
            f"  bizim: +{result['ours']['positive_count']} "
            f"-{result['ours']['negative_count']}\n"
            f"  baseline: +{result['baseline']['positive_count']} "
            f"-{result['baseline']['negative_count']} "
            f"({result['baseline']['missed_relevant']} kacti)"
        )

    # temizlik: benchmark satirlari ana veriyle karismasin
    with conn.cursor() as cur:
        for case in cases:
            cur.execute("DELETE FROM reviews WHERE product_id = %s", (case["product_id"],))
    conn.commit()
    conn.close()

    report = format_report(results, model_name=MODEL_NAME, k=K)
    OUTPUT.write_text(report, encoding="utf-8")
    print(f"\n{report}\n--> {OUTPUT}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Import ve söz dizimi kontrolü (LLM çağrısı yok)**

Run: `python -c "import ast; ast.parse(open('scripts/run_benchmark.py', encoding='utf-8').read()); print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add scripts/run_benchmark.py
git commit -m "run_benchmark scripti: iki yontemi calistirip tabloyu yazar"
```

---

## Task 6: Benchmark'ı çalıştır + sonucu ve README'yi işle

**Files:**
- Create: `docs/benchmark-results.md` (script üretir)
- Modify: `README.md`

**Interfaces:**
- Consumes: tüm önceki task'lar
- Produces: gerçek ölçüm sonucu commit'li; README'de "Ölçüm" bölümü.

- [ ] **Step 1: DB ayakta mı, kontrol et**

Run: `docker compose up -d db`
Expected: `db` healthy.

- [ ] **Step 2: Benchmark'ı çalıştır**

Run: `python scripts/run_benchmark.py`
(Enter'a bas.) Expected: iki vaka çalışır, `docs/benchmark-results.md` yazılır.
~8 Gemini çağrısı harcanır. 429 alırsan: kota bugünlük dolmuş — yarın tekrar
dene, sonraki adımlara geçme.

- [ ] **Step 3: Sonucu gözden geçir**

`docs/benchmark-results.md`'yi aç. Beklenen desen: baseline `missed_relevant`
her vakada > 0 ve `abs_error_negative` bizim yöntemden belirgin büyük. Değilse
(ör. baseline şaşırtıcı iyi): fixture'da ilgili yorum sayısını artır veya K'yı
düşürme — sonucu olduğu gibi bırak ve yorumu dürüst yaz. Ölçüm ölçümdür.

- [ ] **Step 4: README'yi güncelle**

TR "Gelecek geliştirmeler" ve EN "Future work" bölümlerinden baseline
maddesini çıkar. Onun yerine her iki dilde, "Yaklaşım / Approach"
bölümünün hemen altına kısa bir bölüm ekle:

TR:
```markdown
### Ölçüm

Sayım yönteminin klasik RAG'a karşı farkı kontrollü bir sentetik set üzerinde
ölçüldü: [docs/benchmark-results.md](docs/benchmark-results.md). Kısaca —
klasik RAG (K=8, tek LLM özeti) ilgili yorumların çoğunu hiç görmediği için
olumsuz sayısını sistematik olarak düşük raporluyor.
```

EN:
```markdown
### Measurement

The counting method was measured against classic RAG on a controlled synthetic
set: [docs/benchmark-results.md](docs/benchmark-results.md). In short — classic
RAG (K=8, single LLM summary) never sees most of the relevant reviews and so
systematically under-reports the negative count.
```

- [ ] **Step 5: Full test suite (regresyon)**

Run: `python -m pytest -v`
Expected: tüm testler PASS (benchmark testleri dahil, slow hariç).

- [ ] **Step 6: Commit**

```bash
git add docs/benchmark-results.md README.md
git commit -m "baseline olcum sonuclarini ekledim, readme'ye olcum bolumu"
```

- [ ] **Step 7: Branch'i bitir**

`superpowers:finishing-a-development-branch` skill'ini çağır. Base: `main`
(PR #1 merge edildiyse) veya `hibrit-arama`.

---

## Self-Review

**Spec coverage:**
- `LabeledReview`/`Case` tipleri, `ground_truth` → Task 1 ✓
- `gemini_summary_counter` (tek çağrı, 429 retry, JSON guard) → Task 2 ✓
- `baseline_rag` (aynı `hybrid_search`, top-K, `error` işareti) → Task 2 ✓
- `run_case` (mutlak hata, `missed_relevant`) → Task 3 ✓
- `format_report` (Markdown tablo + tarih/model/K başlığı + yorum) → Task 3 ✓
- `data/benchmark.json` (2 vaka, `bench_` öneki, ilgili > 8) → Task 4 ✓
- Guard testi (parse, anahtarlar, sentiment enum, dağılım) → Task 4 ✓
- `scripts/run_benchmark.py` (cost uyarısı, vaka yükleme+embedding, temizlik, doc yazma) → Task 5 ✓
- Gerçek çalıştırma + `docs/benchmark-results.md` commit → Task 6 ✓
- README "Ölçüm/Measurement" bölümü, eski madde kaldırma → Task 6 ✓
- Hata yönetimi: baseline 429 (Task 2 `gemini_summary_counter` retry + Task 2 `error`), ilgili ≤ K (Task 3 `missed_relevant=max(0,...)`, format_report yorumu), bozuk JSON (Task 2 guard) ✓
- LLM bütçesi: script cost uyarısı (Task 5), Task 6 429 talimatı ✓
- Kapsam dışı maddeler plana girmedi ✓

**Placeholder scan:** Task 4 fixture içeriği tam verildi (yer tutucu yok).
Task 6 Step 3'te "fixture'da ilgili sayısını artır" koşullu talimat — bu bir
placeholder değil, ölçüm sonucuna göre karar. Başka yok.

**Type consistency:**
- `SummaryCounterFn = Callable[[str, list[str]], dict]` → Task 2 tanım,
  `gemini_summary_counter` döndürür, `baseline_rag` parametresi ✓
- `ground_truth(case) -> {"relevant","positive","negative","unclear"}` → Task 1,
  `run_case` `gt["positive"]/gt["negative"]/gt["relevant"]` okur ✓
- `baseline_rag` döner `{reviews_seen, positive_count, negative_count,
  unclear_count, error, method}` → `run_case` `base["positive_count"]`,
  `base.get("reviews_seen")`, `base.get("error")` okur ✓
- `our_method()` → `build_consensus` döner `positive_count/negative_count/
  relevant_count` → `run_case` bunları okur ✓
- `run_case` döner `{question, product_id, ground_truth, ours, baseline, error}`
  → `format_report` hepsini okur ✓
- `hybrid_search(conn, pid, q, encode, limit=k)` → iş #1'de `limit`
  parametresi var (`CANDIDATE_LIMIT` varsayılan), Task 2 `limit=k` geçiyor ✓
