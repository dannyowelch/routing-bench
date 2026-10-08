Fix `merge` and `coverage` in `intervals.py`.

Intervals are inclusive integer pairs `[start, end]`.

- `start > end` raises `ValueError`.
- Input may be unsorted and may contain duplicates, nested intervals, and
  point intervals where `start == end`.
- Two intervals merge when they overlap or touch, including at an endpoint.
  `[1, 2]` and `[2, 4]` merge to `[1, 4]`. `[1, 2]` and `[3, 4]` stay apart.
- `merge` returns a sorted list of disjoint intervals.
- `coverage` is the number of distinct integers covered. `[1, 2]` covers 2.
  `[5, 5]` covers 1. An empty list covers 0.
- Negative endpoints are allowed.

Do not change the function names or signatures.
