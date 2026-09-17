#!/usr/bin/env sh
# Production entrypoint: apply migrations, then start the API.
# Seeding is deliberately NOT automatic - a production database should never be
# populated with demo claims by a container restart.
set -e

echo "==> waiting for the database"
python - <<'PY'
import sys, time
from sqlalchemy import text
from app.db.session import engine
for attempt in range(60):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("database reachable")
        sys.exit(0)
    except Exception as exc:
        print(f"  attempt {attempt + 1}: {type(exc).__name__}")
        time.sleep(2)
print("database unreachable", file=sys.stderr)
sys.exit(1)
PY

echo "==> applying migrations"
alembic upgrade head

if [ "${SEED_ON_START}" = "true" ]; then
  echo "==> seeding demo data (SEED_ON_START=true)"
  python -m app.db.seed
fi

echo "==> starting: $*"
exec "$@"
