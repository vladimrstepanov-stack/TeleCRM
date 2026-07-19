#!/bin/bash
set -euo pipefail
PASS=$(openssl rand -base64 18 | tr -d '/+=' | head -c 24)
mysql <<SQL
CREATE DATABASE IF NOT EXISTS telecrm CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'telecrm'@'localhost' IDENTIFIED BY '${PASS}';
ALTER USER 'telecrm'@'localhost' IDENTIFIED BY '${PASS}';
GRANT ALL PRIVILEGES ON telecrm.* TO 'telecrm'@'localhost';
FLUSH PRIVILEGES;
SQL
printf '%s' "$PASS" > /root/.telecrm_mysql_pass
chmod 600 /root/.telecrm_mysql_pass
echo DB_OK
