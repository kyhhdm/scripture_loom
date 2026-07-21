# Chinese translation with strict BSB→CUV alignment — design

- **Date:** 2026-07-21
- **Status:** Design (approved in brainstorming; pending written-spec review)
- **Depends on:** corpus lampposts (`wcf/wsc/wlc.json`), CUV canon (`cuv-simp.json`),
  the bilingual content schema (`content_bank/lib/schema.py`, `LANGS = {en, zh}`),
  the English quote gate (`content_bank/author/gates.py:quote_check`).

## Problem

Content is drafted in English (high quality from the `opus` backend), with Scripture
quoted verbatim from the **BSB**. Serving Mainland-China families requires a Chinese
rendering in which **every Scripture excerpt is the verbatim CUV (和合本) wording for
the same verse** — never a back-translation of the English quote — because the family
reads and memorizes CUV, and the fluency method requires prose to match the text they
hold. The content is theological (anchored to Westminster ch.1), so the translation
must meet a **high doctrinal-accuracy standard**, not merely be fluent Chinese.

Two hard parts:

1. **Alignment.** BSB and CUV are different translations with no word-level
   correspondence. A whole-verse quote aligns trivially by ref; a **sub-verse phrase**
   quoted inside prose has no deterministic matching sub-span in the Chinese verse.
2. **Doctrinal accuracy.** A generic translator renders theological terms wrongly
   (e.g. "justification" → 合理化 instead of 称义) and can silently soften doctrine
   ("infallible" → 可靠/"reliable"). Prompt exhortation alone does not hold a standard.

## Approach (decisions from brainstorming)

- **Coverage:** strict alignment for **all** Scripture excerpts, including inline
  sub-verse phrases — not just full-verse citations.
- **Placement:** a **standalone tool**, runnable on any store slice at any time;
  decoupled from the build stages.
- **Quote detection:** **content-based**, scanning the item's English against the
  BSB of **its own passage + explicitly cited refs** (not delimiter-based, not
  whole-Bible). Each hit carries its source verse → the CUV mapping key.
- **Fallback when no contiguous CUV span exists:** widen to the **smallest contiguous
  CUV span that contains the idea** (clause or whole verse). Strictness is never
  traded for a non-CUV rendering.
- **Accuracy is pinned, then verified:** a CUV-anchored **theological glossary**
  (mandated term renderings) + a **glossary gate** + a **back-translation
  doctrinal-review lens** + **human confirm** — the prompt carries the anchoring
  rules, the checks make the standard hold.
- **Language:** simplified CUV (`cuv-simp`); English is **kept** and `zh` added
  alongside (the schema already holds both), never replaced.

The work is three parts, sequenced **A → B → C**:

---

## Part A — Chinese Standards as a glossary reference (NOT a shipped asset)

The Chinese Westminster Standards are the doctrinal-vocabulary reference for glossary
extraction (Part B). They are **not** ingested as shippable corpus lampposts.

**Licensing reality (2026-07-21).** The chosen translation
(zh.ligonier.org, WCF/WSC/WLC) is **© Ligonier Ministries, All Rights Reserved,
personal-reference-use-only, redistribution prohibited** (`本資源僅供個人參考使用，請勿
以任何形式或管道重製、散播或販賣`). Shipping it inside the product would violate its
terms and the corpus license gate (which serves only `public-domain`/`CC-BY`). It is
therefore used **only as a personal-reference source to extract term-level
vocabulary** — a use the license permits and that does not reproduce the translation's
copyrightable sentence-level expression.

**Guardrails (binding):**

1. **Never shipped.** The full ZH Standards text lives only in a **gitignored working
   directory** (`work/glossary_build/standards_zh/`), never in `corpus/sources/` and
   never as `wcf-zh`/`wsc-zh`/`wlc-zh` canon lampposts.
2. **Term-level extraction only.** What leaves the working dir is the glossary's
   `{en_term, zh_term, sources}` entries — standard theological vocabulary (single
   words / short standard phrases), never verbatim answers or confession sections.
3. **No parallel-lamppost ingest.** `ingest_westminster.py` is **not** extended for
   `zh`; there is no shipped Chinese Standards asset.

**Doctrinal-fidelity check uses the English WCF-1.** The back-translation review lens
(Part C) compares the back-translated English against the **English** WCF-1 lamppost
(public domain, already shipped) — no shipped Chinese Standards is required for it.

