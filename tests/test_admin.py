"""Тесты админского удаления: удаляется только выбранный агент и его данные."""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.ai.schemas import ClientData, DealData, DealStatus, Intent, LLMResult, PropertyData
from app.database import repositories as repo
from app.database.models import Agent, Client, Property


def _payload(name: str) -> LLMResult:
    return LLMResult(
        intent=Intent.UPSERT_DATA,
        client=ClientData(name=name, phone="+79990000000"),
        property=PropertyData(city="Казань", address="ул. Южная", price=Decimal("5000000")),
        deal=DealData(deal_type="sell", status=DealStatus.NEW),
    )


@pytest.mark.asyncio
async def test_wipe_agent_data_only_target(session_factory):
    from app.services import crm

    async with session_factory() as session:
        agent_a = await repo.get_or_create_agent(session, 111)
        agent_b = await repo.get_or_create_agent(session, 222)
        await crm.apply_upsert(
            session,
            agent_id=agent_a.id,
            telegram_id=111,
            llm=_payload("Агент А клиент"),
            source_text="a",
            transcript=None,
        )
        await crm.apply_upsert(
            session,
            agent_id=agent_b.id,
            telegram_id=222,
            llm=_payload("Агент Б клиент"),
            source_text="b",
            transcript=None,
        )

    async with session_factory() as session:
        counts = await repo.wipe_agent_data(session, 111)

    assert counts is not None
    assert counts["clients"] == 1
    assert counts["properties"] == 1
    assert counts["agent"] == 1

    async with session_factory() as session:
        clients = (await session.execute(select(Client))).scalars().all()
        properties = (await session.execute(select(Property))).scalars().all()
        agents = (await session.execute(select(Agent))).scalars().all()

    # Данные и сама строка агента 111 удалены, агент 222 не тронут.
    assert len(clients) == 1
    assert clients[0].name == "Агент Б клиент"
    assert len(properties) == 1
    assert {a.telegram_id for a in agents} == {222}


@pytest.mark.asyncio
async def test_wipe_unknown_agent_returns_none(session_factory):
    async with session_factory() as session:
        result = await repo.wipe_agent_data(session, 999)
    assert result is None
