# Deploy — Oracle Cloud Always Free (ARM) + Docker + Caddy

Hedef: uygulama `https://<ip>.sslip.io` üzerinden canlı, `main`'e her push'ta
otomatik güncellenir. Cebinden 0 TL çıkar.

Bu rehber hiç cloud tecrübesi olmadığını varsayar. Sırayla takip et.

---

## 0. Neye ihtiyacın var

- Bir kredi/banka kartı (Oracle **doğrulama** için ister; Always Free'de ücret çekilmez)
- Windows'ta hazır gelen `ssh` komutu (PowerShell / Windows Terminal'de çalışır)
- GitHub repo'na erişim (secret ekleyeceksin)

---

## 1. Oracle hesabı aç

1. <https://cloud.oracle.com> → **Sign up for free**.
2. **Country/Territory: Turkey**. E-posta, isim.
3. Hesap adı (Cloud Account Name): istediğin bir şey, örn. `oguz-cloud`. Bunu not al.
4. **Home Region: Italy Central (Milan) — `eu-milan-1`**. ⚠️ Sonradan değişmez.
5. Telefon doğrulama (SMS).
6. Kart bilgisi — fatura adresi kartla aynı ülke olmalı. Küçük bir bloke konur,
   birkaç güne iade edilir. **Ücret çekilmez.**
7. Onay → hesap birkaç dakikada hazır. Konsola giriş yap.

Kart reddedilirse: farklı kart dene (Visa/Mastercard, sanal kart bazen reddedilir).

---

## 2. ARM VM oluştur

1. Konsol sol üst menü (☰) → **Compute → Instances → Create instance**.
2. **Name:** `review-engine` (fark etmez).
3. **Image and shape** → **Edit**:
   - **Image** → **Change image** → **Canonical Ubuntu** → sürüm **22.04** → Select.
   - **Shape** → **Change shape** → sekmeler: **Ampere** → `VM.Standard.A1.Flex`.
     - **OCPUs: 1**, **Memory (GB): 6** (Always Free toplam sınırı 4 OCPU / 24 GB;
       1/6 fazlasıyla yeter).
   - Save.
4. **Networking:**
   - "Create new virtual cloud network" seçili kalsın (otomatik VCN + subnet).
   - **Assign a public IPv4 address: Yes** (işaretli olduğundan emin ol).
5. **Add SSH keys:**
   - **Generate a key pair for me** seçili.
   - **Save private key** → indir (`ssh-key-2026-....key` gibi). **Sakla, bir daha veremez.**
   - **Save public key** → indir (yedek için).
6. **Create** butonuna bas.
7. Instance sayfası açılır. Durum **Provisioning → Running** olana kadar bekle (1-2 dk).
8. **"Out of capacity"** hatası: Milano'da bugün ARM kapasitesi yok demektir.
   - **Create** butonunu 10-15 dakikada bir tekrar dene (kapasite gün içinde açılır).
   - Ya da bana söyle, kapasite açılınca otomatik deneyen bir yöntem vereyim.
9. Çalışınca **Instance details** sayfasından **Public IP address**'i kopyala.
   Örn: `140.238.1.234`. Buna bundan sonra **`<IP>`** diyeceğim.

---

## 3. Ağı aç — 80 ve 443 portları (İKİ KATMAN, ikisi de şart)

### 3a. Oracle Security List (bulut firewall)

1. Menü → **Networking → Virtual cloud networks** → oluşan VCN'e tıkla.
2. Sol taraf **Security Lists** → **Default Security List for ...**'e tıkla.
3. **Add Ingress Rules** → şu iki kuralı ekle (her biri ayrı satır):

   | Source Type | Source CIDR | IP Protocol | Destination Port Range |
   |---|---|---|---|
   | CIDR | `0.0.0.0/0` | TCP | `80` |
   | CIDR | `0.0.0.0/0` | TCP | `443` |

4. **Add Ingress Rules** ile kaydet. (Port 22 zaten açık.)

### 3b. VM içi firewall (Ubuntu'nun iptables'ı — 3c'de, SSH'tan sonra)

