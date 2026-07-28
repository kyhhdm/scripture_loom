# Using the Chinese translator

`content_bank/author/translate_cli.py` translates already-drafted English content into
simplified Chinese with **strict CUV alignment**. It is the translation counterpart of
the draft builder (`docs/content_builder_usage.md`): it reads a build run's drafts (or
the store), and for each item runs
**translate → CUV/glossary/citation gates (+ repair) → back-translation drift review →
proposal file**. Like the builder, it **never writes the store** — it emits *proposals*
a human reviews and promotes.

For the vocabulary (pericope, section, gate, citation tags, provenance), see
`docs/content_build_terminology.md`.

---

## Recommended configuration

- **Translator model: `deepseek-v4-flash`** (the `llm_core` default). It is fast and
  cheap and good enough for the reviewed-draft library; the CUV/citation gates plus
  human review are the backstop. A stronger model (`opus`) preserves citation tags more
  reliably but costs more per call.
- **Source drafts: an Opus generation run** (`runs/opus/drafts/`). Opus emits the
  cleanest `<verse>`/`<doctrine>` tags for the translator to carry through.

---

## Prerequisites

Run everything under `uv` (`uv run …`; `uv sync` first). A provider credential is
required — the seam refuses before any network call if none is configured:

- **`--backend llm_core`** (default) → deepseek via `ARK_API_KEY` in the repo `.env`
  (git-ignored; see `.env.example`). The default model is `deepseek-v4-flash`.
- **`--backend claude`** → the `claude` CLI (Claude Code headless) on `PATH`, billed to
  your subscription. Use `--model opus`/`sonnet`.

---

## How Chinese Scripture is marked (the nested form)

Every quoted verse in the Chinese carries **both** markers, nested:

```
<verse ref="PHP.1.6">「我深信那在你们心里动了善工的，必成全这工，直到耶稣基督的日子」</verse>
```

- The `<verse ref="…">` **tag** carries the machine-verifiable canonical ref.
- The CUV corner brackets `「…」` are the reader-facing Scripture-quote convention.

Reader surfaces (the printed kit) strip the tag and keep `「…」`; review pages highlight
the tag. The inner text must be the **shortest verbatim CUV span** that matches the
English quote — a short woven quote stays short (`「基督耶稣的仆人」`), never padded out to
the whole verse. `<doctrine std="…" ref="…">` tags are carried from the English and
translated inside, with `std`/`ref` unchanged — translation never mints new doctrine.

---

## Common commands

Translate a build run's drafts (the usual path — point at the run's `drafts/` dir):

```bash
uv run python -m content_bank.author.translate_cli \
    --book PHP \
    --drafts-dir work/content_bank_build/PHP/runs/opus/drafts
```

Translate specific items only:

```bash
uv run python -m content_bank.author.translate_cli \
    --book PHP --drafts-dir work/content_bank_build/PHP/runs/opus/drafts \
    --items PHP-001 php-s1-throughline
```

Translate from the **store** instead of a drafts dir (by review status):

```bash
uv run python -m content_bank.author.translate_cli --book PHP --status reviewed
```

Use a stronger translator (better tag preservation, higher cost):

```bash
uv run python -m content_bank.author.translate_cli \
    --book PHP --drafts-dir work/content_bank_build/PHP/runs/opus/drafts \
    --backend claude --model opus
```

---

## Flags

