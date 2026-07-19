"""Обработчики Telegram: приём сообщений, поиск, кнопки и выдача документов."""

import logging

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.ai.deepseek import LLMParseError
from app.ai.schemas import Intent, LLMResult
from app.bot.keyboards.card import (
    candidates_keyboard,
    card_keyboard,
    confirm_save_keyboard,
    duplicate_keyboard,
)
from app.bot.states import Flow
from app.database import repositories as repo
from app.database.repositories import Card
from app.services import crm, search
from app.services.completeness import FIELD_PROMPTS, apply_field, missing_required
from app.services.docx import build_meeting_doc, build_owner_report
from app.services.intake import Intake
from app.utils.phone import normalize_phone
from app.utils.tempfiles import temp_path

logger = logging.getLogger(__name__)
router = Router()

CONTINUATION = (
    "Можно отправить голосом или текстом новые данные (клиент, объект, статус и т.д.) "
    "или запросить данные по клиенту/объекту."
)


def _render_card(card: Card) -> str:
    phone = card.client.phone or "телефон не указан"
    address = ", ".join(
        part
        for part in (card.property.city, card.property.address)
        if part and part != "не указан"
    )
    price = (
        f"{card.property.price:,.0f} руб.".replace(",", " ")
        if card.property.price is not None
        else "не указана"
    )
    return (
        f"<b>Клиент:</b> {card.client.name} ({phone})\n"
        f"<b>Объект:</b> {address or 'не указан'}\n"
        f"<b>Цена:</b> {price}\n"
        f"<b>Статус объекта:</b> {card.property.status}\n"
        f"<b>Статус сделки:</b> {card.deal.status}"
    )


async def _extract_text(message: Message, bot: Bot, intake: Intake) -> str | None:
    """Возвращает текст сообщения: напрямую или через распознавание голоса."""
    if message.text:
        return message.text
    if message.voice:
        with temp_path(".ogg") as audio_path:
            await bot.download(message.voice, destination=audio_path)
            return await intake.transcribe(audio_path)
    return None


@router.message(CommandStart())
async def handle_start(message: Message, state: FSMContext, session_factory) -> None:
    await state.clear()
    async with session_factory() as session:
        agent = await repo.get_or_create_agent(session, message.from_user.id)
        await session.commit()
        needs_onboarding = repo.agent_needs_onboarding(agent)

    if needs_onboarding:
        await state.set_state(Flow.onboarding_name)
        await message.answer(
            "Это голосовая CRM. Давайте познакомимся — как вас зовут? Укажите ФИО."
        )
        return

    await message.answer("Это голосовая CRM. " + CONTINUATION)


async def _maybe_start_onboarding(
    message: Message, state: FSMContext, session_factory
) -> bool:
    """Запускает онбординг, если у агента ещё нет ФИО и телефона."""
    async with session_factory() as session:
        agent = await repo.get_or_create_agent(session, message.from_user.id)
        await session.commit()
        needs_onboarding = repo.agent_needs_onboarding(agent)

    if needs_onboarding:
        await state.set_state(Flow.onboarding_name)
        await message.answer("Давайте познакомимся — как вас зовут? Укажите ФИО.")
        return True
    return False


async def _onboarding_name(message: Message, state: FSMContext, text: str) -> None:
    name = text.strip()
    if len(name) < 2:
        await message.answer("Имя слишком короткое. Укажите ФИО.")
        return
    await state.update_data(agent_name=name)
    await state.set_state(Flow.onboarding_phone)
    await message.answer(
        f"Приятно познакомиться, {name}! Укажите ваш телефон (например, +79001234567)."
    )


async def _onboarding_phone(
    message: Message, state: FSMContext, text: str, session_factory
) -> None:
    phone = normalize_phone(text)
    if not phone:
        await message.answer("Не удалось распознать телефон. Пример: +79001234567.")
        return
    data = await state.get_data()
    name = data.get("agent_name")
    async with session_factory() as session:
        agent = await repo.get_or_create_agent(session, message.from_user.id)
        agent.name = name
        agent.phone = phone
        await session.commit()
    await state.clear()
    await message.answer("Спасибо, вы зарегистрированы. " + CONTINUATION)


