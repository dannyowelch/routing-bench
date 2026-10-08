from shop.checkout import quote
from shop.discount import PercentOff
from shop.line import Line


def test_percent_then_tax():
    result = quote([Line("mug", 1000, 1)], [PercentOff(5000)], 1000)
    assert result.merchandise_cents == 1000
    assert result.discount_cents == 500
    assert result.tax_cents == 50
    assert result.total_cents == 550
