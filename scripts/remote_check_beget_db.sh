#!/bin/bash
set -e
echo "=== DATABASE_URL host (masked) ==="
grep "^DATABASE_URL=" /opt/telecrm/.env | sed -E 's#(mysql\+aiomysql://)([^:]+):([^@]+)@#\1\2:***@#'
echo "=== connect 10.16.0.2:3306 ==="
if timeout 5 bash -c 'echo >/dev/tcp/10.16.0.2/3306' 2>/dev/null; then
  echo PORT_OPEN
else
  echo PORT_CLOSED
fi
ping -c 1 -W 2 10.16.0.2 2>&1 | head -5 || true
echo "=== local IPs ==="
ip -4 addr | grep inet || true
