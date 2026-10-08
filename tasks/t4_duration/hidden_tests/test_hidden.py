import pytest

import duration


def test_units():
    assert duration.parse_duration("1h") == 3_600_000
    assert duration.parse_duration("45s") == 45_000
    assert duration.parse_duration("500ms") == 500
    assert duration.parse_duration("1h2m3s4ms") == 3_723_004
    assert duration.parse_duration("2m") == 120_000


def test_rejects_bad_strings():
    for text in ("", "1", "1x", "1m1h", "1h1h", "-1s", "1.5s", "1 h", "ms", "h1"):
        with pytest.raises(ValueError):
            duration.parse_duration(text)
