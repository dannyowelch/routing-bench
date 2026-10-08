from ledger.entries import Entry
from ledger.index import CategoryIndex


class Book:
    def __init__(self):
        self._entries = {}
        self.index = CategoryIndex()

    def add(self, entry: Entry):
        if entry.entry_id in self._entries:
            raise ValueError("duplicate id")
        if entry.amount_cents < 0:
            raise ValueError("negative amount")
        self._entries[entry.entry_id] = entry
        self.index.add(entry)

    def total_cents(self) -> int:
        return sum(entry.amount_cents for entry in self._entries.values())

    def balance_by_category(self) -> dict:
        totals = {}
        for entry in self._entries.values():
            totals[entry.category] = totals.get(entry.category, 0) + entry.amount_cents
        return totals

    def apply_refund(self, entry_id: str, amount_cents: int):
        if amount_cents <= 0:
            raise ValueError("refund must be positive")
        entry = self._entries[entry_id]
        if amount_cents > entry.amount_cents:
            raise ValueError("refund exceeds remaining amount")
        self._entries[entry_id] = Entry(
            entry.entry_id,
            entry.category,
            entry.amount_cents - amount_cents,
        )
