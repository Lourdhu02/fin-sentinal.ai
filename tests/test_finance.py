from decimal import Decimal
import pytest

from core.finance import Money, decimal_amount, reconcile


@pytest.mark.parametrize("raw,expected", [("₹ 1,23,456.78", "123456.78"), ("1,234.56", "1234.56"), ("(123.45)", "-123.45")])
def test_amount_formats(raw, expected):
    assert decimal_amount(raw) == Decimal(expected)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "1,23", "(-10)", "1.234,56"])
def test_ambiguous_amounts_rejected(value):
    with pytest.raises(ValueError):
        decimal_amount(value)


def test_exact_arithmetic_and_currency_boundaries():
    a = Money(Decimal("0.1"), "INR")
    assert a + a + a == Money(Decimal("0.3"), "INR")
    assert reconcile(a, a, Money(Decimal("0.2"), "INR"))
    with pytest.raises(ValueError):
        a + Money(Decimal("1"), "USD")
    with pytest.raises(TypeError):
        decimal_amount(0.1)
