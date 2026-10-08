`shop.checkout.quote(lines, discounts, tax_rate_bps)` is wrong, and the
mistake crosses more than one module. Make it match these rules. Use
`tax_cents` from `shop.tax` for the tax.

- Merchandise is the sum of `unit_cents * qty`. A negative unit price or
  quantity raises `ValueError`. An empty line list has merchandise 0.
- Apply discounts in the order given.
- `PercentOff(bps)` reduces the current remaining merchandise by
  `floor(remaining * bps / 10000)`. `bps` must be from 0 through 10000.
- `AmountOff(cents)` subtracts cents from the remaining merchandise, which
  never goes below 0. `cents` must be >= 0.
- A bad discount value raises `ValueError`.
- Tax is half-up on the post-discount merchandise:
  `floor((amount * tax_rate_bps + 5000) / 10000)`.
  `tax_rate_bps` must be from 0 through 10000.
- `discount_cents` is merchandise minus the post-discount amount.
- `total_cents` is the post-discount amount plus tax.

Return a `Quote`. Keep the dataclass fields.
