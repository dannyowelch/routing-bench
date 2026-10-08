import duration


def test_hours_minutes_seconds():
    assert duration.parse_duration("1h30m15s") == 5_415_000


def test_milliseconds():
    assert duration.parse_duration("500ms") == 500
