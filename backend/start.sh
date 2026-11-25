#!/usr/bin/env bash
# Render start command: migrate, optionally load demo data, then serve.
set -o errexit
python manage.py migrate --noinput
python manage.py ensure_admin
if [ "${SEED_DEMO:-false}" = "true" ]; then
  python manage.py seed_demo
fi
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers "${WEB_CONCURRENCY:-2}" --timeout 120
