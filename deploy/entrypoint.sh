#!/bin/sh
set -eu
cd /app

wait_for_db() {
  i=0
  until python -c "import psycopg, os; psycopg.connect(os.environ['DATABASE_URL']).close()" 2>/dev/null; do
    i=$((i+1)); [ $i -gt 60 ] && echo "database not reachable" && exit 1
    sleep 2
  done
}

case "${1:-web}" in
  web)
    wait_for_db
    python manage.py migrate --noinput
    python manage.py collectstatic --noinput
    python manage.py bootstrap
    exec uvicorn config.asgi:application --host 0.0.0.0 --port 8000 --workers 2 --proxy-headers --forwarded-allow-ips="*"
    ;;
  scheduler)
    wait_for_db
    exec supercronic /app/deploy/crontab
    ;;
  *)
    exec "$@"
    ;;
esac
