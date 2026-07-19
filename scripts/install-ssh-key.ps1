# Одноразово: копирует ключ telecrm на VPS (спросит пароль root).
$ErrorActionPreference = "Stop"
$ip = "155.212.136.250"
$pub = Get-Content "$env:USERPROFILE\.ssh\id_ed25519_telecrm.pub" -Raw
Write-Host "Подключаюсь к root@$ip — введите пароль VPS..."
$pub.Trim() | ssh -o StrictHostKeyChecking=accept-new "root@$ip" "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && echo KEY_INSTALLED"
Write-Host "Готово. Проверка входа по ключу..."
ssh -i "$env:USERPROFILE\.ssh\id_ed25519_telecrm" -o BatchMode=yes "root@$ip" "echo SSH_KEY_OK"
