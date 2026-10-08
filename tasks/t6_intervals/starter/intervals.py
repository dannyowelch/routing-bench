def merge(intervals):
    """Merge inclusive integer intervals. The starter misses touching endpoints."""
    if not intervals:
        return []
    cleaned = []
    for start, end in intervals:
        if start > end:
            raise ValueError("start must be <= end")
        if start == end:
            continue
        cleaned.append((start, end))
    cleaned.sort()
    if not cleaned:
        return []
    merged = [cleaned[0]]
    for start, end in cleaned[1:]:
        current_start, current_end = merged[-1]
        if start < current_end:
            merged[-1] = (current_start, max(current_end, end))
        else:
            merged.append((start, end))
    return merged


def coverage(intervals) -> int:
    return sum(end - start for start, end in merge(intervals))
