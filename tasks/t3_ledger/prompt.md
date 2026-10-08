Finish the expense ledger in the `ledger` package.

`Book.add(entry)` stores the entry and records its id on the category index.
`Book.apply_refund(entry_id, amount_cents)` subtracts a positive refund from
that entry's remaining amount.

- A duplicate id, a negative entry amount, a non-positive refund, or a refund
  larger than the remaining amount raises `ValueError`.
- An unknown id raises `KeyError`.
- A refund may reduce an entry to zero. The entry stays in the book and on
  the category index.
- `balance_by_category()` maps each category to the sum of remaining cents.
- `total_cents()` is the sum of remaining cents.
- `CategoryIndex.ids(category)` lists ids in the order they were added.

Keep the existing dataclasses and method names. You will need to change more
than one file.
