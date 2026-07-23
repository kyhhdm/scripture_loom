# Citation Tags + Two-Mode Hard Gate — Foundation Design

- **Date:** 2026-07-23
- **Status:** Design (approved to write; awaiting spec review)
- **Scope:** Foundation only. Enables — but does not include — the follow-on
  work (EN content-type style rules, ZH fluency-editor pass, editor-facing
  glossary explanations).

## Problem

Two rigidity guarantees must survive an authoring pipeline whose fluency we
want to *increase*:

1. **Scripture must be verbatim.** Any quoted verse must match the licensed
   corpus text (BSB for English, CUV for Chinese) — not a model paraphrase
   that "looks like the Bible."
2. **Doctrinal claims must have a real basis.** Any assertion anchored to the
   Westminster Standards (WCF / WLC / WSC) must cite a section that actually
   exists and actually supports it.

Today the deterministic gates rediscover quotes by string-matching against the
corpus (`quote_check`, `cuv_quote_check`, `quote_detect`). Discovery is
lossy and repeated at every stage: the gate has to *guess* which spans are
quotations, then match them. As we add a fluency-editor pass (which rewrites
Chinese prose), an undetected quote could be silently reworded and never
caught.

The load-bearing move is to make the model **declare** its citations inline as
it authors, so every downstream gate *verifies a declared claim* instead of
*rediscovering* it. A declaration is not trust — the gate still checks the
declared text against ground truth. It repositions string-matching from
discovery to verification.

## Non-goals (explicitly out of this spec)

- Content-type style rules (observation/interpretation/application phrasing).
- The blind ZH fluency-editor pass.
- Surfacing glossary explanations to editors.
- Any change to reader-facing output *other than* stripping tags.
- Retro-tagging the existing PHP/MAT drafts in bulk (see Backward Compatibility).

These ride on top of this foundation in later specs.

## Design

### 1. Tag vocabulary

Two inline XML-style elements, emitted by the LLM inside the existing
`{en, zh}` text fields. Canonical corpus ref format only (`PHP.1.6`), never
human format (`Philippians 1:6`).

**Scripture (quote mode):**

```
<verse ref="PHP.1.6">He who began a good work in you will carry it on to completion</verse>
```

- `ref`: a single marker `AAA.C.V` or a range `AAA.C.V-V` / `AAA.C.V-C.V`,
  matching the corpus marker grammar (`^[A-Z0-9]{3}\.\d+\.\d+$` per
  `corpus/lib/sections.py`, extended for ranges as `gates.py:_REF_TOKEN`
  already tokenizes).
- Inner text: the quoted words, verbatim from the corpus version for that
  language.

**Standards (basis mode):**

```
<doctrine std="WCF" ref="1.4">Scripture's authority rests on God, its author, not on any church</doctrine>
```

- `std`: one of `WCF`, `WLC`, `WSC`.
- `ref`: `WCF` → `chapter.section` (`1.4`); `WLC` / `WSC` → `Q<number>`
  (`Q1`).
