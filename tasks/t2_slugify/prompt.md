Fix `slugify` in `slug.py`.

`slugify(text)` returns an ASCII slug:

- Lowercase ASCII letters and digits are kept.
- Spaces, underscores, and hyphens become a single hyphen.
- Other characters, including punctuation and non-ASCII letters, are dropped.
- Hyphens are never leading, trailing, or repeated.
- The empty string stays empty.

Do not change the function name or signature.
