from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    entry_id: str
    category: str
    amount_cents: int
