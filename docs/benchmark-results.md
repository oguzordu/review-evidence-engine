# Baseline Karşılaştırma Ölçümü

> Ölçüm tarihi: 2026-08-31 · Model: `gemini-flash-lite-latest` · Baseline K: 8

| Soru | Ground truth (ilgili/olumlu/olumsuz) | Bizim yöntem (olumlu/olumsuz, ±hata) | Baseline (gördüğü/olumlu/olumsuz, kaçırılan ilgili) |
|---|---|---|---|
| pil ömrü yeterli mi | 28/8/20 | 8/20 (±0/±0) | 8/2/6 (20 kaçtı) |
| kargo hızlı ve sorunsuz mu | 22/7/15 | 7/15 (±0/±0) | 8/5/3 (14 kaçtı) |

## Yorum

- **pil ömrü yeterli mi**: baseline yalnızca 8 yorum gördü, 20 ilgili yorumu hiç değerlendirmedi; olumsuz sayısını 14 birim yanlış raporladı.
- **kargo hızlı ve sorunsuz mu**: baseline yalnızca 8 yorum gördü, 14 ilgili yorumu hiç değerlendirmedi; olumsuz sayısını 12 birim yanlış raporladı.
