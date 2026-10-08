from dataclasses import dataclass


@dataclass(frozen=True)
class PercentOff:
    bps: int


@dataclass(frozen=True)
class AmountOff:
    cents: int
