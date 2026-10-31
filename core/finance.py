"""Exact monetary primitives. Locale interpretation is explicit, never guessed."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re


def decimal_amount(value: str | Decimal) -> Decimal:
    if not isinstance(value, (str, Decimal)):
        raise TypeError("Amounts must originate from strings or Decimal")
    if isinstance(value, str):
        raw = value.strip()
        negative = raw.startswith("(") and raw.endswith(")")
        if negative:
            raw = raw[1:-1].strip()
        raw = re.sub(r"^(?:INR|USD|EUR|GBP|₹|\$|€|£)\s*", "", raw)
        if not re.fullmatch(r"-?(?:\d+|\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})*,\d{3})(?:\.\d+)?", raw):
            raise ValueError("Unsupported or ambiguous amount format")
        if negative and raw.startswith("-"):
            raise ValueError("Conflicting signs")
        value = Decimal(raw.replace(",", "")) * (-1 if negative else 1)
    if not value.is_finite() or len(value.as_tuple().digits) > 24 or abs(value.as_tuple().exponent) > 12:
        raise ValueError("Amount must be finite and within supported precision")
    return value


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self):
        object.__setattr__(self, "amount", decimal_amount(self.amount))
        if not re.fullmatch(r"[A-Z]{3}", self.currency):
            raise ValueError("Currency must be an uppercase three-letter code")

    def __add__(self, other):
        if not isinstance(other, Money) or self.currency != other.currency:
            raise ValueError("Cannot combine different currencies")
        return Money(self.amount + other.amount, self.currency)

    def rounded(self, exponent: int = 2):
        return Money(self.amount.quantize(Decimal(1).scaleb(-exponent), rounding=ROUND_HALF_UP), self.currency)


def reconcile(subtotal: Money, tax: Money, total: Money) -> bool:
    return subtotal + tax == total
