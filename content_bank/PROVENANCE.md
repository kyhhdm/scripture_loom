# Content bank provenance

## Seed content (2026-07-18)

The initial `store/mat.json` items were migrated from the kit-generator
prototype's hand-authored `prototype/content_bank.json` (25 items across three
prototype pericopes). Content is human-authored; `provenance.drafted_by` is
`hand` and each published item is recorded as reviewed against `WCF-1`
(Westminster Confession, Chapter 1).

### Boundary reconciliation (prototype refs → corpus pericope IDs)

The prototype's `mt-5-1-12` ("The Beatitudes", Matthew 5:1–12) does not exist as
a single corpus pericope: the corpus (seeded from BSB section headings) splits it
into `MAT-013` (5:1–2, "The Sermon on the Mount") and `MAT-014` (5:3–12, "The
Beatitudes"). Items were mapped to the pericope whose range actually covers their
content:

- `mt5a-q-mountain` and `mt5a-quest-who-listens` concern the crowds/mountain
  setup (5:1–2) → **MAT-013**.
- All other `mt5a-*` items concern the Beatitudes proper (5:3–12) → **MAT-014**.
- `mt4-*` → **MAT-009** (5:1–2... no: Matthew 4:1–11, exact match).
- `mt5b-*` → **MAT-015** (Matthew 5:13–16, exact match).

No pericope was invented. `MAT-013` is a real corpus pericope; it is simply not
placed in the sample family's reading sequence, so the prototype's linear
three-passage demo is preserved.

### Bilingual

Only English text was migrated. One item (`mt5a-mv-peacemakers`) carries a
seeded Chinese (`zh`) translation to exercise the bilingual read path. The
remaining `zh` translations are a documented, test-pinned gap (`missing_zh`),
to be authored later.
