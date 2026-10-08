import re

_TOKEN = re.compile(r"(\d+)(ms|h|m|s)")
_ORDER = ("h", "m", "s", "ms")
_SCALE = {"h": 3_600_000, "m": 60_000, "s": 1_000, "ms": 1}


def parse_duration(text: str) -> int:
    """Parse a duration string into milliseconds."""
    if not isinstance(text, str) or text == "":
        raise ValueError("empty duration")
    position = 0
    last_index = -1
    seen = set()
    total = 0
    while position < len(text):
        match = _TOKEN.match(text, position)
        if not match:
            raise ValueError("bad duration")
        unit = match.group(2)
        index = _ORDER.index(unit)
        if unit in seen or index <= last_index:
            raise ValueError("units out of order")
        seen.add(unit)
        last_index = index
        total += int(match.group(1)) * _SCALE[unit]
        position = match.end()
    return total
