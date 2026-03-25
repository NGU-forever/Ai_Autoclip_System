#!/bin/sh
# ============================================================
# entrypoint.sh — Run DB init/seed scripts then start server
# ============================================================

set -e

RUN_DB_INIT="${RUN_DB_INIT:-true}"
RUN_DB_SEED="${RUN_DB_SEED:-true}"

if [ "$RUN_DB_INIT" = "true" ]; then
  echo "▶ Initialising database tables..."
  python scripts/init_new_tables.py
else
  echo "⏭️ RUN_DB_INIT=false, skip DB init"
fi

if [ "$RUN_DB_SEED" = "true" ]; then
  echo "▶ Seeding users..."
  python scripts/seed_users.py
else
  echo "⏭️ RUN_DB_SEED=false, skip seed scripts"
fi

echo "✅ DB setup complete. Starting API server..."

if [ "$DEV_MODE" = "true" ]; then
  echo "DEV_MODE=true, starting Uvicorn with --reload"
  exec uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
else
  exec uvicorn src.main:app --host 0.0.0.0 --port 8000
fi
