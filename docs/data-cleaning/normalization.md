# Normalization

Code: [`src/cleaning/normalize.py`](../../src/cleaning/normalize.py)

<details>
<summary><strong>ISBN handling</strong></summary>

| Function | Behavior |
|---|---|
| `normalize_isbn10(raw)` | Strips non-`[0-9Xx]` chars, uppercases; returns `None` unless exactly 10 chars remain |
| `normalize_isbn13(raw)` | Strips non-digits; returns `None` unless exactly 13 digits and prefixed `978`/`979` |
| `isbn10_to_isbn13(isbn10)` | Standard conversion: `978` + first 9 digits of the ISBN-10, then a recomputed check digit. Returns `None` if the first 9 characters aren't all digits (guards against a stray `X` or corrupted input landing mid-string) |
| `resolve_isbn13(isbn10, isbn13)` | Prefers an already-valid ISBN-13; falls back to deriving one from ISBN-10 |

`resolve_isbn13` is the one merge.py actually calls — every staged row ends up with either a
canonical ISBN-13 or `None`, never a raw/unvalidated value.

</details>

<details>
<summary><strong>Blocking keys</strong></summary>

Used only when a row has no usable ISBN-13, to group same-book rows across sources:

- `normalize_title_key(title)` — strips parenthetical series/subtitle info (`"(Hunger Games,
  #1)"`), drops everything after a colon, lowercases, strips non-alphanumerics. Aggressive by
  design: false-positive collisions across genuinely different books with the same short title
  are rare and get caught by the author-key half of the pairing.
- `author_lastname_key(authors)` — takes the **first** listed author's **last** whitespace-split
  token, lowercased. A single blocking key per row keeps the group-by cheap; it does not attempt
  to disambiguate co-authors.

</details>
