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

    def total_cents(self) -> int:
        return sum(entry.amount_cents for entry in self._entries.values())

    def balance_by_category(self) -> dict:
        raise NotImplementedError

    def apply_refund(self, entry_id: str, amount_cents: int):
        raise NotImplementedError
