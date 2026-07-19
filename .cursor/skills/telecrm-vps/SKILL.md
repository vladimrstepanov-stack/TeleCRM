---
name: telecrm-vps
description: SSH и деплой TeleCRM на Beget VPS. Use when connecting to production server, restarting bot, checking logs, running migrations, or deploying code changes.
---

# TeleCRM VPS

## SSH (Windows)

```powershell
ssh -i C:\Users\Vladimir\.ssh\id_ed25519_telecrm -o IdentitiesOnly=yes root@155.212.136.250
```

Первичная установка ключа (один раз, спросит пароль root):

```powershell
.\scripts\install-ssh-key.ps1
```

## Paths

| Что | Путь |
|---|---|
| Приложение | `/opt/telecrm` |
| Env | `/opt/telecrm/.env` |
| Логи | `/opt/telecrm/logs/app.log`, `error.log` |
| Сервис | `systemctl status\|restart telecrm` |
| БД | Beget MySQL `default-db` @ `10.16.0.2` (VPS `10.16.0.3`) |
| Локальный проект | `C:\Users\Vladimir\Documents\TeleCRM` |

## Rules

- **Не выводить в чат:** `TELEGRAM_BOT_TOKEN`, `AITUNNEL_API_KEY`, пароли из `DATABASE_URL`.
- Для диагностики: `journalctl -u telecrm` и `logs/app.log` / `logs/error.log`.
- На сервере **нет git-remote** — код доставляется через `scp` + `tar`, не `git pull`.
- Локально на Windows может не быть Python/git — тесты и деплой гонять на сервере (venv: `/opt/telecrm/.venv`).

## Частые команды (на сервере)

```bash
# Статус
systemctl is-active telecrm
systemctl status telecrm --no-pager -l | head -20

# Логи
tail -n 50 /opt/telecrm/logs/error.log
tail -n 30 /opt/telecrm/logs/app.log
journalctl -u telecrm -n 30 --no-pager

# Рестарт
systemctl restart telecrm

# Миграции
cd /opt/telecrm && .venv/bin/alembic upgrade head

# Тесты
cd /opt/telecrm && PYTHONPATH=/opt/telecrm .venv/bin/python -m pytest -q
```

## Админ

В `/opt/telecrm/.env`:

```env
ADMIN_TELEGRAM_IDS=7768522585
```

После правки `.env` — `systemctl restart telecrm`. Команда в боте: `/admin`.

## Деплой (Windows → сервер)

1. Собрать архив локально:

```powershell
tar -czf deploy.tgz --exclude=__pycache__ --exclude=*.pyc app tests pyproject.toml
scp -i $env:USERPROFILE\.ssh\id_ed25519_telecrm -o IdentitiesOnly=yes deploy.tgz root@155.212.136.250:/root/deploy.tgz
```

2. На сервере — бэкап, применить, проверить, миграция, рестарт:

```bash
cd /opt/telecrm
cp -r app app.bak && cp -r tests tests.bak && cp pyproject.toml pyproject.toml.bak
tar xzf /root/deploy.tgz -C /opt/telecrm
PYTHONPATH=/opt/telecrm .venv/bin/python -m pytest -q
.venv/bin/alembic upgrade head
systemctl restart telecrm
tail -n 15 logs/app.log
```

3. Откат при проблемах:

```bash
cd /opt/telecrm && rm -rf app && mv app.bak app && systemctl restart telecrm
```

## Безопасная проверка без прода

Распаковать в staging и гонять тесты там:

```bash
rm -rf /root/telecrm_stage && mkdir -p /root/telecrm_stage
tar xzf /root/deploy.tgz -C /root/telecrm_stage
cd /root/telecrm_stage
PYTHONPATH=/root/telecrm_stage /opt/telecrm/.venv/bin/python -m pytest -q
```
