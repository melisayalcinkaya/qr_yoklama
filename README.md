# QR Yoklama

[![CI](https://github.com/melisayalcinkaya/qr_yoklama/actions/workflows/ci.yml/badge.svg)](https://github.com/melisayalcinkaya/qr_yoklama/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.12%20%7C%203.13-3776AB?logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.2-092E20?logo=django&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-blue)

Derste yoklamayı saniyeler içinde alan, **kopya çekilmesi zor** bir QR yoklama sistemi.
Öğretmen ekrana QR kodu yansıtır, öğrenciler telefonlarıyla okutup adlarını girer; liste canlı olarak dolar ve Excel'e aktarılır.

<p align="center">
  <img src="docs/screenshots/canli-yoklama.png" alt="Öğretmenin canlı yoklama ekranı: büyük QR kod ve katılan öğrencilerin listesi" width="760">
</p>

<p align="center">
  <img src="docs/screenshots/ogrenci-formu.png" alt="Öğrencinin telefonda gördüğü yoklama formu" width="230">
  &nbsp;
  <img src="docs/screenshots/ogrenci-onay.png" alt="Yoklama alındı onay ekranı" width="230">
</p>

## Hangi sorunu çözüyor?

Kâğıtla yoklama hem ders süresini yer hem de "arkadaşının yerine imza atma" sorununa açıktır.
Basit QR yoklama sistemleri ise daha da kolay kandırılır: QR'ın fotoğrafını sınıf grubuna atmak yeterlidir.

QR Yoklama bu yüzden **katmanlı** bir yaklaşım kullanır:

| Kopya yöntemi | Önlem |
|---|---|
| QR'ın fotoğrafını sınıf dışındaki arkadaşa göndermek | QR içindeki token **15 saniyede** geçersiz olur, ekrandaki kod 5 saniyede bir yenilenir |
| Linki saklayıp sonradan kullanmak | Token doğrulanınca adres çubuğundan silinir; form yalnızca 3 dakikalık sunucu tarafı izinle gönderilebilir |
| Aynı telefondan birden fazla kişiye yoklama vermek | Cihaz başına tek kayıt (veritabanı kısıtıyla garanti altında) |
| Evden yoklama vermek | İsteğe bağlı **konum doğrulama**: öğrenci sınıfın belirlenen yarıçapında olmalı |
| Gözden kaçan şüpheli kayıt | Öğretmen canlı listede kaydı tek tıkla silebilir; her kaydın sınıfa uzaklığı görünür |

## Özellikler

**Öğretmen**
- Hesap oluşturma ve giriş; birden fazla ders yönetimi
- Süreli yoklama başlatma (süre dolunca otomatik kapanır)
- Projeksiyon için büyük, otomatik yenilenen QR kod
- Öğrenciler katıldıkça güncellenen canlı liste; projeksiyonda gizlilik için adlar varsayılan olarak bulanık
- Yoklama ve ders bazında **Excel** çıktısı
- **Devam istatistikleri:** öğrenci başına katılım oranı, %70 altındakilerin işaretlenmesi, yoklama başına katılım grafiği

**Öğrenci**
- Uygulama yüklemeden, telefon kamerasıyla QR okutup 3 alanlı form
- Rakam klavyesi, otomatik doldurma ve büyük dokunma alanlarıyla mobil öncelikli arayüz

**Genel**
- Açık ve karanlık tema (sistem ayarına göre)
- Klavye ile gezinme, ekran okuyucu desteği, azaltılmış hareket tercihi

<p align="center">
  <img src="docs/screenshots/istatistikler-karanlik.png" alt="Ders devam istatistikleri, karanlık tema" width="760">
</p>

## Nasıl çalışır?

```mermaid
sequenceDiagram
    autonumber
    participant Ö as Öğretmen paneli
    participant S as Sunucu (Django)
    participant T as Öğrenci telefonu

    loop Her 5 saniyede
        Ö->>S: POST /sessions/:id/qr/ (CSRF korumalı)
        S-->>Ö: Yeni token ile QR (15 sn geçerli)
    end
    T->>S: GET /c/:id/?t=token  (QR okutuldu)
    S->>S: Token geçerli mi? (compare_digest)
    S-->>T: Oturuma 3 dk'lık izin yaz, token'sız adrese yönlendir
    T->>S: POST form (+ konum, cihaz kimliği)
    S->>S: İzin, konum, tekrar kontrolü + DB kısıtları
    S-->>T: Yoklamanız alındı
    loop Her 3 saniyede
        Ö->>S: GET /sessions/:id/records/?after=son_id
        S-->>Ö: Yalnızca yeni kayıtlar
    end
```

## Güvenlik

Proje, [OWASP Top 10](https://owasp.org/Top10/) risklerine karşı şu önlemleri içerir:

- **Erişim kontrolü:** Tüm öğretmen sayfaları giriş gerektirir. Öğretmen yalnızca kendi verisine erişir; başkasının kaydı için `404` döner (kaydın varlığı da gizlenir).
- **Kaba kuvvet koruması:** 5 hatalı girişten sonra kullanıcı adı + IP 15 dakika kilitlenir ([django-axes](https://github.com/jazzband/django-axes)).
- **Güvenli token'lar:** `secrets` modülüyle üretilir, `secrets.compare_digest` ile karşılaştırılır (timing attack'a karşı).
- **CSRF:** Veri değiştiren her istek `POST` ve CSRF token'ı ile yapılır.
- **XSS:** Django şablonları otomatik kaçış yapar; JavaScript ile oluşturulan satırlarda `innerHTML` yerine `textContent` kullanılır.
- **Excel formül enjeksiyonu:** `=`, `+`, `-`, `@` ile başlayan değerler dışa aktarımda düz metne çevrilir.
- **Gizli bilgiler:** Anahtarlar ortam değişkenlerinden okunur; `DEBUG` kapalıyken `SECRET_KEY` yoksa uygulama başlamaz.
- **Production ayarları:** HTTPS yönlendirmesi, HSTS, `Secure`/`HttpOnly` çerezler, `X-Frame-Options: DENY`, `nosniff`. CI her push'ta `manage.py check --deploy` çalıştırır.
- **Konteyner:** Uygulama Docker içinde root olmayan bir kullanıcıyla çalışır.
- **Gizlilik (KVKK):** Projeksiyonda öğrenci bilgileri varsayılan olarak gizli; yazı tipi üçüncü taraf sunuculardan değil, uygulamanın kendisinden yüklenir.

## Teknolojiler

| Katman | Teknoloji |
|---|---|
| Backend | Python 3.12+, Django 5.2 |
| Veritabanı | PostgreSQL (production), SQLite (geliştirme) |
| Frontend | Django şablonları, saf JavaScript ve CSS (çatı kütüphanesi yok) |
| Sunucu | Gunicorn, WhiteNoise |
| Kalite | Django test framework, coverage, Ruff (bandit güvenlik kuralları dahil) |
| Altyapı | Docker, Docker Compose, GitHub Actions |

## Kurulum

### Docker ile (önerilen)

```bash
git clone https://github.com/melisayalcinkaya/qr_yoklama.git
cd qr_yoklama
docker compose up --build
```

[http://localhost:8000](http://localhost:8000) adresinde **demo / demo-sifre-2026** ile giriş yapın.
Örnek ders ve 8 haftalık yoklama verisi otomatik oluşturulur.

### Yerel geliştirme

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

cp .env.example .env             # DJANGO_DEBUG=True bırakın
python manage.py migrate
python manage.py seed_demo       # isteğe bağlı demo verisi
python manage.py runserver
```

> **Telefonla denemek için:** Telefon ve bilgisayar aynı ağdayken `python manage.py runserver 0.0.0.0:8000` çalıştırın ve bilgisayarın IP'sini `.env` içindeki `DJANGO_ALLOWED_HOSTS` listesine ekleyin. Konum doğrulaması tarayıcı kuralı gereği yalnızca HTTPS (veya `localhost`) üzerinde çalışır.

### Ortam değişkenleri

| Değişken | Açıklama | Varsayılan |
|---|---|---|
| `DJANGO_DEBUG` | Geliştirme modu | `False` |
| `DJANGO_SECRET_KEY` | Gizli anahtar (production'da zorunlu) | — |
| `DJANGO_ALLOWED_HOSTS` | İzin verilen alan adları, virgülle | `localhost,127.0.0.1` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Ör. `https://yoklama.ornek.com` | — |
| `DATABASE_URL` | Ör. `postgres://kullanici:sifre@host:5432/db` | SQLite |
| `DJANGO_SECURE_SSL_REDIRECT` | HTTP'yi HTTPS'e yönlendir | `True` |

## Testler

```bash
python manage.py test                     # 57 test
coverage run manage.py test && coverage report
ruff check . && ruff format --check .
```

Testler; QR token'ının süresi ve yenilenmesi, QR okutmadan yoklama verme girişimi, aynı öğrenci/cihazla tekrar, konum doğrulama, yetkisiz erişim, kaba kuvvet kilidi, Excel formül enjeksiyonu ve istatistik hesaplarını kapsar.
CI bu kontrolleri Python 3.12 ve 3.13'te çalıştırır, Docker imajını oluşturup ayağa kalktığını doğrular.

## Proje yapısı

```
qr_yoklama/
├── attendance/            # Uygulama
│   ├── models.py          # Course, AttendanceSession, AttendanceRecord
│   ├── views.py           # Öğretmen ekranları, öğrenci akışı, istatistikler
│   ├── forms.py           # Form doğrulama
│   ├── geo.py             # Haversine mesafe hesabı
│   ├── management/        # seed_demo komutu
│   ├── static/            # CSS ve yazı tipi
│   ├── templates/
│   └── tests/             # 57 test
├── config/                # Django ayarları ve URL'ler
├── templates/             # Ortak şablonlar (base, giriş)
├── .github/workflows/     # CI
├── Dockerfile
└── docker-compose.yml
```

## Bilinen sınırlamalar ve yol haritası

- **Konum, istemciden gelir.** Teknik bilgisi olan biri sahte konum gönderebilir; bu yüzden konum tek başına değil, diğer katmanlarla birlikte bir caydırıcıdır.
- **Canlı liste polling ile güncellenir.** Bir sınıf için yeterli ve basit; çok büyük ölçekte WebSocket'e (Django Channels) geçilebilir.
- **İstatistiklerde açık yoklama da sayılır.** Yoklama sürerken henüz katılmamış öğrenciler "kaçırdı" görünür.
- Planlananlar: öğrenci listesini Excel'den içe aktarma ve sadece kayıtlı öğrencileri kabul etme, ders bazında ayarlanabilir devam sınırı, İngilizce arayüz.

## Lisans

[MIT](LICENSE) © Melisa Yalçınkaya

---

### In English

**QR Yoklama** is a Django attendance system that is hard to cheat: the QR code shown in class rotates every 5 seconds and its token expires after 15 seconds, a short-lived server-side grant protects the form, one record is allowed per student and device, and an optional geofence checks that the student is in the classroom. Teachers get a live attendance list, Excel export and per-student attendance statistics. The project ships with 57 tests, Ruff linting, a GitHub Actions pipeline, production security settings and a non-root Docker image. Run it with `docker compose up --build` and log in as **demo / demo-sifre-2026**.
