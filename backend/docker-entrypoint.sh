#!/bin/sh
set -eu

wait_for_port() {
  host="$1"
  port="$2"
  label="$3"

  python - "$host" "$port" "$label" <<'PY'
import socket
import sys
import time

host, port, label = sys.argv[1], int(sys.argv[2]), sys.argv[3]
for _ in range(60):
    try:
        with socket.create_connection((host, port), timeout=2):
            raise SystemExit(0)
    except OSError:
        time.sleep(2)
raise SystemExit(f'{label} did not become reachable at {host}:{port}')
PY
}

wait_for_port "${DB_HOST:-db}" "${DB_PORT:-3306}" "MySQL"
wait_for_port "redis" "6379" "Redis"
wait_for_port "qdrant" "6333" "Qdrant"

case "${1:-web}" in
  web)
    python manage.py migrate --noinput
    python manage.py collectstatic --noinput
    python manage.py initialize_qdrant
    exec gunicorn MoonBirdNotes.wsgi:application \
      --bind 0.0.0.0:8000 \
      --workers "${GUNICORN_WORKERS:-1}" \
      --worker-class gthread \
      --threads "${GUNICORN_THREADS:-2}" \
      --timeout 180 \
      --access-logfile - \
      --error-logfile -
    ;;
  worker)
    while true; do
      python manage.py process_rag_jobs --max-jobs "${RAG_WORKER_MAX_JOBS:-100}"
      sleep "${RAG_WORKER_POLL_SECONDS:-10}"
    done
    ;;
  *)
    exec "$@"
    ;;
esac