---

## 4. VM'e SSH ile bağlan

Windows Terminal / PowerShell aç. İndirdiğin key dosyasının yolunu kullan.

```powershell
# key dosyasının izinlerini düzelt (yoksa ssh reddeder)
icacls "C:\Users\Oguz\Downloads\ssh-key-2026-01-01.key" /inheritance:r /grant:r "$($env:USERNAME):(R)"

# bağlan
ssh -i "C:\Users\Oguz\Downloads\ssh-key-2026-01-01.key" ubuntu@<IP>
```

İlk bağlantıda "yes" yaz. `ubuntu@review-engine:~$` görüyorsan içerdesin.

### 4c. VM içi firewall (artık SSH'tasın)

```bash
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
sudo apt-get update
sudo apt-get install -y netfilter-persistent iptables-persistent
sudo netfilter-persistent save
```

---

## 5. Docker ve Git kur

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
sudo apt-get install -y git
```

Grup değişikliğinin geçerli olması için **çık ve tekrar bağlan:**

```bash
exit
```
```powershell
ssh -i "C:\Users\Oguz\Downloads\ssh-key-...key" ubuntu@<IP>
```

Kontrol:
```bash
docker version        # Client + Server görünmeli
docker compose version
```

---

## 6. Repo'yu çek ve yapılandır

```bash
git clone https://github.com/oguzordu/review-evidence-engine.git
cd review-evidence-engine
cp .env.prod.example .env.prod
nano .env.prod
```

`nano` açılınca 3 satırı doldur:

```
GEMINI_API_KEY=AIza...        # aistudio.google.com/apikey (ücretsiz)
SITE_ADDRESS=140-238-1-234.sslip.io    # <IP>'nin NOKTALARINI TİRE yap + .sslip.io
POSTGRES_PASSWORD=buraya-rastgele-bir-sey
```

Rastgele şifre üretmek istersen: `openssl rand -hex 16` çıktısını yapıştır.

Kaydet: `Ctrl+O` → Enter → `Ctrl+X`.

> **sslip.io nedir:** `140-238-1-234.sslip.io` otomatik olarak `140.238.1.234`'e
> çözülür. Domain almadan geçerli bir hostname'in olur, Let's Encrypt bununla
> sertifika verir.

---

## 7. Build et ve başlat

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

İlk build **ARM'da ~10-15 dakika** sürer (torch derleniyor). Sabırlı ol.
İzlemek istersen ayrı bir SSH penceresinde:

```bash
cd review-evidence-engine
docker compose -f docker-compose.prod.yml logs -f
```

Bittiğinde `docker compose -f docker-compose.prod.yml ps` → 3 servis
(`db`, `app`, `caddy`) **Up** / **healthy** olmalı.

---

## 8. Şemayı kur ve veriyi yükle (tek seferlik)

```bash
# 1) tablolar + pgvector + usage_log
docker compose -f docker-compose.prod.yml exec -T app python -c "from review_evidence.db import connect, init_schema; from review_evidence.config import DATABASE_URL; init_schema(connect(DATABASE_URL))"

# 2) veri setini indir (HuggingFace'ten 1000 yorum -> data/sample_reviews.json)
docker compose -f docker-compose.prod.yml exec -T app python scripts/fetch_dataset.py

# 3) yorumları yükle + embedding üret (ARM CPU'da birkaç dakika)
docker compose -f docker-compose.prod.yml exec -T app python -c "
from pathlib import Path
from review_evidence.db import connect, init_schema
from review_evidence.ingest import load_reviews
from review_evidence.config import DATABASE_URL
c = connect(DATABASE_URL); init_schema(c)
print('yuklendi:', load_reviews(c, Path('data/sample_reviews.json')))
"
```

`data/demo_qa.json` repo'da hazır geliyor — uygulama onu otomatik okur, ekstra iş yok.

---

## 9. Çalışıyor mu?

**VM içinden** (Caddy → app zincirini test eder):
```bash
docker compose -f docker-compose.prod.yml exec -T caddy wget -qO- http://app:8000/health
# {"status":"ok"}
```

**Kendi bilgisayarından** (tarayıcı): `https://<SITE_ADDRESS>` aç.
İlk açılışta Caddy Let's Encrypt sertifikası alır (5-10 sn). Sonra arayüz gelir,
"Hazır sorular" çipleri anında yanıt verir.

