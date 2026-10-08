"""Compute a client-side cost from the pinned price table."""

from __future__ import annotations


def pattern_matches(pattern: str, model: str) -> bool:
    """Match a price-table pattern against a model id.

    Bare family names (``haiku``) match only the whole string. Patterns that
    contain a digit or a hyphen match as substrings, so ``haiku-5-5`` matches
    ``claude-haiku-5-5`` without also matching ``claude-haiku-4-5``.
    """
    pattern = pattern.lower()
    model = model.lower()
    if pattern == model:
        return True
    specific = any(character.isdigit() for character in pattern) or "-" in pattern
    return specific and pattern in model


def find_price(model: str | None, table: dict) -> dict | None:
    if not model:
        return None
    for rule in table.get("models") or []:
        for pattern in rule.get("match") or []:
            if pattern_matches(str(pattern), model):
                return rule
    return None


def compute_cost_usd(
    model: str | None,
    *,
    input_uncached: int,
    cache_read: int,
    cache_write_5m: int,
    cache_write_1h: int,
    output: int,
    table: dict,
) -> float | None:
    rule = find_price(model, table)
    if rule is None:
        return None
    million = 1_000_000
    total = (
        input_uncached * float(rule["input"])
        + cache_read * float(rule["cache_read"])
        + cache_write_5m * float(rule["cache_write_5m"])
        + cache_write_1h * float(rule["cache_write_1h"])
        + output * float(rule["output"])
    )
    return total / million
