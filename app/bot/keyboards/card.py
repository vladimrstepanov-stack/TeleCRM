"""Inline-клавиатуры карточки, выбора и разрешения дублей.

Подписи кнопок короткие, чтобы помещаться в один ряд Telegram.
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.database.repositories import Card


def card_keyboard(deal_id: int) -> InlineKeyboardMarkup:
    """Три кнопки под карточкой: порядок фиксирован планом."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Обновить", callback_data=f"update:{deal_id}"),
                InlineKeyboardButton(text="К встрече", callback_data=f"meet:{deal_id}"),
                InlineKeyboardButton(text="Отчёт", callback_data=f"report:{deal_id}"),
            ]
        ]
    )


def candidates_keyboard(cards: list[Card]) -> InlineKeyboardMarkup:
    """Компактный список найденных вариантов."""
    rows = []
    for card in cards:
        label = f"{card.client.name} · {card.property.city}, {card.property.address}"
        rows.append(
            [InlineKeyboardButton(text=label[:60], callback_data=f"pick:{card.deal.id}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_save_keyboard() -> InlineKeyboardMarkup:
    """Подтверждение записи собранного черновика в базу."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Внести данные", callback_data="save_confirm"),
                InlineKeyboardButton(text="Отмена", callback_data="save_cancel"),
            ]
        ]
    )


def duplicate_keyboard(keep_client_id: int) -> InlineKeyboardMarkup:
    """Выбор действия при совпадении телефона."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Объединить", callback_data=f"merge:{keep_client_id}"
                ),
                InlineKeyboardButton(text="Раздельно", callback_data="separate"),
            ]
        ]
    )
