# Corpus

Source texts and reference structure under the content bank. See
`docs/superpowers/specs/2026-07-17-corpus-assets-design.md` for the design and
`PROVENANCE.md` for where every asset came from.

- `sources/` — raw upstream files + provenance metadata. `sources/private/` is
  git-ignored: copyrighted personal-use texts only, never committed, never shipped.
- `ingest/` — deterministic stdlib scripts, `sources/ -> canon/`. Rerunnable.
- `canon/` — the normalized store; the only thing consumers read.
- `lib/passage.py: get_passage(version, ref)` — the one read path, with the
  license gate: product mode serves only public-domain / CC-BY displayable text.

Run tests: `python3 -m unittest discover -s corpus/tests -v`

Rebuild everything from sources:
`python3 corpus/ingest/build_books.py && python3 corpus/ingest/ingest_bible.py && python3 corpus/ingest/seed_pericopes.py MAT && python3 corpus/ingest/ingest_crossrefs.py && python3 corpus/ingest/ingest_westminster.py && python3 corpus/ingest/ingest_commentary.py`
