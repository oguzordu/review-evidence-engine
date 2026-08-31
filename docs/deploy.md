# Deploy — Oracle Cloud Always Free (ARM) + Docker + Caddy

Cebinden 0 TL. `<ip>.sslip.io` üzerinden HTTPS. `main`'e her push'ta otomatik deploy.

## 1. Oracle hesabı ve VM

1. [cloud.oracle.com](https://cloud.oracle.com) → **Start for free**. Doğrulama için
   kredi kartı ister (1 TL bloke, iade edilir; **Always Free** kaldığın sürece
   ücret çekilmez). Türk debit kartların çoğu çalışır; olmazsa farklı kart dene.
2. Konsol → **Compute → Instances → Create instance**:
   - Image: **Canonical Ubuntu 22.04**
   - Shape: **Ampere (ARM)** → `VM.Standard.A1.Flex`, **1 OCPU / 6 GB** (Always Free
     sınırı 4 OCPU / 24 GB toplam — 1/6 yeterli)
   - "ARM out of capacity" hatası alırsan: birkaç saat sonra tekrar dene ya da
     farklı Availability Domain / bölge seç
   - SSH: **Generate a key pair** → private key'i indir (`.key`), sakla
3. Instance açılınca **Public IP** adresini not al (örn. `123.45.67.89`).

## 2. Ağ — 80 ve 443'ü aç

İki katman var, ikisini de aç:

**Oracle VCN Security List:**
Networking → Virtual Cloud Networks → (VCN) → Security Lists → Default →
**Add Ingress Rules**: Source `0.0.0.0/0`, IP Protocol TCP, Destination Port
`80` (bir kural) ve `443` (bir kural).

**VM içi firewall** (Ubuntu image'da iptables kuralları var):
```bash
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

## 3. Sunucu hazırlığı

```bash
ssh -i /yol/private.key ubuntu@<IP>

sudo apt update && sudo apt install -y docker.io docker-compose-v2 git
sudo usermod -aG docker $USER
exit   # gruba katilim icin cikip tekrar gir
ssh -i /yol/private.key ubuntu@<IP>

git clone https://github.com/oguzordu/review-evidence-engine.git
cd review-evidence-engine
```

## 4. Yapılandırma

```bash
cp .env.prod.example .env.prod
nano .env.prod
```
Doldur:
- `GEMINI_API_KEY` — [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
- `SITE_ADDRESS` — IP'nin noktalarını tireye çevir: `123.45.67.89` → `123-45-67-89.sslip.io`
- `POSTGRES_PASSWORD` — rastgele bir şey

## 5. İlk deploy

```bash
docker compose -f docker-compose.prod.yml up -d --build
```
İlk build ARM'da **~10-15 dk** (torch derleniyor). RAM 6 GB ile sorun olmaz;
1 GB shape'te swap ekle:
```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
```

Şemayı kur:
```bash
docker compose -f docker-compose.prod.yml exec -T app \
  python -c "from review_evidence.db import connect, init_schema; from review_evidence.config import DATABASE_URL; init_schema(connect(DATABASE_URL))"
```

## 6. Veriyi yükle (tek seferlik)

```bash
docker compose -f docker-compose.prod.yml exec -T app python scripts/fetch_dataset.py
docker compose -f docker-compose.prod.yml exec -T app python -c "
from pathlib import Path
from review_evidence.db import connect, init_schema
from review_evidence.ingest import load_reviews
from review_evidence.config import DATABASE_URL
conn = connect(DATABASE_URL); init_schema(conn)
print(load_reviews(conn, Path('data/sample_reviews.json')))
"
```
`data/demo_qa.json` repo'da hazır — uygulama onu okur, ekstra iş yok.

## 7. Doğrula

```bash
curl https://<SITE_ADDRESS>/health      # {"status":"ok"}
```
Tarayıcıda `https://<SITE_ADDRESS>` → arayüz, hazır sorular anında yanıt verir.
İlk istekte Caddy Let's Encrypt sertifikası alır (birkaç saniye).

**Sertifika alınmıyorsa:** 80/443 hem Security List hem VM firewall'da açık mı?
`docker compose -f docker-compose.prod.yml logs caddy` bak.

## 8. CD'yi aç

GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Değer |
|---|---|
| `DEPLOY_HOST` | VM public IP |
| `DEPLOY_USER` | `ubuntu` |
| `DEPLOY_SSH_KEY` | private key'in **tam içeriği** (`-----BEGIN ... END-----` dahil) |

Bundan sonra `main`'e her push → CI yeşilse `.github/workflows/deploy.yml`
otomatik SSH ile `git pull` + `up -d --build` yapar.

## Bakım

- Logları izle: `docker compose -f docker-compose.prod.yml logs -f app`
- Ücretsiz uptime takibi: [uptimerobot.com](https://uptimerobot.com) → `https://<SITE_ADDRESS>/health` (opsiyonel)
- Oracle "Always Free" kaynaklarını kapatma/idle yüzünden silebiliyor — ayda bir
  konsola girip instance'ın "Running" olduğunu kontrol et.
