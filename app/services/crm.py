"""CRM-логика: создание/обновление связки клиент+объект+сделка и аудит.

Каждая операция выполняется в одной транзакции сессии. История изменений
пишется в audit_events, включая diff «старое → новое» и исходный текст/транскрипт.
"""

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.schemas import LLMResult
from app.database import repositories as repo
from app.database.models import Activity, AuditEvent, Client, Deal, Demand, Property
from app.utils.phone import normalize_phone

logger = logging.getLogger(__name__)


@dataclass
class UpsertOutcome:
    """Результат попытки записи."""

    card: repo.Card | None = None
    created: bool = False
    needs_clarification: str | None = None
    duplicate_candidates: list[Client] = field(default_factory=list)


def _diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Возвращает изменённые поля в формате {поле: [старое, новое]}."""
    changes: dict[str, Any] = {}
    for key, new_value in after.items():
        old_value = before.get(key)
        if old_value != new_value:
            changes[key] = [_json_safe(old_value), _json_safe(new_value)]
    return changes


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    return value


def _apply_property_fields(prop: Property, data) -> dict[str, Any]:
    """Обновляет поля объекта только там, где модель прислала значение."""
    after: dict[str, Any] = {}
    for attr in (
        "city",
        "district",
        "address",
        "house_number",
        "apartment_number",
        "property_type",
        "rooms_count",
        "floor",
        "total_floors",
        "total_area",
        "price",
    ):
        value = getattr(data, attr, None)
        if value is not None:
            setattr(prop, attr, value)
            after[attr] = value
    if data.status is not None:
        prop.status = data.status.value
        after["status"] = prop.status
    return after


async def _resolve_client(
    session: AsyncSession, agent_id: int, data, *, allow_duplicate: bool
) -> tuple[Client | None, list[Client]]:
    """Находит существующего клиента по телефону или создаёт нового.

    При совпадении телефона с другим именем возвращает кандидатов на объединение
    вместо тихого создания дубля.
    """
    phone = normalize_phone(data.phone) if data else None
    name = (data.name if data else None) or None

    if phone:
        existing = await repo.find_clients_by_phone(session, agent_id, phone)
        if existing and not allow_duplicate:
            same_name = [c for c in existing if name is None or c.name.lower() == name.lower()]
            if same_name:
                return same_name[0], []
            # Телефон тот же, имя другое — требуется решение пользователя.
            return None, existing

    client = Client(agent_id=agent_id, name=name or "Без имени", phone=phone)
    session.add(client)
    await session.flush()
    return client, []


async def apply_upsert(
    session: AsyncSession,
    *,
    agent_id: int,
    telegram_id: int,
    llm: LLMResult,
    source_text: str,
    transcript: str | None,
    target_card: repo.Card | None = None,
    allow_duplicate: bool = False,
) -> UpsertOutcome:
    """Основной сценарий записи данных из сообщения."""

    # Режим обновления существующей карточки (кнопка «Обновить»).
    if target_card is not None:
        return await _update_existing(
            session,
            agent_id=agent_id,
            telegram_id=telegram_id,
            llm=llm,
            source_text=source_text,
            transcript=transcript,
            card=target_card,
        )

    has_identifier = bool((llm.client and (llm.client.name or llm.client.phone)))
    has_property = bool(llm.property and (llm.property.address or llm.property.city))
    if not has_identifier and not has_property:
        return UpsertOutcome(
            needs_clarification=(
                "Не хватает данных для записи. Укажите имя или телефон клиента "
                "либо адрес объекта."
            )
        )

    client, candidates = await _resolve_client(
        session, agent_id, llm.client, allow_duplicate=allow_duplicate
    )
    if client is None:
        return UpsertOutcome(duplicate_candidates=candidates)

    card = await _create_card_for_client(
        session,
        agent_id=agent_id,
        telegram_id=telegram_id,
        client=client,
        llm=llm,
        source_text=source_text,
        transcript=transcript,
    )
    await session.commit()
    return UpsertOutcome(card=card, created=True)


async def _create_card_for_client(
    session: AsyncSession,
    *,
    agent_id: int,
    telegram_id: int,
    client: Client,
    llm: LLMResult,
    source_text: str,
    transcript: str | None,
) -> repo.Card:
    """Создаёт объект, сделку, связь, активности и audit для заданного клиента."""
    prop = Property(
        agent_id=agent_id,
        city="не указан",
        address="не указан",
        house_number="-",
        property_type="не указан",
        price=Decimal("0"),
    )
    if llm.property is not None:
        _apply_property_fields(prop, llm.property)
    session.add(prop)
    await session.flush()

    relation = "owner"
    deal_type = "sell"
    if llm.deal and llm.deal.deal_type is not None:
        deal_type = llm.deal.deal_type.value
        relation = "buyer" if deal_type == "buy" else "owner"

    deal = Deal(
        client_id=client.id,
        property_id=prop.id,
        deal_type=deal_type,
        status=(llm.deal.status.value if llm.deal and llm.deal.status else "new"),
        offer_price=(llm.deal.offer_price if llm.deal else None),
        notes=(llm.deal.notes if llm.deal else None),
    )
    session.add(deal)
    await session.flush()

    await repo.link_client_property(session, client.id, prop.id, relation)
    await _write_demand(session, client.id, llm)
    await _write_activities(session, agent_id, client.id, prop.id, llm)

    await repo.add_audit_event(
        session,
        AuditEvent(
            client_id=client.id,
            property_id=prop.id,
            event_type="create",
            initiator_type="user",
            initiator_telegram_id=telegram_id,
            entity_type="deal",
            entity_id=deal.id,
            changes_json={"created": True},
            source_text=source_text,
            transcript=transcript,
        ),
    )
    return repo.Card(client=client, property=prop, deal=deal)


async def _update_existing(
    session: AsyncSession,
    *,
    agent_id: int,
    telegram_id: int,
    llm: LLMResult,
    source_text: str,
    transcript: str | None,
    card: repo.Card,
) -> UpsertOutcome:
    prop = await session.get(Property, card.property.id)
    deal = await session.get(Deal, card.deal.id)
    client = await session.get(Client, card.client.id)

    before_prop = {"price": prop.price, "status": prop.status}
    if llm.property is not None:
        _apply_property_fields(prop, llm.property)

    before_deal = {"status": deal.status, "offer_price": deal.offer_price}
    if llm.deal is not None:
        if llm.deal.status is not None:
            deal.status = llm.deal.status.value
        if llm.deal.offer_price is not None:
            deal.offer_price = llm.deal.offer_price
        if llm.deal.notes is not None:
            deal.notes = llm.deal.notes

    if llm.client is not None:
        if llm.client.name:
            client.name = llm.client.name
        new_phone = normalize_phone(llm.client.phone)
        if new_phone:
            client.phone = new_phone

    await _write_activities(session, agent_id, client.id, prop.id, llm)

    changes = {
        **_diff(before_prop, {"price": prop.price, "status": prop.status}),
        **_diff(before_deal, {"status": deal.status, "offer_price": deal.offer_price}),
    }
    await repo.add_audit_event(
        session,
        AuditEvent(
            client_id=client.id,
            property_id=prop.id,
            event_type="update",
            initiator_type="user",
            initiator_telegram_id=telegram_id,
            entity_type="deal",
            entity_id=deal.id,
            changes_json=changes or {"note": "activity_added"},
            source_text=source_text,
            transcript=transcript,
        ),
    )

    await session.commit()
    return UpsertOutcome(
        card=repo.Card(client=client, property=prop, deal=deal), created=False
    )


async def _write_demand(session: AsyncSession, client_id: int, llm: LLMResult) -> None:
    """Пишет потребности покупателя, если модель их извлекла."""
    if llm.demand is None:
        return
    demand = llm.demand
    session.add(
        Demand(
            client_id=client_id,
            # cities в модели NOT NULL — при отсутствии городов пишем пустой список.
            cities=demand.cities or [],
            rooms_desired=demand.rooms_desired,
            min_area=demand.min_area,
            max_area=demand.max_area,
            budget_min=demand.budget_min,
            budget_max=demand.budget_max,
        )
    )
    await session.flush()


async def _write_activities(
    session: AsyncSession, agent_id: int, client_id: int, property_id: int, llm: LLMResult
) -> None:
    for item in llm.activities:
        await repo.add_activity(
            session,
            Activity(
                agent_id=agent_id,
                client_id=client_id,
                property_id=property_id,
                activity_type=item.activity_type.value,
                summarized_action=item.summarized_action,
                buyer_feedback=item.buyer_feedback,
                seller_feedback=item.seller_feedback,
                proposed_price=item.proposed_price,
                next_action_agreed=item.next_action_agreed,
            ),
        )


async def merge_into_existing(
    session: AsyncSession,
    *,
    agent_id: int,
    telegram_id: int,
    keep_client_id: int,
    llm: LLMResult,
    source_text: str,
    transcript: str | None,
) -> UpsertOutcome:
    """Пользователь выбрал «Объединить»: пишем данные в существующего клиента."""
    keep = await session.get(Client, keep_client_id)
    if keep is None or keep.agent_id != agent_id:
        return UpsertOutcome(needs_clarification="Карточка для объединения не найдена.")

    # Обновляем контактные данные существующего клиента при необходимости.
    if llm.client is not None and llm.client.name:
        keep.name = llm.client.name

    await repo.add_audit_event(
        session,
        AuditEvent(
            client_id=keep.id,
            event_type="merge",
            initiator_type="user",
            initiator_telegram_id=telegram_id,
            entity_type="client",
            entity_id=keep.id,
            changes_json={"merged_into": keep.id},
            source_text=source_text,
            transcript=transcript,
        ),
    )
    # Данные из сообщения дописываем к сохранённому клиенту как новую связку.
    card = await _create_card_for_client(
        session,
        agent_id=agent_id,
        telegram_id=telegram_id,
        client=keep,
        llm=llm,
        source_text=source_text,
        transcript=transcript,
    )
    await session.commit()
    return UpsertOutcome(card=card, created=True)
