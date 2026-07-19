"""Тесты CRM: upsert+audit, антидубль, merge, режим обновления."""

from decimal import Decimal

import pytest

from app.ai.schemas import (
    ClientData,
    DealData,
    DealStatus,
    LLMResult,
    Intent,
    PropertyData,
)
from app.database import repositories as repo
from app.database.models import AuditEvent
from sqlalchemy import select


def _upsert_payload(name="Иван Петров", phone="+79990000000", price=5_000_000):
    return LLMResult(
        intent=Intent.UPSERT_DATA,
        client=ClientData(name=name, phone=phone),
        property=PropertyData(city="Казань", address="ул. Южная", price=Decimal(price)),
        deal=DealData(deal_type="sell", status=DealStatus.NEW),
    )


@pytest.mark.asyncio
async def test_upsert_creates_card_and_audit(session_factory):
    from app.services import crm

    async with session_factory() as session:
        agent = await repo.get_or_create_agent(session, 111)
        outcome = await crm.apply_upsert(
            session,
            agent_id=agent.id,
            telegram_id=111,
            llm=_upsert_payload(),
            source_text="исходный текст",
            transcript=None,
        )

    assert outcome.created is True
    assert outcome.card.client.name == "Иван Петров"
    assert outcome.card.property.price == Decimal("5000000")

    async with session_factory() as session:
        events = (await session.execute(select(AuditEvent))).scalars().all()
    assert len(events) == 1
    assert events[0].event_type == "create"
    assert events[0].source_text == "исходный текст"


@pytest.mark.asyncio
async def test_duplicate_phone_different_name_returns_candidates(session_factory):
    from app.services import crm

    async with session_factory() as session:
        agent = await repo.get_or_create_agent(session, 111)
        await crm.apply_upsert(
            session,
            agent_id=agent.id,
            telegram_id=111,
            llm=_upsert_payload(name="Иван Петров"),
            source_text="t1",
            transcript=None,
        )
        outcome = await crm.apply_upsert(
            session,
            agent_id=agent.id,
            telegram_id=111,
            llm=_upsert_payload(name="Пётр Сидоров"),
            source_text="t2",
            transcript=None,
        )

    assert outcome.card is None
    assert len(outcome.duplicate_candidates) == 1
    assert outcome.duplicate_candidates[0].name == "Иван Петров"


@pytest.mark.asyncio
async def test_merge_keeps_single_client(session_factory):
    from app.services import crm

    async with session_factory() as session:
        agent = await repo.get_or_create_agent(session, 111)
        first = await crm.apply_upsert(
            session,
            agent_id=agent.id,
            telegram_id=111,
            llm=_upsert_payload(name="Иван Петров"),
            source_text="t1",
            transcript=None,
        )
        keep_id = first.card.client.id
        merged = await crm.merge_into_existing(
            session,
            agent_id=agent.id,
            telegram_id=111,
            keep_client_id=keep_id,
            llm=_upsert_payload(name="Пётр Сидоров"),
            source_text="t2",
            transcript=None,
        )

    assert merged.card.client.id == keep_id
    async with session_factory() as session:
        from app.database.models import Client

        clients = (await session.execute(select(Client))).scalars().all()
    assert len(clients) == 1


@pytest.mark.asyncio
async def test_update_existing_records_diff(session_factory):
    from app.services import crm

    async with session_factory() as session:
        agent = await repo.get_or_create_agent(session, 111)
        created = await crm.apply_upsert(
            session,
            agent_id=agent.id,
            telegram_id=111,
            llm=_upsert_payload(price=5_000_000),
            source_text="t1",
            transcript=None,
        )
        card = await repo.get_card_by_deal(session, agent.id, created.card.deal.id)
        update_llm = LLMResult(
            intent=Intent.UPSERT_DATA,
            property=PropertyData(price=Decimal("4500000")),
        )
        updated = await crm.apply_upsert(
            session,
            agent_id=agent.id,
            telegram_id=111,
            llm=update_llm,
            source_text="снизили цену",
            transcript=None,
            target_card=card,
        )

    assert updated.created is False
    assert updated.card.property.price == Decimal("4500000")


@pytest.mark.asyncio
async def test_needs_clarification_without_identifier(session_factory):
    from app.services import crm

    async with session_factory() as session:
        agent = await repo.get_or_create_agent(session, 111)
        outcome = await crm.apply_upsert(
            session,
            agent_id=agent.id,
            telegram_id=111,
            llm=LLMResult(intent=Intent.UPSERT_DATA),
            source_text="просто текст",
            transcript=None,
        )
    assert outcome.needs_clarification is not None
