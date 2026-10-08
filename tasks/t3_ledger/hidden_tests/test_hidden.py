import pytest

from ledger.book import Book
from ledger.entries import Entry


def _book():
    book = Book()
    book.add(Entry("rent", "home", 1000))
    book.add(Entry("lunch", "food", 400))
    book.add(Entry("dinner", "food", 600))
    return book


def test_refund_updates_balance_and_keeps_the_id():
    book = _book()
    book.apply_refund("lunch", 150)
    assert book.total_cents() == 1850
    assert book.balance_by_category() == {"home": 1000, "food": 850}
    assert book.index.ids("food") == ["lunch", "dinner"]


def test_refund_to_zero_keeps_the_category():
    book = _book()
    book.apply_refund("rent", 1000)
    assert book.balance_by_category()["home"] == 0
    assert book.index.ids("home") == ["rent"]
    assert book.total_cents() == 1000


def test_duplicate_and_negative_entry():
    book = _book()
    with pytest.raises(ValueError):
        book.add(Entry("rent", "home", 1))
    with pytest.raises(ValueError):
        book.add(Entry("x", "food", -1))


def test_bad_refunds():
    book = _book()
    with pytest.raises(KeyError):
        book.apply_refund("missing", 1)
    with pytest.raises(ValueError):
        book.apply_refund("lunch", 0)
    with pytest.raises(ValueError):
        book.apply_refund("lunch", -5)
    with pytest.raises(ValueError):
        book.apply_refund("lunch", 401)