`https://<SITE_ADDRESS>/health` → `{"status":"ok"}`.

**Sertifika alınmıyor / site açılmıyorsa** → aşağıdaki "Sorun giderme".

---

## 10. Otomatik deploy'u (CD) aç

### 10a. SSH secret'ları

GitHub repo → **Settings → Secrets and variables → Actions**.

**Secrets** sekmesi → **New repository secret** (3 kez):

| Name | Secret |
|---|---|
| `DEPLOY_HOST` | `<IP>` (sadece IP, örn. `140.238.1.234`) |
| `DEPLOY_USER` | `ubuntu` |
| `DEPLOY_SSH_KEY` | private key dosyasının **tüm içeriği** — dosyayı Not Defteri'yle aç, `-----BEGIN...` satırından `...END-----` satırına kadar HER ŞEYİ kopyala yapıştır |

### 10b. Deploy'u etkinleştir

Aynı sayfada **Variables** sekmesi → **New repository variable**:

| Name | Value |
|---|---|
| `DEPLOY_ENABLED` | `true` |

Bu olmadan deploy workflow'u atlanır (kasıtlı — VM yokken kırmızı X çıkmasın diye).

### 10c. Test et

Repo'da küçük bir değişiklik yapıp `main`'e push et (ya da GitHub'da herhangi bir
dosyayı düzenle). Sıra:

1. **CI** workflow'u çalışır → testler → yeşil
2. **Deploy** workflow'u tetiklenir → VM'e SSH → `git pull` + `docker compose up -d --build`
3. Actions sekmesinde ikisi de yeşil olmalı

Bundan sonra her `main` push'u otomatik canlıya gider.

---

## Sorun giderme

| Belirti | Sebep / Çözüm |
|---|---|
| `ssh: Permission denied (publickey)` | Key izinleri (adım 4 `icacls`) veya yanlış key dosyası |
| VM oluştururken "Out of capacity" | Milano ARM dolu; 10-15 dk'da bir **Create** tekrar dene |
| `https://<site>` açılmıyor, tarayıcı takılıyor | 80/443 kapalı. Kontrol: **hem** Security List (adım 3a) **hem** iptables (adım 4c). `sudo iptables -L INPUT -n --line-numbers` ile 80/443 ACCEPT satırlarını gör |
| Site açılıyor ama "not secure" / sertifika hatası | Caddy sertifika alamadı. `docker compose -f docker-compose.prod.yml logs caddy` bak. Genelde 80 portu dışarıdan erişilemiyor demektir |
| Build sırasında donuyor / OOM | 6 GB shape kullandığından emin ol. 1 GB'daysan swap ekle: `sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile` |
| Deploy workflow "missing server host" | `DEPLOY_HOST` secret'ı eksik veya `DEPLOY_ENABLED` variable'ı `true` değil |
| `/ask`'e serbest soru → hep "budget_exhausted" | Gemini günlük kota dolmuş; ertesi gün sıfırlanır. Hazır sorular çalışmaya devam eder |

## Bakım

- Logları izle: `docker compose -f docker-compose.prod.yml logs -f app`
- Ücretsiz uptime izleme (opsiyonel): <https://uptimerobot.com> → `https://<SITE_ADDRESS>/health`
- Oracle "Always Free" instance'ları uzun süre CPU idle kalırsa **durdurabiliyor**
  (silmiyor). Ayda bir konsola girip **Running** olduğunu kontrol et; durmuşsa **Start**.
- demo_qa.json'ı yenilemek istersen (kota resetlendiğinde), VM'de:
  `docker compose -f docker-compose.prod.yml exec -T app python scripts/build_demo_qa.py`
  sonra çıktıyı repo'ya commit et.
