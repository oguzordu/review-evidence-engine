# Canlı Deploy — Tasarım Dokümanı

> Tarih: 2026-08-31
> Durum: onaylandı
> Branch: `deploy`

## Hedef

`review-evidence-engine`'i Oracle Cloud Always Free ARM VM'de canlıya almak,
GitHub Actions ile CI/CD kurmak. Cebinden 0 TL. Gemini 20/gün kotasını demo
modu + günlük canlı bütçeyle yönetmek.

## Kararlar

| Konu | Karar |
|---|---|
| Host | Oracle Cloud Always Free, ARM Ampere (VM.Standard.A1.Flex, 1 OCPU / 6 GB), Ubuntu 22.04, Docker |
| HTTPS | `<ip-tireli>.sslip.io` hostname + Let's Encrypt, **Caddy** reverse proxy (tek dosya, otomatik yenileme) |
| `/ask` (prod) | Demo modu: önceden hesaplanmış cevaplar + günlük ~15 çağrılık paylaşılan canlı bütçe + IP başına 2/gün |
| `/ask` (lokal) | `DEMO_MODE` kapalı → mevcut davranış, hep canlı |
| CD | GitHub Actions, CI başarılıysa `main`'e push'ta SSH deploy |
| VM kurulumu | Kullanıcı yapar (runbook verilir); kod + config bu oturumda hazırlanır |

## Mimari

### App kodu

