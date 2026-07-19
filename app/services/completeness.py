"""Проверка обязательных полей черновика и разбор точечных ответов пользователя.

Роль клиента определяется по содержимому сообщения:
- продавец/собственник — есть объект (`property`) или сделка на продажу;
- покупатель — есть потребности (`demand`) или сделка на покупку;
- если ничего не указывает на покупателя, клиент считается продавцом
  (по договорённости: «если есть клиент, должен быть объект»).

Ответы на уточняющие вопросы разбираются локально, без обращения к LLM, чтобы
не тратить токены на простые подстановки (телефон, число комнат, цена и т.п.).
"""

import re
from decimal import Decimal, InvalidOperation

from app.ai.schemas import ClientData, DealType, DemandData, LLMResult, PropertyData
from app.utils.phone import normalize_phone

# Человеческие подсказки для каждого обязательного поля.
FIELD_PROMPTS: dict[str, str] = {
    "client.name": "Укажите ФИО клиента.",
    "client.phone": "Укажите телефон клиента (например, +79001234567).",
    "property.city": "Укажите город объекта.",
    "property.address": "Укажите адрес объекта (улица и дом).",
    "property.rooms_count": "Сколько комнат в объекте? Укажите числом, например 2.",
    "property.total_area": "Какая площадь объекта в кв. м? Например 45 или 45.5.",
    "property.price": "Какая цена объекта? Например 5000000 или 5 млн.",
    "demand.rooms_desired": "Какая комнатность нужна покупателю? Например 2 или 2,3.",
    "demand.area": "Какая площадь нужна покупателю? Например 50 или 50-70 кв. м.",
    "demand.budget": "Какой бюджет покупки? Например 5 млн или 4-6 млн.",
}


def _is_buyer(draft: LLMResult) -> bool:
    if draft.demand is not None:
        return True
    if draft.deal is not None and draft.deal.deal_type == DealType.BUY:
        return True
    return False


def _is_seller(draft: LLMResult) -> bool:
    if draft.property is not None:
        return True
    if draft.deal is not None and draft.deal.deal_type == DealType.SELL:
        return True
    # По умолчанию клиент — продавец, если ничто не указывает на покупателя.
    return not _is_buyer(draft)


def missing_required(draft: LLMResult) -> list[str]:
    """Возвращает список ключей обязательных полей, которых не хватает."""
    missing: list[str] = []

    client = draft.client
    if not (client and client.name and client.name.strip()):
        missing.append("client.name")
    if not (client and client.phone and normalize_phone(client.phone)):
        missing.append("client.phone")

    if _is_seller(draft):
        prop = draft.property
        if not (prop and prop.city and prop.city.strip()):
            missing.append("property.city")
        if not (prop and prop.address and prop.address.strip()):
            missing.append("property.address")
        if not (prop and prop.rooms_count is not None):
            missing.append("property.rooms_count")
        if not (prop and prop.total_area is not None):
            missing.append("property.total_area")
        if not (prop and prop.price is not None):
            missing.append("property.price")

    if _is_buyer(draft):
        demand = draft.demand
        if not (demand and demand.rooms_desired):
            missing.append("demand.rooms_desired")
        if not (demand and (demand.min_area is not None or demand.max_area is not None)):
            missing.append("demand.area")
        if not (demand and (demand.budget_min is not None or demand.budget_max is not None)):
            missing.append("demand.budget")

    return missing


def _ensure_client(draft: LLMResult) -> ClientData:
    if draft.client is None:
        draft.client = ClientData()
    return draft.client


def _ensure_property(draft: LLMResult) -> PropertyData:
    if draft.property is None:
        draft.property = PropertyData()
    return draft.property


def _ensure_demand(draft: LLMResult) -> DemandData:
    if draft.demand is None:
        draft.demand = DemandData()
    return draft.demand


def _parse_int(text: str) -> int | None:
    match = re.search(r"-?\d+", text)
    return int(match.group()) if match else None