| Flag | Default | Meaning |
|------|---------|---------|
| `--book` | *(required)* | Book code, e.g. `PHP`. |
| `--drafts-dir DIR` | — | Translate a build run's drafts (`runs/<model>/drafts`) instead of the store. |
| `--items [ID ...]` | — | Restrict to these item ids (works with `--drafts-dir` or the store). |
| `--status STATUS` | — | Store mode only: translate items at this `review_status` (e.g. `reviewed`). |
| `--backend {llm_core,claude}` | `llm_core` | `llm_core` = deepseek via credits; `claude` = subscription. |
| `--model MODEL` | backend's default (`deepseek-v4-flash`) | Override the translator model. Sets the output slug. |
| `--max-repair N` | `2` | Gate-repair rounds before a proposal is emitted with `gate_ok:false`. |
| `--concurrency N` | `4` | How many items to translate in parallel (each item's translate→repair→back-translate chain stays sequential). |
| `--out DIR` | derived | Output dir. Defaults to `<drafts-dir>/../translations/<translator-slug>`. |

---

## Output layout

With `--drafts-dir …/runs/<gen-model>/drafts`, proposals default to a per-translator
dir beside the drafts:

```
work/content_bank_build/<BOOK>/runs/<gen-model>/translations/<translator-slug>/
    <item-id>.json          # one proposal per item
```

so `opus` drafts translated by `deepseek-v4-flash` land in
`runs/opus/translations/deepseek-v4-flash/`. Each proposal JSON carries:

- `id`, `en` — the item id and English source text
- `item` — the full item with `text.zh` (and `leader_reference`/`category` zh) merged in
- `cuv_refs` — the CUV refs detected for alignment
- `terms`, `uncertain` — the model's glossary-rendering report and self-flagged doubts
- `gate_ok`, `gate_flags` — CUV/glossary/citation gate result
- `drift` — the back-translation doctrinal-drift review (`{drift, notes}`)

`translate_cli` never writes the store; promoting an accepted proposal into the store
is a separate human-gated step (`translate.promote`).

---

## How an item is translated

1. **Translate.** The prompt gives the item, the aligned BSB↔CUV text for its refs, the
   applicable glossary terms, and the WCF-1 frame, and asks for the zh fields plus a
   terms report and an uncertainty list. Scripture is rendered as the nested
   `<verse ref>「…CUV…」</verse>` form (above); `<doctrine>` tags are carried through.
2. **Gates + repair.** `cuv_quote_check` (every `「…」` span is verbatim CUV),
   `glossary_check` (mandated term renderings), and `citation_check` (zh tags verify;
   a bare verbatim-CUV `「…」` left *outside* a `<verse>` tag is flagged
   `citation.untagged_quote`). Flags feed the repair loop for up to `--max-repair`
   rounds; anything left is reported on the proposal as `gate_ok:false` — it is **not**
   dropped, so a human sees it.
3. **Back-translation drift review.** The zh is back-translated and compared to the
   English + Westminster frame for softened/strengthened/added/removed doctrine; the
   verdict rides on the proposal as `drift`.

---

## Then compare

Generate the side-by-side translation review page (English ▸ CUV source ▸ one column per
translator), with citation tags highlighted:

```bash
uv run python -m content_bank.author.translate_compare_html PHP \
    --draft-run opus \
    --translators deepseek-v4-flash,opus
# → runs/opus/translations/review.html  (self-contained; open in a browser)
```

On the page: `<verse>` spans are highlighted green (with the ref) and `<doctrine>` amber,
and each cell carries **gate / drift / uncertain** badges. A translation that *dropped* a
tag shows up as an un-highlighted Chinese cell next to a highlighted English one — the
fastest way to spot a citation the translator failed to preserve.

---

## Practical notes

- **The gate guarantees citation correctness, not fluency.** A model can satisfy the
  gate with awkward prose (e.g. a whole-verse quote where a phrase was meant). The
  highlighted review page + human review are the fluency backstop; the prompt steers the
  model toward the shortest apt CUV span, but a cheap model still errs.
- **`deepseek-v4-flash` drops or mis-tags some citations** (a wrong CUV character, an
  untagged short phrase). This is expected — the gate flags them (`gate_ok:false`) so
  they surface for review rather than shipping silently. A stronger translator flags
  fewer.
- **Proposals are always written**, gated or not. `gate_ok:false` is a review signal,
  not a failure to emit.
- **Runs are independent** — translate the same drafts with several models into separate
  `translations/<slug>/` dirs and compare them on one page.
