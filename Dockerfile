# ---- QR Yoklama production imajı ----
FROM python:3.13-slim

# .pyc dosyası yazma, çıktıyı tamponlama (loglar anında görünsün)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Önce sadece bağımlılıkları kopyala: kod değişse bile bu katman önbellekten gelir,
# imaj çok daha hızlı yeniden oluşturulur.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Statik dosyaları imaj oluşturulurken topla. Bu adım için geçici bir anahtar
# yeterli; gerçek anahtar konteyner çalışırken ortam değişkeninden gelir.
RUN DJANGO_SECRET_KEY=build-only DJANGO_DEBUG=False python manage.py collectstatic --noinput

# Uygulamayı root olmayan bir kullanıcıyla çalıştır: bir açık bulunsa bile
# saldırgan konteyner içinde sınırlı yetkiye sahip olur.
RUN useradd --create-home --uid 1000 app && chown -R app:app /app
USER app

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
