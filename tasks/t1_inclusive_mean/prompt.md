Fix `mean_inclusive` in `stats.py`.

`mean_inclusive(values, start, end)` returns the arithmetic mean of the inclusive
index range `values[start]` through `values[end]`.

- `start` and `end` are integers. `start > end` raises `ValueError`.
- An index below 0 or past the last element raises `IndexError`.
- The mean of one element is that element.
- Do not change the function name or signature.
