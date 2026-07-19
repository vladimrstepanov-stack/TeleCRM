"""Тесты строгой валидации ответа LLM."""

import pytest
from pydantic import ValidationError

from app.ai.schemas import Intent, LLMResult


def test_minimal_fetch():
    result = LLMResult.model_validate({"intent": "fetch_data", "search": {"phone": "123"}})
    assert result.intent == Intent.FETCH_DATA
    assert result.search.phone == "123"


def test_unknown_field_rejected():
    # Защита от prompt-injection: лишние поля недопустимы.
    with pytest.raises(ValidationError):
        LLMResult.model_validate({"intent": "upsert_data", "hacked": True})


def test_invalid_enum_rejected():
    with pytest.raises(ValidationError):
        LLMResult.model_validate(
            {"intent": "upsert_data", "deal": {"status": "не существует"}}
        )


def test_activity_requires_summary():
    with pytest.raises(ValidationError):
        LLMResult.model_validate(
            {"intent": "upsert_data", "activities": [{"activity_type": "call"}]}
        )


def test_demand_parsed():
    result = LLMResult.model_validate(
        {
            "intent": "upsert_data",
            "demand": {
                "rooms_desired": [2, 3],
                "min_area": 50,
                "budget_max": 6000000,
                "cities": ["Казань"],
            },
        }
    )
    assert result.demand.rooms_desired == [2, 3]
    assert result.demand.cities == ["Казань"]


def test_demand_rejects_unknown_field():
    with pytest.raises(ValidationError):
        LLMResult.model_validate(
            {"intent": "upsert_data", "demand": {"unknown": 1}}
        )
