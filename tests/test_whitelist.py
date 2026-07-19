"""Тест whitelist: посторонний не доходит до обработчика (нет AI-вызовов)."""

import pytest

from app.bot.middlewares.whitelist import WhitelistMiddleware


class _User:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class _Event:
    """Минимальная заглушка Message с методом answer."""

    def __init__(self) -> None:
        self.answers: list[str] = []

    async def answer(self, text: str, **kwargs) -> None:
        self.answers.append(text)


# Патчим isinstance-проверку: считаем заглушку Message.
import app.bot.middlewares.whitelist as wl


@pytest.mark.asyncio
async def test_blocks_unknown_user(monkeypatch):
    middleware = WhitelistMiddleware(allowed_ids={111})
    monkeypatch.setattr(wl, "Message", _Event)

    called = False

    async def handler(event, data):
        nonlocal called
        called = True

    event = _Event()
    await middleware(handler, event, {"event_from_user": _User(999)})

    assert called is False
    assert event.answers == ["Доступ ограничен."]


@pytest.mark.asyncio
async def test_allows_known_user(monkeypatch):
    middleware = WhitelistMiddleware(allowed_ids={111})
    monkeypatch.setattr(wl, "Message", _Event)

    called = False

    async def handler(event, data):
        nonlocal called
        called = True

    event = _Event()
    await middleware(handler, event, {"event_from_user": _User(111)})

    assert called is True
