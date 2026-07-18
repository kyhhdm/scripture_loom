# Content bank

The static, human-reviewed study-content library above the corpus. Items are
indexed by corpus pericope × dimension × age tier and served through one gated
read path.

- `store/<book>.json` — the content, one file per book, keyed on corpus pericope
  ids (e.g. `MAT-014`). Only `review_status: published` items are served in
  product mode.
- `lib/content.py: get_content(book, ...)` — the single read path + content
  gate (`mode="product"` serves published-only; `mode="author"` sees all).
- `lib/schema.py` — the controlled vocabularies and per-item validation.
- `lib/validate.py: validate_store(book)` — referential integrity against corpus
  pericopes, id uniqueness, and bilingual coverage counts.
- `lib/corpus_bridge.py` — read-only access to corpus pericopes, book names, the
  Westminster guardrail, and passage text.
- `lib/prototype_bank.py` — adapter to the kit-generator prototype's bank shape.
- `author/` — the offline drafting harness: `build_draft_prompt.py` assembles a
  per-pericope prompt pack (passage + WCF guardrail + dimensions + schema);
  `review_checklist.py` prints the draft→reviewed→published checklist. No API
  calls; drafting is human-in-the-loop.

Run tests: `python3 -m unittest discover -s content_bank/tests -v`

Bilingual: items carry per-language text (`text: {en, zh}`); one id per logical
item regardless of render language. Content authoring at scale is a separate
effort (see `docs/superpowers/specs/2026-07-18-content-bank-design.md`).
