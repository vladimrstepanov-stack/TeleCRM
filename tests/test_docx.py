"""Тесты DOCX: порядок хронологии и отсутствие секретных полей."""

from datetime import datetime
from decimal import Decimal
from pathlib import Path

from docx import Document

from app.database.models import Activity, Client, Deal, Property
from app.database.repositories import Card
from app.services.docx import build_meeting_doc, build_owner_report


def _card() -> Card:
    client = Client(id=1, agent_id=1, name="Иван Петров", phone="+79990000000")
    prop = Property(
        id=1,
        agent_id=1,
        city="Казань",
        address="ул. Южная",
        house_number="10",
        property_type="flat",
        price=Decimal("5000000"),
        min_acceptable_price=Decimal("4200000"),
        status="active",
    )
    deal = Deal(id=1, client_id=1, property_id=1, deal_type="sell", status="new")
    return Card(client=client, property=prop, deal=deal)


def _read_text(path: Path) -> str:
    document = Document(path)
    return "\n".join(p.text for p in document.paragraphs)


def test_report_timeline_newest_first(tmp_path):
    card = _card()
    old = Activity(
        agent_id=1,
        client_id=1,
        property_id=1,
        activity_type="call",
        summarized_action="Первый звонок",
        created_at=datetime(2026, 1, 1, 10, 0),
    )
    new = Activity(
        agent_id=1,
        client_id=1,
        property_id=1,
        activity_type="showing",
        summarized_action="Провели показ",
        created_at=datetime(2026, 3, 1, 10, 0),
    )
    out = build_owner_report(tmp_path / "r.docx", card, [old, new], [])
    text = _read_text(out)
    assert text.index("Провели показ") < text.index("Первый звонок")


def test_report_hides_secret_price(tmp_path):
    card = _card()
    out = build_owner_report(tmp_path / "r.docx", card, [], [])
    text = _read_text(out)
    assert "4200000" not in text.replace(" ", "")


def test_meeting_hides_secret_price(tmp_path):
    card = _card()
    out = build_meeting_doc(tmp_path / "m.docx", card)
    text = _read_text(out)
    assert "4200000" not in text.replace(" ", "")
    assert "Иван Петров" in text
