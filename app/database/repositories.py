"""Параметризованный доступ к данным.

Все запросы ограничены agent_id владельца, поэтому чужие данные недоступны.
SQL не собирается склейкой строк — используются выражения SQLAlchemy с
привязкой параметров, что защищает от SQL-инъекций.
"""

from dataclasses import dataclass

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Activity,
    Agent,
    AuditEvent,
    Client,
    ClientProperty,
    Deal,
    Demand,
    Property,
)


@dataclass
class Card:
    """Связка клиент+объект+сделка — единица отображения и поиска."""

    client: Client
    property: Property
    deal: Deal


async def get_or_create_agent(session: AsyncSession, telegram_id: int) -> Agent:
    result = await session.execute(select(Agent).where(Agent.telegram_id == telegram_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        agent = Agent(telegram_id=telegram_id)
        session.add(agent)
        await session.flush()
    return agent


def agent_needs_onboarding(agent: Agent) -> bool:
    """Агент считается непредставившимся, пока нет ФИО и телефона."""
    return not (agent.name and agent.phone)


async def list_agents(session: AsyncSession) -> list[Agent]:
    result = await session.execute(select(Agent).order_by(Agent.id))
    return list(result.scalars().all())


async def wipe_agent_data(session: AsyncSession, telegram_id: int) -> dict[str, int] | None:
    """Полностью удаляет агента вместе со всеми его данными (для тестирования).

    Возвращает счётчики удалённого по таблицам или None, если агент не найден.
    Удаление идёт в порядке зависимостей внешних ключей и ограничено этим агентом;
    в конце удаляется и сама строка агента, поэтому при следующем сообщении он
    снова пройдёт онбординг.
    """
    result = await session.execute(select(Agent).where(Agent.telegram_id == telegram_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        return None

    agent_id = agent.id
    client_ids = list(
        (
            await session.execute(select(Client.id).where(Client.agent_id == agent_id))
        ).scalars().all()
    )
    property_ids = list(
        (
            await session.execute(select(Property.id).where(Property.agent_id == agent_id))
        ).scalars().all()
    )

    counts: dict[str, int] = {}

    res = await session.execute(delete(Activity).where(Activity.agent_id == agent_id))
    counts["activities"] = res.rowcount or 0

    if client_ids or property_ids:
        conditions = []
        if client_ids:
            conditions.append(AuditEvent.client_id.in_(client_ids))
        if property_ids:
            conditions.append(AuditEvent.property_id.in_(property_ids))
        res = await session.execute(delete(AuditEvent).where(or_(*conditions)))
        counts["audit_events"] = res.rowcount or 0
    else:
        counts["audit_events"] = 0

    if client_ids:
        res = await session.execute(delete(Deal).where(Deal.client_id.in_(client_ids)))
        counts["deals"] = res.rowcount or 0
        res = await session.execute(
            delete(ClientProperty).where(ClientProperty.client_id.in_(client_ids))
        )
        counts["client_properties"] = res.rowcount or 0
        res = await session.execute(delete(Demand).where(Demand.client_id.in_(client_ids)))
        counts["demands"] = res.rowcount or 0
    else:
        counts["deals"] = 0
        counts["client_properties"] = 0
        counts["demands"] = 0

    res = await session.execute(delete(Property).where(Property.agent_id == agent_id))
    counts["properties"] = res.rowcount or 0

    res = await session.execute(delete(Client).where(Client.agent_id == agent_id))
    counts["clients"] = res.rowcount or 0

    res = await session.execute(delete(Agent).where(Agent.id == agent_id))
    counts["agent"] = res.rowcount or 0

    await session.commit()
    return counts


async def find_clients_by_phone(
    session: AsyncSession, agent_id: int, phone: str
) -> list[Client]:
    result = await session.execute(
        select(Client).where(Client.agent_id == agent_id, Client.phone == phone)
    )
    return list(result.scalars().all())


async def search_cards(
    session: AsyncSession,
    agent_id: int,
    *,
    phone: str | None = None,
    client_name: str | None = None,
    address: str | None = None,
    city: str | None = None,
) -> list[Card]:
    """Ищет карточки по любому из идентифицирующих признаков."""
    stmt = (
        select(Client, Property, Deal)
        .join(Deal, Deal.client_id == Client.id)
        .join(Property, Property.id == Deal.property_id)
        .where(Client.agent_id == agent_id)
    )

    conditions = []
    if phone:
        conditions.append(Client.phone == phone)
    if client_name:
        conditions.append(Client.name.ilike(f"%{client_name}%"))
    if address:
        conditions.append(Property.address.ilike(f"%{address}%"))
    if city:
        conditions.append(Property.city.ilike(f"%{city}%"))

    if conditions:
        stmt = stmt.where(or_(*conditions))

    stmt = stmt.order_by(Deal.updated_at.desc()).limit(10)
    result = await session.execute(stmt)
    return [Card(client=row[0], property=row[1], deal=row[2]) for row in result.all()]


async def get_card_by_deal(session: AsyncSession, agent_id: int, deal_id: int) -> Card | None:
    stmt = (
        select(Client, Property, Deal)
        .join(Deal, Deal.client_id == Client.id)
        .join(Property, Property.id == Deal.property_id)
        .where(Client.agent_id == agent_id, Deal.id == deal_id)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None
    return Card(client=row[0], property=row[1], deal=row[2])


async def link_client_property(
    session: AsyncSession, client_id: int, property_id: int, relation_type: str
) -> None:
    exists = await session.get(ClientProperty, (client_id, property_id, relation_type))
    if exists is None:
        session.add(
            ClientProperty(
                client_id=client_id, property_id=property_id, relation_type=relation_type
            )
        )


async def add_activity(session: AsyncSession, activity: Activity) -> Activity:
    session.add(activity)
    await session.flush()
    return activity


async def add_audit_event(session: AsyncSession, event: AuditEvent) -> AuditEvent:
    session.add(event)
    await session.flush()
    return event


async def get_property_history(
    session: AsyncSession, agent_id: int, property_id: int
) -> tuple[list[Activity], list[AuditEvent]]:
    """История для отчёта: активности и аудит по объекту, от новых к старым."""
    activities = (
        await session.execute(
            select(Activity)
            .where(Activity.agent_id == agent_id, Activity.property_id == property_id)
            .order_by(Activity.created_at.desc())
        )
    ).scalars().all()

    events = (
        await session.execute(
            select(AuditEvent)
            .where(AuditEvent.property_id == property_id)
            .order_by(AuditEvent.created_at.desc())
        )
    ).scalars().all()

    return list(activities), list(events)


async def merge_clients(session: AsyncSession, keep_id: int, drop_id: int) -> None:
    """Переносит все связи дубля на основную карточку и удаляет дубль."""
    await session.execute(
        update(Deal).where(Deal.client_id == drop_id).values(client_id=keep_id)
    )
    await session.execute(
        update(Activity).where(Activity.client_id == drop_id).values(client_id=keep_id)
    )
    await session.execute(
        update(AuditEvent).where(AuditEvent.client_id == drop_id).values(client_id=keep_id)
    )
    await session.execute(
        update(ClientProperty)
        .where(ClientProperty.client_id == drop_id)
        .values(client_id=keep_id)
    )
    from app.database.models import Demand

    await session.execute(
        update(Demand).where(Demand.client_id == drop_id).values(client_id=keep_id)
    )
    drop = await session.get(Client, drop_id)
    if drop is not None:
        await session.delete(drop)
