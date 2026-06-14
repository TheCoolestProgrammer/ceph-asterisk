#!/bin/sh
set -e

echo "Ожидание готовности MySQL..."
uv run python - <<'PY'
import sys
import time

from sqlalchemy import create_engine, text

from app.core.config import config

urls = [config.DATABASE_URL, config.DATABASE_CDR_URL]
deadline = time.time() + 90

while time.time() < deadline:
    try:
        for url in urls:
            engine = create_engine(url)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        print("MySQL готов.")
        sys.exit(0)
    except Exception:
        time.sleep(2)

print("MySQL не ответил за 90 секунд.", file=sys.stderr)
sys.exit(1)
PY

echo "Применение миграций Alembic..."
uv run alembic -x db=main upgrade main@head
uv run alembic -x db=cdr upgrade cdr@head

echo "Запуск приложения..."
exec "$@"
