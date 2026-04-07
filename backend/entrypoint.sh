#!/bin/sh
# ============================================================
# entrypoint.sh — Run DB init/seed scripts then start server
# ============================================================

set -e

RUN_DB_INIT="${RUN_DB_INIT:-true}"
RUN_DB_SEED="${RUN_DB_SEED:-true}"

if [ "$RUN_DB_INIT" = "true" ]; then
  echo "▶ Initialising database tables..."
  python scripts/init_tables.py
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

# 检查是否启用浏览器登录服务
if [ "$BROWSER_LOGIN_ENABLED" = "true" ]; then
  echo "🌐 Browser login service enabled on port ${BROWSER_LOGIN_PORT:-8003}"
  echo "🖥️  Remote desktop (noVNC) available on port ${NOVNC_PORT:-6080}"
  exec python start_services.py
else
  # 传统模式：只启动主服务
  if [ "$DEV_MODE" = "true" ]; then
    echo "DEV_MODE=true, starting Uvicorn with --reload"
    exec uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
  else
    exec uvicorn src.main:app --host 0.0.0.0 --port 8000
  fi
fi