@router.message(F.text | F.voice)
async def handle_input(
    message: Message,
    state: FSMContext,
    bot: Bot,
    intake: Intake,
    session_factory,
) -> None:
    text = await _extract_text(message, bot, intake)
    if not text:
        await message.answer("Не удалось прочитать сообщение. Попробуйте ещё раз.")
        return

    current_state = await state.get_state()

    # Онбординг агента при первой встрече: сначала ФИО, затем телефон.
    if current_state == Flow.onboarding_name.state:
        await _onboarding_name(message, state, text)
        return
    if current_state == Flow.onboarding_phone.state:
        await _onboarding_phone(message, state, text, session_factory)
        return

    # Ветка ожидания решения по дублю: просим нажать кнопку.
    if current_state == Flow.resolving_duplicate.state:
        await message.answer("Выберите: «Объединить» или «Раздельно».")
        return

    # Ветка ожидания идентификатора после неудачного поиска.
    if current_state == Flow.waiting_identifier.state:
        await _handle_identifier(message, state, text, session_factory)
        return

    # Ответ на уточняющий вопрос по недостающему полю — разбираем без LLM.
    if current_state == Flow.collecting_field.state:
        await _handle_collecting(message, state, text)
        return

    # Новое сообщение во время ожидания подтверждения отменяет черновик и
    # начинает разбор заново.
    if current_state == Flow.confirming_save.state:
        await state.clear()
        current_state = None

    # Если агент ещё не представился — сначала онбординг, до платного LLM.
    if current_state is None and await _maybe_start_onboarding(
        message, state, session_factory
    ):
        return

    try:
        llm = await intake.interpret(text)
    except LLMParseError:
        logger.warning("Не удалось разобрать сообщение в схему LLM")
        await message.answer(
            "Не удалось разобрать сообщение. Попробуйте сформулировать короче и "
            "конкретнее (клиент, объект, действие)."
        )
        return

    # Режим правки текущей карточки (после кнопки «Обновить»).
    if current_state == Flow.updating_card.state:
        data = await state.get_data()
        await _apply_update(message, state, text, llm, data.get("deal_id"), session_factory)
        return

    if llm.intent == Intent.FETCH_DATA:
        await _handle_fetch(message, state, llm, session_factory)
    else:
        await _start_upsert(message, state, text, llm)


async def _start_upsert(
    message: Message, state: FSMContext, text: str, llm: LLMResult
) -> None:
    """Проверяет обязательные поля: спрашивает недостающее либо показывает превью."""
    await state.update_data(
        draft_llm=llm.model_dump_json(),
        source_text=text,
        transcript=text if message.voice else None,
    )

    missing = missing_required(llm)
    if missing:
        await state.set_state(Flow.collecting_field)
        await state.update_data(pending_field=missing[0])
        await message.answer(FIELD_PROMPTS[missing[0]])
        return

    await state.set_state(Flow.confirming_save)
    await message.answer(_render_preview(llm), reply_markup=confirm_save_keyboard())


async def _handle_collecting(message: Message, state: FSMContext, text: str) -> None:
    """Записывает ответ пользователя в недостающее поле черновика."""
    data = await state.get_data()
    draft = LLMResult.model_validate_json(data["draft_llm"])
    pending = data.get("pending_field")
    if pending is None:
        await state.clear()
        await message.answer("Черновик не найден, начните заново.")
        return

    error = apply_field(draft, pending, text)
    if error:
        await message.answer(f"{error}\n{FIELD_PROMPTS[pending]}")
        return

    await state.update_data(draft_llm=draft.model_dump_json())

    missing = missing_required(draft)
    if missing:
        await state.update_data(pending_field=missing[0])
        await message.answer(FIELD_PROMPTS[missing[0]])
        return

    await state.set_state(Flow.confirming_save)
    await message.answer(_render_preview(draft), reply_markup=confirm_save_keyboard())


def _money(value) -> str:
    return f"{value:,.0f} руб.".replace(",", " ")


def _range(low, high) -> str:
    if low is not None and high is not None:
        return f"{low}–{high}"
    return str(low if low is not None else high)


