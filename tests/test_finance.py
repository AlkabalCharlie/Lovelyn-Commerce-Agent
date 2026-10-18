import pytest

from models.finance import FinanceValidationError, format_cents, parse_amount_to_cents


def test_parses_plain_amount():
    assert parse_amount_to_cents("12.34") == 1234


def test_parses_dollar_sign_and_whole():
    assert parse_amount_to_cents("$7") == 700


def test_rejects_garbage():
    with pytest.raises(FinanceValidationError):
        parse_amount_to_cents("abc")


def test_rejects_zero():
    with pytest.raises(FinanceValidationError):
        parse_amount_to_cents("0")


def test_format_cents():
    assert format_cents(1234) == "$12.34"
    assert format_cents(5) == "$0.05"