**`config.py`** — yeni ayarlar (hepsi env'den, `.env`/`.env.prod`):
- `DEMO_MODE: bool` (default `False`)
- `DAILY_LIVE_BUDGET: int` (default `15`)
- `PER_IP_LIMIT: int` (default `2`)

**`db.py`** — `SCHEMA`'ya ekle:
```sql
CREATE TABLE IF NOT EXISTS usage_log (
    id         SERIAL PRIMARY KEY,
    day        DATE NOT NULL DEFAULT CURRENT_DATE,
    ip         TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_usage_log_day ON usage_log (day);
```

**`src/review_evidence/quota.py`** (yeni) — HTTP bilmez:
- `check_live_quota(conn, ip, *, daily_budget, per_ip_limit) -> str`
  - `SELECT count(*) FROM usage_log WHERE day = CURRENT_DATE` → `>= daily_budget` ise `"budget_exhausted"`
  - `... AND ip = %s` → `>= per_ip_limit` ise `"ip_limit"`
  - aksi halde `INSERT INTO usage_log (ip) VALUES (%s)` + `"ok"`
  - Kayıt ve kontrol tek fonksiyonda; çağıran `"ok"` alırsa canlı çağrı yapar.

**`src/review_evidence/demo.py`** (yeni) — HTTP bilmez:
- `load_demo_qa(path="data/demo_qa.json") -> dict` — `{product_id: {normalized_question: answer_payload}}` yapısına indexler; dosya yoksa `{}`.
- `lookup(demo_qa, product_id, question) -> dict | None` — `text.normalize(question)` ile eşleştirir.
- `answer_payload` = `build_consensus`'ın döndürdüğü tam sözlük + `"source"` alanı.

**`main.py`** — `/ask`:
```
if DEMO_MODE:
    hit = demo.lookup(_demo_qa, product_id, question)
    if hit: return {**hit, "source": "precomputed"}
    if _client is None: 503
    verdict = quota.check_live_quota(conn, client_ip, daily_budget=..., per_ip_limit=...)
    if verdict != "ok":
        sample = demo.any_for_product(_demo_qa, product_id)  # varsa
        return {**(sample or {}), "source": verdict}
    result = build_consensus(...); return {**result, "source": "live"}
else:
    # mevcut davranis
    if _client is None: 503
    result = build_consensus(...); return {**result, "source": "live"}
```
- `client_ip`: `request.headers.get("x-forwarded-for", request.client.host)` — ilk değer (Caddy `X-Forwarded-For` ekler). `Request` parametresi eklenir.
- `_demo_qa = demo.load_demo_qa()` modül seviyesinde.

**`scripts/build_demo_qa.py`** (yeni):
- Küratörlü `{product_id: [questions]}` (p1–p5, her biri 3 soru).
- Her biri için `build_consensus(conn, pid, q, gemini_batch_classifier(client), encode)` çalıştırır.
- `data/demo_qa.json` yazar: `{"generated_at", "model", "items": [{product_id, question, answer}]}`.
- Lokalde bir kez çalışır (~15 Gemini çağrısı = bir günlük bütçe; dikkatli). Çıktı commit'lenir.
- `.gitignore`'a `!data/demo_qa.json` istisnası.

**`static/index.html`** — precomputed sorular tıklanabilir çip; sonuç kartında
`source` rozeti (`precomputed` / `live` / `budget_exhausted` / `ip_limit`);
bütçe tükendiğinde açıklama metni.

### Prod infra

**`docker-compose.prod.yml`:**
```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: review_evidence
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: review_evidence
    volumes: [pgdata:/var/lib/postgresql/data]
    healthcheck: {test: ["CMD-SHELL","pg_isready -U review_evidence"], interval: 5s, timeout: 5s, retries: 10}
    restart: unless-stopped
  app:
    build: .
    environment:
      DATABASE_URL: postgresql://review_evidence:${POSTGRES_PASSWORD}@db:5432/review_evidence
      GEMINI_API_KEY: ${GEMINI_API_KEY}
      DEMO_MODE: "true"
    depends_on: {db: {condition: service_healthy}}
    restart: unless-stopped
  caddy:
    image: caddy:2-alpine
    ports: ["80:80","443:443"]
    environment:
      SITE_ADDRESS: ${SITE_ADDRESS}
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    depends_on: [app]
    restart: unless-stopped
volumes: {pgdata: {}, caddy_data: {}, caddy_config: {}}
```
Not: `db` ve `app` portları host'a açılmaz (sadece iç ağ).

**`Caddyfile`:**
```
{$SITE_ADDRESS} {
	reverse_proxy app:8000
}
```

**`.env.prod.example`:**
```
GEMINI_API_KEY=
SITE_ADDRESS=123-45-67-89.sslip.io
POSTGRES_PASSWORD=change-me
```

### CD — `.github/workflows/deploy.yml`

```yaml
name: Deploy
on:
  workflow_run:
    workflows: ["CI"]
    types: [completed]
    branches: [main]
jobs:
  deploy:
    if: github.event.workflow_run.conclusion == 'success'
    runs-on: ubuntu-latest
    steps:
      - uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.DEPLOY_HOST }}
          username: ${{ secrets.DEPLOY_USER }}
          key: ${{ secrets.DEPLOY_SSH_KEY }}
          script: |
            cd ~/review-evidence-engine
            git pull --ff-only
            docker compose -f docker-compose.prod.yml up -d --build
            docker compose -f docker-compose.prod.yml exec -T app \
              python -c "from review_evidence.db import connect, init_schema; from review_evidence.config import DATABASE_URL; init_schema(connect(DATABASE_URL))"
```
Secrets: `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`.

### Runbook — `docs/deploy.md`

Adımlar: Oracle hesap → ARM VM oluştur (Ubuntu 22.04) → VCN Security List'te
80/443 ingress → SSH → `apt install docker.io docker-compose-v2` + `usermod -aG
docker` → `git clone` → `cp .env.prod.example .env.prod` doldur
(`SITE_ADDRESS` = IP'nin noktalarını tireye çevir + `.sslip.io`) → `docker
compose -f docker-compose.prod.yml up -d --build` (ARM'da torch ~10-15 dk) →
veri yükle (`fetch_dataset` + ingest) → `data/demo_qa.json` zaten commit'li,
sadece uygulama okur → `sudo ufw allow 80,443` → `curl
https://<site>/health` → GitHub repo Settings → Secrets → 3 secret → sonraki
push otomatik deploy.

## Hata Yönetimi

| Senaryo | Davranış |
|---|---|
| `DEMO_MODE=true`, `demo_qa.json` yok | `_demo_qa = {}`; her soru canlı bütçeye düşer (log uyarısı) |
| Canlı bütçe dolu | `source: "budget_exhausted"` + varsa o ürün için bir precomputed örnek |
| IP limiti dolu | `source: "ip_limit"` + precomputed örnek |
| `GEMINI_API_KEY` yok ama `DEMO_MODE=true` | precomputed sorular çalışır; canlı istek 503 yerine `source: "no_api_key"` + örnek |
| Caddy sertifika alamıyor (DNS/port) | runbook'ta teşhis: 80/443 hem OS hem Oracle Security List'te açık mı |
| ARM'da build OOM (torch) | runbook notu: 6 GB yeterli; 1 GB shape'te swap ekle |

## Test Planı

- `tests/test_quota.py` — `check_live_quota`: boş → `ok` + kayıt; bütçe sınırında
  → `budget_exhausted`; IP sınırında → `ip_limit`; farklı gün kayıtları sayılmaz.
- `tests/test_demo.py` — `load_demo_qa` yapı; `lookup` normalize ile eşleşme;
  dosya yoksa `{}`.
- `tests/test_main.py` — `DEMO_MODE` monkeypatch: precomputed hit → `source:
  precomputed`, LLM çağrılmaz; bütçe dolu → `source: budget_exhausted`;
  `DEMO_MODE` kapalı → mevcut testler değişmez.
- Prod infra / CD: VM'de manuel doğrulama (runbook adımları), otomatik test yok.

## Kapsam Dışı (YAGNI)

- Monitoring/alerting (ayrı, sonra — Uptime Robot ücretsiz eklenebilir).
- nginx alternatifi (Caddy yeterli).
- Blue-green / zero-downtime deploy (tek VM, `up -d` yeterli).
- Trend analizi (iş #3, yapılmıyor).
- Otomatik veri yükleme CD'de (ilk kurulum elle, runbook'ta).