def _render_preview(llm: LLMResult) -> str:
    """Показывает, что именно и в какие поля будет внесено."""
    lines: list[str] = ["<b>Проверьте данные перед сохранением:</b>", ""]

    client = llm.client
    if client and (client.name or client.phone or client.lead_source):
        lines.append("<b>Клиент</b>")
        if client.name:
            lines.append(f"• ФИО: {client.name}")
        if client.phone:
            lines.append(f"• Телефон: {client.phone}")
        if client.lead_source:
            lines.append(f"• Источник: {client.lead_source}")
        lines.append("")

    prop = llm.property
    if prop and any(
        v is not None
        for v in (prop.city, prop.address, prop.rooms_count, prop.total_area, prop.price)
    ):
        lines.append("<b>Объект</b>")
        if prop.city:
            lines.append(f"• Город: {prop.city}")
        if prop.address:
            lines.append(f"• Адрес: {prop.address}")
        if prop.rooms_count is not None:
            lines.append(f"• Комнат: {prop.rooms_count}")
        if prop.total_area is not None:
            lines.append(f"• Площадь: {prop.total_area} кв. м")
        if prop.price is not None:
            lines.append(f"• Цена: {_money(prop.price)}")
        if prop.status is not None:
            lines.append(f"• Статус: {prop.status.value}")
        lines.append("")

    demand = llm.demand
    if demand:
        lines.append("<b>Потребности покупателя</b>")
        if demand.rooms_desired:
            lines.append(f"• Комнатность: {', '.join(map(str, demand.rooms_desired))}")
        if demand.min_area is not None or demand.max_area is not None:
            lines.append(f"• Площадь: {_range(demand.min_area, demand.max_area)} кв. м")
        if demand.budget_min is not None or demand.budget_max is not None:
            lines.append(f"• Бюджет: {_range(demand.budget_min, demand.budget_max)} руб.")
        if demand.cities:
            lines.append(f"• Города: {', '.join(demand.cities)}")
        lines.append("")

    deal = llm.deal
    if deal and (deal.deal_type or deal.status or deal.offer_price or deal.notes):
        lines.append("<b>Сделка</b>")
        if deal.deal_type is not None:
            lines.append(f"• Тип: {deal.deal_type.value}")
        if deal.status is not None:
            lines.append(f"• Статус: {deal.status.value}")
        if deal.offer_price is not None:
            lines.append(f"• Оффер: {_money(deal.offer_price)}")
        if deal.notes:
            lines.append(f"• Заметки: {deal.notes}")
        lines.append("")

    if llm.activities:
        lines.append("<b>Активности</b>")
        for activity in llm.activities:
            lines.append(f"• {activity.activity_type.value}: {activity.summarized_action}")
        lines.append("")

    lines.append("Нажмите «Внести данные», чтобы сохранить.")
    return "\n".join(lines).strip()


async def _finalize_upsert(
    answer_to: Message,
    state: FSMContext,
    user_id: int,
    llm: LLMResult,
    source_text: str,
    transcript: str | None,
    session_factory,
) -> None:
    """Фактическая запись подтверждённого черновика и отчёт пользователю."""
    async with session_factory() as session:
        agent = await repo.get_or_create_agent(session, user_id)
        outcome = await crm.apply_upsert(
            session,
            agent_id=agent.id,
            telegram_id=user_id,
            llm=llm,
            source_text=source_text,
            transcript=transcript,
        )

    if outcome.needs_clarification:
        await state.clear()
        await answer_to.answer(outcome.needs_clarification)
        return

    if outcome.duplicate_candidates:
        keep = outcome.duplicate_candidates[0]
        await state.set_state(Flow.resolving_duplicate)
        await state.update_data(
            source_text=source_text,
            transcript=transcript,
            llm_json=llm.model_dump_json(),
            keep_client_id=keep.id,
        )
        await answer_to.answer(
            f"Найден клиент с таким телефоном: {keep.name}. Объединить карточки или "
            "оставить раздельно?",
            reply_markup=duplicate_keyboard(keep.id),
        )
        return

    await state.clear()
    await answer_to.answer(
        "Данные сохранены.\n\n" + _render_card(outcome.card),
        reply_markup=card_keyboard(outcome.card.deal.id),
    )
    await answer_to.answer(CONTINUATION)


