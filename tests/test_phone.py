"""Тесты нормализации телефонов."""

from app.utils.phone import normalize_phone


def test_ru_number_with_eight():
    assert normalize_phone("8 (999) 123-45-67") == "+79991234567"


def test_ru_number_with_seven():
    assert normalize_phone("+7 999 123 45 67") == "+79991234567"


def test_ten_digits():
    assert normalize_phone("9991234567") == "+79991234567"


def test_empty():
    assert normalize_phone("") is None
    assert normalize_phone(None) is None
    assert normalize_phone("нет") is None
