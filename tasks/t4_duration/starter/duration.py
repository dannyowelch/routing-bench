def parse_duration(text: str) -> int:
    """Parse a duration string into milliseconds."""
    total = 0
    if "h" in text:
        hours, text = text.split("h", 1)
        total += int(hours) * 3_600_000
    if "m" in text:
        minutes, text = text.split("m", 1)
        total += int(minutes) * 60_000
    if text.endswith("s"):
        seconds = text[:-1]
        total += int(seconds or "0") * 1_000
    return total