async def _handle_fetch(
    message: Message, state: FSMContext, llm: LLMResult, session_factory
) -> None:
    criteria = llm.search
    async with session_factory() as session:
        agent = await repo.get_or_create_agent(session, message.from_user.id)
        cards = (
            await search.find_cards(session, agent.id, criteria) if criteria else []
        )

    if not cards:
        await state.set_state(Flow.waiting_identifier)
        await message.answer(
            "Ничего не найдено. Пришлите телефон клиента (или другие данные для поиска)."
        )
        return

    await _present_cards(message, state, cards)


async def _handle_identifier(
    message: Message, state: FSMContext, text: str, session_factory
) -> None:
    from app.ai.schemas import SearchCriteria

    async with session_factory() as session:
        agent = await repo.get_or_create_agent(session, message.from_user.id)
        # Пробуем и как телефон, и как имя/адрес одновременно.
        cards = await search.find_cards(
            session,
            agent.id,
            SearchCriteria(phone=text, client_name=text, address=text),
        )

    if not cards:
        await message.answer("Всё ещё ничего не найдено. Пришлите телефон клиента.")
        return

    await state.clear()
    await _present_cards(message, state, cards)


async def _present_cards(message: Message, state: FSMContext, cards: list[Card]) -> None:
    if len(cards) == 1:
        await state.clear()
        card = cards[0]
        await message.answer(
            _render_card(card), reply_markup=card_keyboard(card.deal.id)
        )
        return

    await message.answer(
        "Найдено несколько вариантов, выберите нужный:",
        reply_markup=candidates_keyboard(cards),
    )


async def _apply_update(
    message: Message,
    state: FSMContext,
    text: str,
    llm: LLMResult,
    deal_id: int | None,
    session_factory,
) -> None:
    if deal_id is None:
        await state.clear()
        await message.answer("Карточка для обновления не найдена.")
        return

    async with session_factory() as session:
        agent = await repo.get_or_create_agent(session, message.from_user.id)
        card = await repo.get_card_by_deal(session, agent.id, deal_id)
        if card is None:
            await state.clear()
            await message.answer("Карточка не найдена.")
            return
        outcome = await crm.apply_upsert(
            session,
            agent_id=agent.id,
            telegram_id=message.from_user.id,
            llm=llm,
            source_text=text,
            transcript=text if message.voice else None,
            target_card=card,
        )

    await state.clear()
    await message.answer("Карточка обновлена.")
    await message.answer(
        _render_card(outcome.card), reply_markup=card_keyboard(outcome.card.deal.id)
    )
    await message.answer(CONTINUATION)


@router.callback_query(F.data.startswith("pick:"))
async def handle_pick(query: CallbackQuery, state: FSMContext, session_factory) -> None:
    deal_id = int(query.data.split(":", 1)[1])
    async with session_factory() as session:
        agent = await repo.get_or_create_agent(session, query.from_user.id)
        card = await repo.get_card_by_deal(session, agent.id, deal_id)
    await state.clear()
    if card is None:
        await query.answer("Карточка не найдена.", show_alert=True)
        return
    await query.message.answer(_render_card(card), reply_markup=card_keyboard(deal_id))
    await query.answer()


@router.callback_query(F.data.startswith("update:"))
async def handle_update_button(query: CallbackQuery, state: FSMContext) -> None:
    deal_id = int(query.data.split(":", 1)[1])
    await state.set_state(Flow.updating_card)
    await state.update_data(deal_id=deal_id)
    await query.message.answer(
        "Режим обновления. Пришлите голосом или текстом изменения (цена, статус, показ, оферта)."
    )
    await query.answer()


