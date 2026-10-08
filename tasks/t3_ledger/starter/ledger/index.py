class CategoryIndex:
    """Entry ids grouped by category, in insertion order."""

    def __init__(self):
        self._ids = {}

    def add(self, entry):
        self._ids.setdefault(entry.category, []).append(entry.entry_id)

    def ids(self, category):
        return list(self._ids.get(category, []))
