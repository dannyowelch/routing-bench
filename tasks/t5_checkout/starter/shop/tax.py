def tax_cents(amount_cents: int, tax_rate_bps: int) -> int:
    """Half-up tax. The starter checkout does not call this."""
    if tax_rate_bps < 0 or tax_rate_bps > 10_000:
        raise ValueError("tax rate out of range")
    return (amount_cents * tax_rate_bps + 5_000) // 10_000
