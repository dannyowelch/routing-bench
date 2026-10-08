from dataclasses import dataclass

from shop.discount import AmountOff, PercentOff
from shop.line import Line
from shop.tax import tax_cents


@dataclass(frozen=True)
class Quote:
    merchandise_cents: int
    discount_cents: int
    tax_cents: int
    total_cents: int


def quote(lines: list[Line], discounts: list, tax_rate_bps: int) -> Quote:
    merchandise = 0
    for line in lines:
        if line.unit_cents < 0 or line.qty < 0:
            raise ValueError("negative line")
        merchandise += line.unit_cents * line.qty
    remaining = merchandise
    for discount in discounts:
        if isinstance(discount, PercentOff):
            if discount.bps < 0 or discount.bps > 10_000:
                raise ValueError("percent out of range")
            remaining -= (remaining * discount.bps) // 10_000
        elif isinstance(discount, AmountOff):
            if discount.cents < 0:
                raise ValueError("amount out of range")
            remaining = max(0, remaining - discount.cents)
        else:
            raise ValueError("unknown discount")
    tax = tax_cents(remaining, tax_rate_bps)
    discount_cents = merchandise - remaining
    return Quote(merchandise, discount_cents, tax, remaining + tax)
