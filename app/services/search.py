"""Поиск карточек по извлечённым из сообщения признакам."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.schemas import SearchCriteria
from app.database import repositories as repo
from app.utils.phone import normalize_phone


async def find_cards(
    session: AsyncSession, agent_id: int, criteria: SearchCriteria
) -> list[repo.Card]:
    """Ищет связки клиент+объект+сделка по телефону/имени/адресу/городу."""
    return await repo.search_cards(
        session,
        agent_id,
        phone=normalize_phone(criteria.phone),
        client_name=criteria.client_name,
        address=criteria.address,
        city=criteria.city,
    )
