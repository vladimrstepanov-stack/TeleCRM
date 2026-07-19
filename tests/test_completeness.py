"""Тесты матрицы обязательных полей и разбора точечных ответов."""

from decimal import Decimal

from app.ai.schemas import (
    ClientData,
    DealData,
    DemandData,
    Intent,
    LLMResult,
    PropertyData,
)
from app.services.completeness import apply_field, missing_required


def _seller_complete() -> LLMResult:
    return LLMResult(
        intent=Intent.UPSERT_DATA,
        client=ClientData(name="Иван Петров", phone="+79990000000"),
        property=PropertyData(
            city="Казань",
            address="ул. Южная, 5",
            rooms_count=2,
            total_area=Decimal("45"),
            price=Decimal("5000000"),
        ),
    )


def test_seller_complete_has_no_missing():
    assert missing_required(_seller_complete()) == []


def test_seller_missing_object_fields():
    draft = LLMResult(
        intent=Intent.UPSERT_DATA,
        client=ClientData(name="Иван", phone="+79990000000"),
        property=PropertyData(city="Казань"),
    )
    missing = missing_required(draft)
    assert "property.address" in missing
    assert "property.rooms_count" in missing
    assert "property.total_area" in missing
    assert "property.price" in missing


def test_client_without_contact_is_missing():
    draft = LLMResult(intent=Intent.UPSERT_DATA, property=PropertyData(city="Казань"))
    missing = missing_required(draft)
    assert "client.name" in missing
    assert "client.phone" in missing


def test_buyer_requires_demand():
    draft = LLMResult(
        intent=Intent.UPSERT_DATA,
        client=ClientData(name="Иван", phone="+79990000000"),
        deal=DealData(deal_type="buy"),
        demand=DemandData(),
    )
    missing = missing_required(draft)
    assert "demand.rooms_desired" in missing
    assert "demand.area" in missing
    assert "demand.budget" in missing
    # Покупатель без объекта — поля продавца не требуются.
    assert not any(key.startswith("property.") for key in missing)


def test_both_roles_require_property_and_demand():
    draft = LLMResult(
        intent=Intent.UPSERT_DATA,
        client=ClientData(name="Иван", phone="+79990000000"),
        property=PropertyData(city="Казань"),
        demand=DemandData(),
    )
    missing = missing_required(draft)
    assert any(key.startswith("property.") for key in missing)
    assert any(key.startswith("demand.") for key in missing)


def test_apply_field_phone_normalizes():
    draft = LLMResult(intent=Intent.UPSERT_DATA)
    assert apply_field(draft, "client.phone", "8 900 123-45-67") is None
    assert draft.client.phone == "+79001234567"


def test_apply_field_price_with_millions():
    draft = LLMResult(intent=Intent.UPSERT_DATA)
    assert apply_field(draft, "property.price", "5 млн") is None
    assert draft.property.price == Decimal("5000000")


def test_apply_field_rejects_bad_phone():
    draft = LLMResult(intent=Intent.UPSERT_DATA)
    error = apply_field(draft, "client.phone", "не телефон")
    assert error is not None


def test_apply_field_demand_budget_range():
    draft = LLMResult(intent=Intent.UPSERT_DATA)
    assert apply_field(draft, "demand.budget", "4-6 млн") is None
    assert draft.demand.budget_min == Decimal("4000000")
    assert draft.demand.budget_max == Decimal("6000000")
