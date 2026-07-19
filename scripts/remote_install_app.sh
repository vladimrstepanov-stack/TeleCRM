#!/bin/bash
set -euo pipefail
cd /opt/telecrm

PASS=$(cat /root/.telecrm_mysql_pass)
DB_URL="mysql+aiomysql://telecrm:${PASS}@127.0.0.1:3306/telecrm?charset=utf8mb4"

if [[ ! -f /opt/telecrm/.env ]]; then
  cat > /opt/telecrm/.env <<EOF
ALLOWED_TELEGRAM_IDS=REPLACE_TELEGRAM_ID
TELEGRAM_BOT_TOKEN=REPLACE_BOT_TOKEN
DATABASE_URL=${DB_URL}
AITUNNEL_BASE_URL=https://api.aitunnel.ru/v1
AITUNNEL_API_KEY=REPLACE_AITUNNEL_KEY
STT_MODEL=qwen3-asr-flash-2026-02-10
DEEPSEEK_MODEL=deepseek-chat
LOG_LEVEL=INFO
EOF
  chmod 600 /opt/telecrm/.env
  echo "CREATED_ENV_PLACEHOLDERS"
else
  # keep secrets, refresh DATABASE_URL
  if grep -q '^DATABASE_URL=' /opt/telecrm/.env; then
    sed -i "s|^DATABASE_URL=.*|DATABASE_URL=${DB_URL}|" /opt/telecrm/.env
  else
    echo "DATABASE_URL=${DB_URL}" >> /opt/telecrm/.env
  fi
  echo "UPDATED_DATABASE_URL"
fi

python3 -m venv /opt/telecrm/.venv
# shellcheck disable=SC1091
source /opt/telecrm/.venv/bin/activate
pip install -U pip wheel
pip install -e "/opt/telecrm[dev]"

# migrations need valid settings - temporarily use dummy secrets if placeholders
if grep -q REPLACE_ /opt/telecrm/.env; then
  echo "SKIP_MIGRATE_NEED_SECRETS"
else
  alembic upgrade head
  echo "MIGRATE_OK"
fi

echo INSTALL_OK