If a genuinely public-domain or licensed-for-distribution Chinese Standards translation
is obtained later, the original parallel-lamppost design (shippable `wcf-zh` etc.,
key-aligned to the English, `proof_texts` shared) can be added then — it is an additive
change, not a redesign.

---

## Part B — Theological glossary (derived, not hand-seeded)

A reviewed index over **CUV (shipped, PD)** + the **Chinese Standards (reference only,
per Part A)**, mapping each theological head-term to its **mandated** Chinese rendering,
with every rendering traceable to a scriptural and/or confessional source. The glossary
itself ships (standard vocabulary, not copyrightable expression); the Standards text
behind the doctrinal entries does not.

**Two authoritative sources, by term type:**

- **CUV Bible** anchors **biblical** terms — words that appear in Scripture the family
  reads (圣徒 saints, 恩典 grace, 义 righteousness, 监督/执事 overseers/deacons). These
  must match the embedded CUV excerpts.
- **Westminster zh** anchors **systematic/doctrinal** terms that summarize rather than
  quote (称义 justification, 成圣 sanctification, 预定 predestination, 因信称义).

**Build (`content_bank/author/build_glossary.py`).** Walk a curated list of English
theological head-terms; for each, gather its attested Chinese rendering from (a) CUV
verses (BSB↔CUV aligned by ref) and (b) Westminster zh sections/Q&A (aligned by key),
recording every source. Emit `content_bank/author/glossary.json`:

```json
{ "en_term": "justification", "zh_term": "称义",
  "sources": ["WSC.33", "WCF.11.1"], "variants": [], "note": "..." }
```

**Precedence when CUV and the Standards differ:** if the term is **attested in CUV**
(it appears in Scripture), CUV's rendering is mandated (fluency requires prose to match
the memorized verse); terms existing **only** in systematic theology take the Standards'
rendering. Divergences are surfaced to the reviewer (both renderings shown) before the
`zh_term` is fixed. **A human curates the extracted list once** (bounded, one-time).

The glossary feeds two consumers: the translation **prompt** (mandated renderings) and
the deterministic **glossary gate** (Part C).

---

## Part C — The content translation tool

`content_bank/author/translate_cli.py` — standalone; reads a store slice, emits a
**translation proposal** (never mutates the served store directly), gated and
human-confirmed before `zh` lands.

### Per-item data flow

1. **Resolve source verses.** From the item's structured `passage` and any cited ref
   (`leader_reference.verse`), fetch both `get_passage("BSB", ref)` and
   `get_passage("CUV", ref)`.
2. **Detect BSB quotes (content-based).** Build the BSB haystack from the item's
   passage + cited refs; normalize (casefold, collapse whitespace, strip smart
   punctuation); find every **maximal span of the item's English occurring verbatim in
   that haystack**, length ≥ 4 words (kills coincidental function-word runs). Each hit
   → `(quote_text, source_ref)`, which keys the CUV counterpart.
3. **Translate (LLM).** Inputs: the English item; the detected quote spans + their
   paired BSB/CUV text; the **glossary**; the aligned **WCF-1 (EN + ZH)** frame.
   Rules (in the prompt):
   - Translate prose into natural simplified Chinese.
   - Render every detected Scripture span as its **verbatim CUV span**, wrapped in
     `「…」`; if no contiguous CUV span matches, **widen** (never back-translate).
   - Use **mandated glossary renderings** for theological terms; do not substitute
     synonyms.
   - **Doctrinal fidelity:** preserve every doctrinal claim exactly — do not soften,
     strengthen, reinterpret, evangelize, or add/remove. Evidence-not-judgment holds.
   - **Surface uncertainty:** structured output returns `zh` **plus** a `terms` report
     (which glossary terms were used) and an `uncertain` list. If a rendering is
     unsure, **flag it — never fabricate.**
   - Leave structured fields (dimension, refs, ids) untouched.
4. **Gate + repair** (mirrors the English `quote_check` + repair loop):
   - **`cuv_quote_check`** — every `「…」` span in a `zh` field must be a verbatim
     contiguous substring of CUV for the item's passage/cited refs (whole-CUV
     haystack, like the BSB gate). Length threshold in **Han characters (≥4)**, not
     `.split()`.
   - **`glossary_check`** — if the English contains a glossary term, the `zh` must
     contain the mandated rendering and none of the recorded known-wrong variants.
   - Flags feed the model for up to `--max-repair` rounds; remaining HARD flags fail
     the item.
