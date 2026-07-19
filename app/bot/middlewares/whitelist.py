"""Whitelist-доступ: чужие сообщения отклоняются до вызова платного AI."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

logger = logging.getLogger(__name__)


class WhitelistMiddleware(BaseMiddleware):
    """Пропускает дальше только Telegram ID из разрешённого списка."""

    def __init__(self, allowed_ids: set[int]) -> None:
        self._allowed_ids = allowed_ids

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        user_id = user.id if user else None

        if user_id not in self._allowed_ids:
            # Отказ происходит здесь, чтобы не тратить STT/LLM на посторонних.
            logger.warning("Отклонён доступ для telegram_id=%s", user_id)
            if isinstance(event, Message):
                await event.answer("Доступ ограничен.")
            elif isinstance(event, CallbackQuery):
                await event.answer("Доступ ограничен.", show_alert=True)
            return None

        logger.info("Доступ разрешён для telegram_id=%s", user_id)
        return await handler(event, data)