def _parse_decimal(text: str) -> Decimal | None:
    cleaned = text.replace(" ", "").replace(",", ".")
    match = re.search(r"\d+(?:\.\d+)?", cleaned)
    if not match:
        return None
    try:
        return Decimal(match.group())
    except InvalidOperation:
        return None


def _parse_amount(text: str) -> Decimal | None:
    """Разбирает денежную сумму с учётом суффиксов «млн» и «тыс»."""
    lowered = text.lower()
    value = _parse_decimal(lowered)
    if value is None:
        return None
    if "млн" in lowered or "миллион" in lowered:
        value *= Decimal("1000000")
    elif "тыс" in lowered:
        value *= Decimal("1000")
    return value


def _parse_int_list(text: str) -> list[int]:
    return [int(n) for n in re.findall(r"\d+", text)]


def _parse_range(text: str) -> tuple[Decimal | None, Decimal | None]:
    """Разбирает «50» или «50-70» в (min, max) для площади."""
    numbers = re.findall(r"\d+(?:[.,]\d+)?", text.replace(" ", ""))
    values = [Decimal(n.replace(",", ".")) for n in numbers]
    if not values:
        return None, None
    if len(values) == 1:
        return values[0], None
    return values[0], values[1]


def _parse_amount_range(text: str) -> tuple[Decimal | None, Decimal | None]:
    """Разбирает бюджет «5 млн» или «4-6 млн» в (min, max)."""
    lowered = text.lower()
    multiplier = Decimal("1")
    if "млн" in lowered or "миллион" in lowered:
        multiplier = Decimal("1000000")
    elif "тыс" in lowered:
        multiplier = Decimal("1000")
    numbers = re.findall(r"\d+(?:[.,]\d+)?", lowered.replace(" ", ""))
    values = [Decimal(n.replace(",", ".")) * multiplier for n in numbers]
    if not values:
        return None, None
    if len(values) == 1:
        # Одно число трактуем как верхнюю границу бюджета.
        return None, values[0]
    return values[0], values[1]


def apply_field(draft: LLMResult, key: str, raw_text: str) -> str | None:
    """Записывает ответ пользователя в поле черновика.

    Возвращает текст ошибки, если значение не распозналось, иначе None.
    """
    text = raw_text.strip()
    if not text:
        return "Пустой ответ. Попробуйте ещё раз."

    if key == "client.name":
        _ensure_client(draft).name = text
    elif key == "client.phone":
        phone = normalize_phone(text)
        if not phone:
            return "Не удалось распознать телефон. Пример: +79001234567."
        _ensure_client(draft).phone = phone
    elif key == "property.city":
        _ensure_property(draft).city = text
    elif key == "property.address":
        _ensure_property(draft).address = text
    elif key == "property.rooms_count":
        value = _parse_int(text)
        if value is None or value < 0:
            return "Укажите число комнат, например 2."
        _ensure_property(draft).rooms_count = value
    elif key == "property.total_area":
        value = _parse_decimal(text)
        if value is None or value <= 0:
            return "Укажите площадь числом, например 45 или 45.5."
        _ensure_property(draft).total_area = value
    elif key == "property.price":
        value = _parse_amount(text)
        if value is None or value <= 0:
            return "Укажите цену числом, например 5000000 или 5 млн."
        _ensure_property(draft).price = value
    elif key == "demand.rooms_desired":
        rooms = _parse_int_list(text)
        if not rooms:
            return "Укажите комнатность, например 2 или 2,3."
        _ensure_demand(draft).rooms_desired = rooms
    elif key == "demand.area":
        low, high = _parse_range(text)
        if low is None and high is None:
            return "Укажите площадь, например 50 или 50-70."
        demand = _ensure_demand(draft)
        demand.min_area, demand.max_area = low, high
    elif key == "demand.budget":
        low, high = _parse_amount_range(text)
        if low is None and high is None:
            return "Укажите бюджет, например 5 млн или 4-6 млн."
        demand = _ensure_demand(draft)
        demand.budget_min, demand.budget_max = low, high
    else:
        return "Неизвестное поле."

    return None