5. **Back-translation doctrinal-review lens.** A second LLM pass translates the `zh`
   back to English and compares doctrinal meaning against the source + WCF-1; drift is
   flagged for the reviewer (does not auto-fail).
6. **Emit proposal.** `zh` fields + CUV refs used + `terms`/`uncertain`/gate/review
   status, to `work/content_bank_build/<BOOK>/translations/<unit>.json`.

### Review & promote (the human gate)

Extend `compare_html` to show, per item, **English ▸ Chinese ▸ CUV source verse ▸
flagged terms / back-translation drift**, so a reviewer confirms the excerpt matches
the family's Bible at a glance. Accept → a **promote** step writes `zh` into the store
item's language maps, touching neither `en` nor structured fields. This preserves
"human confirms before permanent" even though the tool may run on already-published
items.

### Gate changes to existing code

- **`quote_check` becomes language-aware:** `en` spans check against BSB (as today);
  `zh` spans check against CUV. Factor the haystack/version into a shared helper.
- **Fix single-quote detection:** `_quoted_spans` currently matches only double
  quotes; extend so single-quoted BSB phrases stop leaking past the English gate.
- **Length filter by script:** whitespace word-count for English; Han-char count for
  Chinese.

### CLI

`python -m content_bank.author.translate_cli`:

| Flag | Meaning |
|------|---------|
| `--book PHP` / `--items ID …` / `--status {reviewed,published}` | slice to translate |
| `--backend` / `--model` | reuse build backends; **default `opus`** (subtle CUV placement + doctrinal care reward the stronger model) |
| `--max-repair N` | gate-repair rounds (default 2) |
| `--out DIR` | proposal output (default `work/…/translations/`) |

Output parity with the builder: `[ok]`/`[FAIL]` per item, `Done. ok=N failed=M`.

---

## Testing (network-free, LLM seam mocked like `llm_core/tests`)

**Part A** — no shipped ZH Standards asset; a guard asserts no copyrighted Standards
text is written under `corpus/sources/` or the canon lampposts (the extraction
reference stays in the gitignored working dir).

**Part B** — glossary build extracts term pairs from CUV and the Standards reference
with correct `sources`; precedence rule picks CUV for a biblical term and Standards for
a doctrinal-only term; divergences recorded as `variants`; glossary entries are
term-level (no verbatim section/answer passages).

**Part C**
- `cuv_quote_check`: verbatim CUV passes; back-translated / altered span fails;
  Han-char length threshold; whole-CUV haystack allows a legitimate cross-ref quote.
- `quote_check` language-awareness: `en`→BSB, `zh`→CUV, single-quote fix, no
  cross-contamination.
- `glossary_check`: mandated term present passes; known-wrong variant fails.
- Detector: finds an **unquoted** verbatim BSB span; ignores a <4-word coincidence;
  returns the correct source ref.
- Promote round-trips `zh` into a temp store without touching `en` or structured fields.

## Invariants preserved

- **License gate.** Only `public-domain`/`CC-BY` text ships (CUV, English Standards).
  The copyrighted Ligonier Chinese Standards are reference-only: never entered into
  `corpus/sources/`, never shipped; only extracted term-level vocabulary survives.
- **Human is the gate.** Translations land only via confirm→promote; the tool proposes.
- **Theology not agnostic.** WCF-1 anchoring and glossary enforcement carry the
  doctrinal standard into the Chinese layer, not just the English.
- **Paper artifact / evidence-not-judgment** unchanged — this is a rendering layer.

## Sequencing & dependencies

- **A** (fetch the Ligonier ZH Standards into the gitignored working dir as an
  extraction reference) is unblocked — no owner source files needed.
- **B** is blocked on **A** (the reference) + CUV (already present).
- **C**'s *code* can be built in parallel, but its *output quality* depends on **B**.

## Open items / deferred

- Traditional-CUV output (`cuv-trad`) if a Hong Kong / Taiwan audience is later in
  scope — the design is version-parametrized, so it is an added canon version, not a
  redesign.
- Whole-BSB **audit** scan for unattributed cross-reference quotes (flag-only), if
  passage-anchored detection proves to miss real cases in review.
- Translating section `title_zh` (currently empty in `corpus/canon/structure/sections`)
  — small, can ride the same glossary/CUV machinery.
