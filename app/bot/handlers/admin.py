"""Мини-админка: полное удаление выбранного агента и его данных для тестирования.

Доступ только у Telegram ID из ADMIN_TELEGRAM_IDS. Секреты не выводятся.
"""

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.database import repositories as repo

logger = logging.getLogger(__name__)
admin_router = Router()


def _is_admin(user_id: int | None, admin_ids: set[int]) -> bool:
    return user_id is not None and user_id in admin_ids


def _agents_keyboard(agents) -> InlineKeyboardMarkup:
    rows = []
    for agent in agents:
        title = agent.name or f"agent {agent.id}"
        label = f"{title} · tg:{agent.telegram_id}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=label[:60], callback_data=f"admin_pick:{agent.telegram_id}"
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _confirm_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Удалить агента", callback_data=f"admin_clear:{telegram_id}"
                ),
                InlineKeyboardButton(text="Отмена", callback_data="admin_cancel"),
            ]
        ]
    )


@admin_router.message(Command("admin"))
async def handle_admin(message: Message, session_factory, admin_ids: set[int]) -> None:
    if not _is_admin(message.from_user.id, admin_ids):
        logger.warning("Отклонён /admin для telegram_id=%s", message.from_user.id)
        return

    async with session_factory() as session:
        agents = await repo.list_agents(session)

    if not agents:
        await message.answer("Агентов пока нет.")
        return

    await message.answer(
        "Админка. Выберите агента, которого удалить вместе с данными (для тестирования):",
        reply_markup=_agents_keyboard(agents),
    )


@admin_router.callback_query(F.data.startswith("admin_pick:"))
async def handle_admin_pick(query: CallbackQuery, admin_ids: set[int]) -> None:
    if not _is_admin(query.from_user.id, admin_ids):
        await query.answer("Нет доступа.", show_alert=True)
        return
    telegram_id = int(query.data.split(":", 1)[1])
    await query.message.answer(
        f"Удалить агента tg:{telegram_id} и все его данные? Действие необратимо.",
        reply_markup=_confirm_keyboard(telegram_id),
    )
    await query.answer()


@admin_router.callback_query(F.data.startswith("admin_clear:"))
async def handle_admin_clear(
    query: CallbackQuery, session_factory, admin_ids: set[int]
) -> None:
    if not _is_admin(query.from_user.id, admin_ids):
        await query.answer("Нет доступа.", show_alert=True)
        return
    telegram_id = int(query.data.split(":", 1)[1])

    async with session_factory() as session:
        counts = await repo.wipe_agent_data(session, telegram_id)

    if counts is None:
        await query.message.answer(f"Агент tg:{telegram_id} не найден.")
        await query.answer()
        return

    report = "\n".join(f"• {table}: {number}" for table, number in counts.items())
    await query.message.answer(
        f"Агент tg:{telegram_id} удалён:\n{report}"
    )
    await query.answer("Готово.")


@admin_router.callback_query(F.data == "admin_cancel")
async def handle_admin_cancel(query: CallbackQuery, admin_ids: set[int]) -> None:
    if not _is_admin(query.from_user.id, admin_ids):
        await query.answer("Нет доступа.", show_alert=True)
        return
    await query.answer("Отменено.")
    await query.message.answer("Очистка отменена.")
