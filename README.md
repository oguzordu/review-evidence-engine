# Review Evidence Engine

*Yorum Kanıt Motoru*

Ürün yorumları üzerinde **örnekleme değil sayım** yapan, her cevabını
dayandığı yorumları göstererek kuran bir soru-cevap servisi.

## Problem

Bir ürünün altında yüzlerce yorum var. "Pil gerçekten dayanıyor mu?" diye
sormak istiyorsun ama hepsini okuyamıyorsun.

Standart yorum özeti sistemleri (büyük e-ticaret sitelerinin kendi "AI özeti"
özellikleri dahil) birkaç benzer yorumu okuyup kendinden emin bir cevap
üretir. İlgili yorum sayısı okunanlardan fazlaysa, geri kalanı sessizce
görmezden gelinir — Amazon'un kendi AI özet özelliğinin, yorumların küçük bir
kesitine bakıp genel tabloyu yanlış yansıttığı raporlanmıştır.

## Yaklaşım

Bu servis ilgili yorumların **tamamını** tek tek değerlendirir, örnekleme
yapmaz. Şunları raporlar:

- Soruyla gerçekten ilgili kaç yorum var
- Bunların kaçı olumlu, kaçı olumsuz, kaçı belirsiz
- Yorumlar çelişiyorsa bunu gizlemeden gösterir
- Son dönemde bir eğilim değişimi var mı (ürün/parti değişmiş olabilir)
- Her iddianın hangi yorumlara dayandığı

Örnek:

```
"Su geçirir mi?"  ->  47 ilgili yorum

   31 yorum: su geçirmiyor
   12 yorum: sızdırıyor
    4 yorum: belirsiz

   Uyarı: olumsuz yorumların 9'u son 3 ayda yoğunlaşıyor.
```

## Teknoloji

Python, FastAPI, PostgreSQL, anlamsal arama için bir vektör veritabanı,
sınıflandırma için bir LLM — Docker ile paketlenmiş.

## Kurulum

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Çalıştırma

```powershell
.venv\Scripts\python.exe -m uvicorn review_evidence.main:app --reload
```

API dokümanı: http://127.0.0.1:8000/docs

## Test

```powershell
.venv\Scripts\python.exe -m pytest -v
```
