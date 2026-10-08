Fix `parse_duration` in `duration.py`. It converts a duration string to
milliseconds.

The string is one or more pieces in this order: hours `h`, minutes `m`,
seconds `s`, milliseconds `ms`. Each unit appears at most once. Numbers are
non-negative integers. Leading zeros are allowed. There is no sign and no
spaces. At least one piece is required. Anything else raises `ValueError`:
a bad unit, units out of order, a repeated unit, a sign, a decimal, or spaces.

Examples: `1h` is 3600000, `1h30m15s` is 5415000, `500ms` is 500,
`1h2m3s4ms` is 3723004.

Do not change the function name or signature.
