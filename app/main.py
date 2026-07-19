"""Точка входа: запуск Telegram-бота в режиме long polling."""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.ai.deepseek import DeepSeekParser
from app.ai.stt import SpeechToText
from app.bot.handlers.admin import admin_router
from app.bot.handlers.router import router
from app.bot.middlewares.whitelist import WhitelistMiddleware
from app.config import get_settings
from app.database.base import get_session_factory, init_engine
from app.logging import configure_logging
from app.services.intake import Intake

logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("Запуск Voice CRM бота")

    init_engine(settings.database_url.get_secret_value())

    stt = SpeechToText(
        base_url=settings.aitunnel_base_url,
        api_key=settings.aitunnel_api_key.get_secret_value(),
        model=settings.stt_model,
    )
    parser = DeepSeekParser(
        base_url=settings.aitunnel_base_url,
        api_key=settings.aitunnel_api_key.get_secret_value(),
        model=settings.deepseek_model,
    )
    intake = Intake(stt=stt, parser=parser)

    bot = Bot(
        token=settings.telegram_bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()

    # Whitelist срабатывает до обработчиков и до любых платных AI-вызовов.
    # Админы всегда входят в число разрешённых.
    allowed_ids = settings.allowed_telegram_ids | settings.admin_telegram_ids
    whitelist = WhitelistMiddleware(allowed_ids)
    dispatcher.message.middleware(whitelist)
    dispatcher.callback_query.middleware(whitelist)

    # Общие зависимости прокидываются в обработчики через workflow data.
    dispatcher["intake"] = intake
    dispatcher["session_factory"] = get_session_factory()
    dispatcher["admin_ids"] = settings.admin_telegram_ids

    # Админ-роутер включаем первым, чтобы команда /admin не попадала в общий
    # обработчик текста.
    dispatcher.include_router(admin_router)
    dispatcher.include_router(router)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("Бот остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Остановка по сигналу")
