import pytest

from shop.checkout import quote
from shop.discount import AmountOff, PercentOff
from shop.line import Line


def test_half_up_tax_on_small_amount():
    result = quote([Line("pin", 10, 1)], [], 500)
    assert result.tax_cents == 1
    assert result.total_cents == 11
    assert result.discount_cents == 0


def test_discount_order_is_the_list_order():
    result = quote([Line("book", 1000, 2)], [AmountOff(100), PercentOff(5000)], 1000)
    # merchandise 2000, minus 100, then 50% -> 950. tax 10% of 950 = 95.
    assert result.merchandise_cents == 2000
    assert result.discount_cents == 1050
    assert result.tax_cents == 95
    assert result.total_cents == 1045


def test_amount_off_does_not_go_negative():
    result = quote([Line("cup", 100, 1)], [PercentOff(10_000), AmountOff(50)], 800)
    assert result.discount_cents == 100
    assert result.tax_cents == 0
    assert result.total_cents == 0


def test_compound_percents():
    result = quote([Line("desk", 1000, 1)], [PercentOff(5000), PercentOff(5000)], 0)
    assert result.discount_cents == 750
    assert result.total_cents == 250


def test_empty_and_zero_qty():
    empty = quote([], [], 1000)
    assert empty.total_cents == 0
    assert empty.merchandise_cents == 0
    zero = quote([Line("none", 500, 0)], [AmountOff(10)], 1000)
    assert zero.merchandise_cents == 0
    assert zero.total_cents == 0


def test_rejects_bad_inputs():
    with pytest.raises(ValueError):
        quote([Line("x", -1, 1)], [], 0)
    with pytest.raises(ValueError):
        quote([Line("x", 10, -1)], [], 0)
    with pytest.raises(ValueError):
        quote([Line("x", 10, 1)], [PercentOff(10_001)], 0)
    with pytest.raises(ValueError):
        quote([Line("x", 10, 1)], [AmountOff(-1)], 0)
    with pytest.raises(ValueError):
        quote([Line("x", 10, 1)], [], -1)
    with pytest.raises(ValueError):
        quote([Line("x", 10, 1)], [], 10_001)
