def mean_inclusive(values, start, end):
    """Mean of values[start] through values[end], inclusive."""
    if start > end:
        raise ValueError("start must be <= end")
    if start < 0 or end >= len(values):
        raise IndexError("index out of range")
    window = values[start : end + 1]
    if not window:
        raise ValueError("empty window")
    return sum(window) / len(window)
