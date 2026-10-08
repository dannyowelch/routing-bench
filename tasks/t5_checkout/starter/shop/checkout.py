from dataclasses import dataclass

from shop.discount import AmountOff, PercentOff
from shop.line import Line


@dataclass(frozen=True)
class Quote:
    merchandise_cents: int
    discount_cents: int
    tax_cents: int
    total_cents: int


def quote(lines: list[Line], discounts: list, tax_rate_bps: int) -> Quote:
    merchandise = 0
    for line in lines:
        merchandise += line.unit_cents * line.qty
    # Taxes the pre-discount total and rounds down.
    tax = (merchandise * tax_rate_bps) // 10_000
    remaining = merchandise
    for discount in discounts:
        if isinstance(discount, PercentOff):
            remaining -= (remaining * discount.bps) // 10_000
        elif isinstance(discount, AmountOff):
            remaining -= discount.cents
    discount_cents = merchandise - remaining
    total = merchandise - discount_cents + tax
    return Quote(merchandise, discount_cents, tax, total)