- Inner text: the *paraphrase* of the doctrine (author's words), NOT a
  verbatim quote of the standard.

Two distinct elements (not one element with a `mode=` attribute) because the
verification semantics and attributes genuinely differ: `<verse>` verifies
inner text against ground truth; `<doctrine>` verifies only that the ref
resolves. Keeping them separate makes both the parser and the prompt
unambiguous.

Tags may nest zero-or-one deep in practice (a verse inside a sentence, a
doctrine claim in another); the parser treats them as independent inline
spans and does not require nesting.

### 2. Canonical storage & rendering

- **The tagged string is the stored source of truth** in every text field:
  `text.{en,zh}`, `leader_reference.text.{en,zh}`,
  `leader_reference.verse.{en,zh}`. (`category` carries no citations; it is
  never tagged.)
- **Rendering strips tags, keeps inner text.** A single function
  `strip_tags(s: str) -> str` removes `<verse …>`, `</verse>`, `<doctrine …>`,
  `</doctrine>` and preserves inner text exactly. Applied at every
  reader-facing surface:
  - the prototype kit renderer,
  - `compare_html.py` and `translate_compare_html.py` display cells.
- Rejected alternative: clean text + a char-offset sidecar. Offsets drift the
  moment any edit touches the string; co-locating the markup with the text is
  robust to edits.

### 3. The gate: `citation_check`

A new deterministic gate function in `content_bank/author/gates.py`, run per
item, per present language, added to `run_all`.

For each language string in the item (text, leader_reference.text,
leader_reference.verse):

1. **Parse tags, fail-closed on malformed markup.** Unbalanced/unclosed tags,
   unknown attributes, unknown `std`, or a `ref` that does not match the
   grammar → gate failure (flag: `citation.malformed`). No silent skip.

2. **quote-mode (`<verse>`):** resolve the ref via
   `corpus_bridge.passage_text(ref, version=…)` — `BSB` for the `en` string,
   `CUV` for the `zh` string (per `gates.py` `_EN_VERSION` / `_ZH_VERSION`). Normalize both sides (the same
   normalization `quote_check` / `cuv_quote_check` already use: whitespace,
   punctuation, CUV `「」` handling). Then:
   - **equality** required when the item `type` is `memory_verse`, OR the tag
     spans a whole verse/range (inner normalized text == full passage
     normalized text);
   - **containment** (inner normalized text is a contiguous substring of the
     passage) allowed for a sub-verse phrase.
   - Mismatch → `citation.verse_mismatch`.

3. **basis-mode (`<doctrine>`):** resolve the ref against the committed
   Standards sources and require it to **exist**:
   - `WCF`: `Data[Chapter==C].Sections[S-1]` exists (1-based section).
   - `WLC` / `WSC`: `Data[Number==N]` exists for `ref="Q<N>"`.
   - Unresolvable → `citation.basis_unresolved`.
   - Faithfulness of the paraphrase is **not** gated here — that is the human
     review gate's job ("AI proposes; leader confirms"). basis-mode
     guarantees a basis is *named and real*, nothing more.

4. **recall net (`quote_detect`):** after tag verification, run the existing
   content-based detector over the *stripped* text. A verbatim BSB/CUV span
   (≥ the existing `DETECT_MIN_WORDS` / `MIN_HAN` floor) that is NOT inside a
   `<verse>` tag → `citation.untagged_quote` — a **flag for repair**, never
   an auto-insert. This is the under-tagging safety net.

The gate returns the existing gate-result shape (`ok`, `flags`), so it plugs
into the existing repair loops (`_repair_to_clean` in build, `translate_with_gates`
in translation) with no new machinery.

**A new resolver module** `content_bank/lib/standards.py` provides
`resolve(std, ref) -> bool` (or the section text, for future use), loading the
three committed source JSONs via the same `corpus_bridge._load` path.

### 4. Authorship & cross-pipeline flow

- **The LLM authors all tags; the gate only verifies.** Authorship never moves
  to a script — only the model knows which spans it intends as quotes and
  which claims rest on which standard. A script re-deriving that is exactly the
  heuristic discovery we are removing.
- **English generation (`build_draft_prompt` / `build_cli`):** the model emits
  both `<verse>` and `<doctrine>` tags. `citation_check` verifies `en` verse
  text against BSB and that every `<doctrine>` ref resolves.
- **Translation (`build_translate_prompt` / `translate`):** tags are **carried
  through**. The model translates inner text, and re-tags the `zh` Scripture
  span so `citation_check` can verify it against **CUV**. It does **not** mint
  new `<doctrine>` tags — a doctrinal claim originates in English; translation
  only renders it. The `zh` `<doctrine>` inner text is the translated
  paraphrase; its `std`/`ref` are copied from the `en` tag.
- This makes the future blind ZH fluency pass safe: the fluency editor is
  instructed never to alter text inside a tag, and `citation_check` re-runs
  afterward to confirm tagged spans are byte-identical.

### 5. Prompt changes

- `build_draft_prompt.py`: add a "Citation tagging" section — the two
  elements, canonical ref format, "tag every quoted verse and every claim that
  rests on WCF/WLC/WSC; tag by function, down to the 4-word floor; do not tag
  incidental word overlap."
- `build_translate_prompt.py`: add "preserve every tag; translate inner text;
  keep Scripture spans verbatim CUV inside `<verse>`; copy `<doctrine>`
  `std`/`ref` unchanged and translate only the inner paraphrase."

### 6. Backward compatibility & migration

- **Untagged legacy content stays valid.** An item with no tags has nothing to
  verify by tag; `citation_check` passes it on the tag checks. The
  `quote_detect` recall net still flags any untagged verbatim quote in it, so
  legacy items with quotes surface as `citation.untagged_quote` on their next
  authoring/translate touch.
- **Migration is lazy:** re-tag on next touch. No bulk rewrite of PHP/MAT.
- `store_writer` / schema validation: the tagged string is still a non-empty
  string, so no schema change is required for storage. Tag *well-formedness*
  is enforced by the gate, not by schema validation.

## Testing

Network-free, `llm` mocked. New `content_bank/tests/test_citation_check.py`
and `test_standards.py`:

- accepts a correct `<verse>` (equality, full verse);
- accepts a sub-verse `<verse>` by containment;
- rejects a `<verse>` whose inner text was altered (`verse_mismatch`);
- rejects an out-of-range / malformed `ref` and unbalanced tags
  (`malformed`, fail-closed);
- `<doctrine std="WCF" ref="1.4">` resolves; `ref="1.99"` and `std="XYZ"`
  do not (`basis_unresolved`);
- `WSC`/`WLC` `Q1` resolves; `Q999` does not;
- an untagged verbatim BSB span is flagged `untagged_quote`;
- `strip_tags` yields clean reader text for both elements and leaves untagged
  text unchanged;
- CUV path: a `zh` `<verse>` verifies against the CUV corpus text.

Render-strip is covered where the renderers are tested
(`test_translate_compare_html.py`, prototype/compare tests).

## File-level impact (for the plan)

- **New:** `content_bank/lib/standards.py`, tests.
- **Modify:** `content_bank/author/gates.py` (add `citation_check`, register in
  `run_all`), `build_draft_prompt.py`, `build_translate_prompt.py`,
  `compare_html.py` + `translate_compare_html.py` (strip on render), the
  prototype kit renderer (strip on render), `translate.py` (carry tags).
- **Reuse unchanged:** `quote_detect.py`, `corpus_bridge.passage_text`, the
  existing repair loops.