@router.callback_query(F.data == "save_confirm")
async def handle_save_confirm(
    query: CallbackQuery, state: FSMContext, session_factory
) -> None:
    data = await state.get_data()
    draft_json = data.get("draft_llm")
    if not draft_json:
        await query.answer("Черновик не найден, начните заново.", show_alert=True)
        await state.clear()
        return
    llm = LLMResult.model_validate_json(draft_json)
    await _finalize_upsert(
        query.message,
        state,
        query.from_user.id,
        llm,
        data.get("source_text", ""),
        data.get("transcript"),
        session_factory,
    )
    await query.answer()


@router.callback_query(F.data == "save_cancel")
async def handle_save_cancel(query: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await query.answer("Отменено.")
    await query.message.answer("Ввод отменён. " + CONTINUATION)


@router.callback_query(F.data.startswith("report:"))
async def handle_report(query: CallbackQuery, bot: Bot, session_factory) -> None:
    deal_id = int(query.data.split(":", 1)[1])
    await _send_document(query, bot, session_factory, deal_id, kind="report")


@router.callback_query(F.data.startswith("meet:"))
async def handle_meeting(query: CallbackQuery, bot: Bot, session_factory) -> None:
    deal_id = int(query.data.split(":", 1)[1])
    await _send_document(query, bot, session_factory, deal_id, kind="meeting")


async def _send_document(
    query: CallbackQuery, bot: Bot, session_factory, deal_id: int, *, kind: str
) -> None:
    async with session_factory() as session:
        agent = await repo.get_or_create_agent(session, query.from_user.id)
        card = await repo.get_card_by_deal(session, agent.id, deal_id)
        if card is None:
            await query.answer("Карточка не найдена.", show_alert=True)
            return
        activities, events = await repo.get_property_history(
            session, agent.id, card.property.id
        )

    date_tag = _today_tag()
    if kind == "report":
        filename = f"otchet_sobstvenniku_{card.property.id}_{date_tag}.docx"
    else:
        filename = f"k_vstreche_{card.property.id}_{date_tag}.docx"

    with temp_path(".docx") as doc_path:
        if kind == "report":
            build_owner_report(doc_path, card, activities, events)
        else:
            build_meeting_doc(doc_path, card)
        await query.message.answer_document(FSInputFile(doc_path, filename=filename))

    await query.answer()
    await query.message.answer(CONTINUATION)


@router.callback_query(F.data.startswith("merge:"))
async def handle_merge(query: CallbackQuery, state: FSMContext, session_factory) -> None:
    keep_client_id = int(query.data.split(":", 1)[1])
    data = await state.get_data()
    llm = LLMResult.model_validate_json(data["llm_json"])
    async with session_factory() as session:
        agent = await repo.get_or_create_agent(session, query.from_user.id)
        outcome = await crm.merge_into_existing(
            session,
            agent_id=agent.id,
            telegram_id=query.from_user.id,
            keep_client_id=keep_client_id,
            llm=llm,
            source_text=data.get("source_text", ""),
            transcript=data.get("transcript"),
        )
    await state.clear()
    await query.answer()
    if outcome.card is not None:
        await query.message.answer("Карточки объединены.\n\n" + _render_card(outcome.card))
        await query.message.answer(
            _render_card(outcome.card), reply_markup=card_keyboard(outcome.card.deal.id)
        )
    await query.message.answer(CONTINUATION)


@router.callback_query(F.data == "separate")
async def handle_separate(query: CallbackQuery, state: FSMContext, session_factory) -> None:
    data = await state.get_data()
    llm = LLMResult.model_validate_json(data["llm_json"])
    async with session_factory() as session:
        agent = await repo.get_or_create_agent(session, query.from_user.id)
        outcome = await crm.apply_upsert(
            session,
            agent_id=agent.id,
            telegram_id=query.from_user.id,
            llm=llm,
            source_text=data.get("source_text", ""),
            transcript=data.get("transcript"),
            allow_duplicate=True,
        )
    await state.clear()
    await query.answer()
    if outcome.card is not None:
        await query.message.answer("Создана отдельная карточка.\n\n" + _render_card(outcome.card))
        await query.message.answer(
            _render_card(outcome.card), reply_markup=card_keyboard(outcome.card.deal.id)
        )
    await query.message.answer(CONTINUATION)


def _today_tag() -> str:
    from datetime import date

    return date.today().strftime("%Y-%m-%d")
