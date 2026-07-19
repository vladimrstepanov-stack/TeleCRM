"""Нормализация телефонов для надёжной дедупликации карточек."""

import re


def normalize_phone(raw: str | None) -> str | None:
    """Приводит телефон к формату +7XXXXXXXXXX.

    Возвращает None, если распознать номер не удалось: без телефона
    автоматическое объединение клиентов не выполняется.
    """
    if not raw:
        return None

    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None

    # Российские номера: 8XXXXXXXXXX и 7XXXXXXXXXX приводим к +7XXXXXXXXXX.
    if len(digits) == 11 and digits[0] in {"7", "8"}:
        return "+7" + digits[1:]
    if len(digits) == 10:
        return "+7" + digits
    return "+" + digits
