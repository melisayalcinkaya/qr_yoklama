#!/bin/sh
# Konteyner her başladığında veritabanını güncel şemaya getirir, sonra
# asıl komutu (varsayılan: gunicorn) çalıştırır.
set -e

python manage.py migrate --noinput

if [ "${DJANGO_SEED_DEMO:-False}" = "True" ]; then
    python manage.py seed_demo
fi

exec "$@"
