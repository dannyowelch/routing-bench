from ledger.book import Book
from ledger.entries import Entry


def test_add_is_indexed_and_balanced():
    book = Book()
    book.add(Entry("a", "food", 500))
    book.add(Entry("b", "food", 250))
    assert book.index.ids("food") == ["a", "b"]
    assert book.balance_by_category() == {"food": 750}
    assert book.total_cents() == 750
