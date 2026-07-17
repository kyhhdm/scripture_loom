# Design: The Content Bank (infrastructure layer)

- **Date:** 2026-07-18
- **Status:** approved design; implementation plan to follow
- **Depends on:** the corpus source layer (`corpus/`) and `docs/design-kit_generator.md` Part 2 (the `ContentItem` model, the static-library decision, and the Westminster guardrail).

## Purpose and scope

Build the **infrastructure** for Scripture Loom's content bank — the static, human-reviewed library of per-passage study content that the selector/kit generator draws from. This cycle delivers the machinery, not a book's worth of content:

- the storage format and schema for `ContentItem`s,
- a single gated read path (`get_content`) that serves only `published` content in product mode,
- structural + referential validation,
- an offline authoring harness (a per-pericope prompt pack that assembles the Westminster guardrail + schema, plus a human review checklist), and
- migration of the prototype's toy content into the new store, with the prototype rewired to consume it.

Authoring a real book's worth of `ContentItem`s, a live-API drafter, and selector/scheduler changes beyond repointing the loader are **explicitly out of scope** (see §9).

### Governing constraints inherited from the project

- **Python 3 standard library only.** No third-party packages, no network at read or validate time. (The authoring *prompt pack* is run by a human/Claude out-of-band; the repo itself makes no API calls.)
- **Diff-able normalized JSON**, consistent with the corpus canon store and the existing prototype.
- **The content bank is a layer *above* the corpus.** It reads from the corpus (passage text via `corpus.lib.passage.get_passage`; the Westminster Confession and MHC/JFB commentary via the lampposts) and never duplicates corpus-owned data such as pericope boundaries.
- **The library is not theologically agnostic.** All drafting is anchored to the Westminster Confession, especially Chapter 1 on Holy Scripture; the `draft → reviewed → published` gate includes explicit human conformity review (`docs/design-kit_generator.md`, "The theological guardrail").
- **Evidence, never judgment**, and the durable asset is the longitudinal per-member record — unchanged here, but the schema must key on stable IDs so records stay comparable over years.

## Design decisions (settled during brainstorming)

1. **Infrastructure first** — deliver the machinery plus small seed content, not authored content at scale.
2. **Prompt-harness, no live API** — the tooling assembles a per-pericope prompt pack; a human/Claude runs it and pastes back draft JSON, which the tooling validates. Keeps the stdlib-only/offline invariant intact.
3. **New top-level `content_bank/`** — a sibling of `corpus/` and `prototype/`, reflecting a distinct layer that consumes the corpus as a dependency.
4. **One JSON file per book** — e.g. `content_bank/store/matthew.json`. Review is logically per-pericope even though storage is per-book. Book files grow large over time; accepted for now.
5. **Migrate + rewire the prototype** — seed the store by migrating the prototype's three pericopes' items (re-keyed to corpus pericope IDs) and repoint `prototype/selector.py` + `generate_kit.py` to load from the new store. Prototype tests stay green. This also completes the design's deferred "migrate the prototype's string pericope keys to stable pericope IDs" follow-up.
6. **Full bilingual now** — the schema carries per-language text from the start.
7. **Bilingual model = one item, per-language text** — a single logical `ContentItem` owns one id and shares `dimension`/`type`/`age_tier`/`difficulty` across languages; only the language-specific strings live in a `text: {en, zh}` map. At least one language is required; a twin can be absent (a `zh`-only item remains one distinct item). One id in the member record regardless of render language — the cleanest longitudinal record.
8. **Enforcement model (Approach A)** — the *gate* is mechanical (product mode serves only `published`); the *guardrail* is assembled by the machine into every draft prompt and its review is *recorded* as a publish precondition, but conformity is **judged by a human**, never linted by keyword heuristics. The software proves an item was reviewed, not that it is doctrinally sound.

## Module layout

Mirrors `corpus/` conventions (stdlib-only, diff-able JSON, single gated read path):

```
content_bank/
  store/
    matthew.json          one file per book: { "book": "MAT", "items": [ ... ] }
  lib/
    __init__.py
    schema.py             ContentItem shape + controlled vocabularies; validate_item()
    content.py            get_content(...) — THE single read path + content gate
  author/
    build_draft_prompt.py     per-pericope prompt pack -> author/out/<PERICOPE>.prompt.md
    review_checklist.py       emits the draft->reviewed->published review sheet
  tests/
    test_schema.py
    test_content.py           gate + filtering + read-path behavior
    test_migration.py         prototype-parity after migration
  README.md
  PROVENANCE.md               content provenance: who drafted/reviewed, guardrail edition, boundary-mapping notes
```

## Data model

The store file is intentionally thin — it holds items only. **Pericope definitions are not duplicated here**; they live in the corpus (`MAT-005`, its `range`, `title_en`/`title_zh`). Items reference them by ID, keeping one source of truth for passage boundaries.

```jsonc
// content_bank/store/matthew.json
{
  "book": "MAT",
  "items": [
    {
      "id": "mat5a-q-blessed",        // globally unique, stable
      "passage": "MAT-005",           // FK -> corpus pericope ID (must resolve)
      "dimension": "D7",              // one of D1..D8
      "type": "question",             // question | activity | vocab_list | memory_verse |
                                      //   key_facts | narration_prompt | pre_reading_quest
      "age_tier": "youth",            // pre_reader | child | youth | adult | all
      "difficulty": 2,                // 1..3, within tier
      "review_status": "published",   // draft | reviewed | published
      "text": {                       // per-language map; >= 1 key required, each non-empty
        "en": "Who does Jesus call blessed? ...",
        "zh": "耶稣称谁为有福？..."
      },
      "category": {                   // optional; ONLY for pre_reading_quest (Stage-2 fade text); per-language
        "en": "What kind of list is this?",
        "zh": "..."
      },
      "provenance": {                 // required once review_status != "draft"
        "drafted_by": "ai",           // ai | hand
        "reviewed_by": "kyhhdm",
        "reviewed_date": "2026-07-18",
        "guardrail": "WCF-1"          // the standard the review checked against
      },
      "version": 1
    }
  ]
}
```

Differences from the prototype's shape: `body` -> `text:{en,zh}`; `passage` is now a corpus pericope ID (`MAT-005`) rather than a free string (`mt-5-1-12`); `category` becomes bilingual; `provenance` and `version` added.

### Controlled vocabularies (single source of truth in `schema.py`)

- `dimension`: `D1`..`D8`
- `type`: `question`, `activity`, `vocab_list`, `memory_verse`, `key_facts`, `narration_prompt`, `pre_reading_quest`
- `age_tier`: `pre_reader`, `child`, `youth`, `adult`, `all`
- `review_status`: `draft`, `reviewed`, `published`
- `lang` keys in `text`/`category`: `en`, `zh`
- `guardrail`: `WCF-1`
- `difficulty`: integer 1..3

## The read path + content gate

One public read function, exactly analogous to the corpus's `get_passage`:

```python
get_content(book, *, pericope=None, dimension=None, age_tier=None,
            lang="en", mode="product") -> list[ContentItem]
```

- **`mode="product"` (default) is the content gate: it returns only `review_status == "published"` items.** Drafts and reviewed-but-unpublished items are invisible to any product/selector path. This is the content-bank analog of the corpus license gate.
- **`mode="author"`** returns all statuses — used only by the authoring/review tooling, never by the kit generator.
- `lang` selects which `text` string is rendered. An item lacking the requested language is skipped for that language (counted as a "missing translation", never a crash).
- Filtering by `pericope` / `dimension` / `age_tier` / `lang` is deterministic and stdlib-only. `age_tier="all"` items match every tier filter.

**Loud at build, safe at read** (mirrors the corpus): `get_content` in product mode never raises on unpublished or missing-translation items — it filters and counts. Structurally invalid store data is a *validation* failure surfaced loudly in tests/CI, not a runtime surprise.

## Validation (`schema.validate_item` + a store-level validator)

Structural and referential lint, run in tests and available as a script:

- IDs are globally unique across the store.
- `passage` resolves to a real corpus pericope ID (referential integrity against `corpus/canon/structure/pericopes/`).
- `dimension` / `type` / `age_tier` / `review_status` / `guardrail` are in controlled vocab; `difficulty` in range.
- `text` has >= 1 language key and each present string is non-empty; `category` appears only on `pre_reading_quest` items.
- **Publish invariant:** `review_status != "draft"` requires `provenance.reviewed_by` and `provenance.reviewed_date` present and `provenance.guardrail == "WCF-1"`. A `published` item missing review provenance fails validation — unreviewed content cannot pass the gate.
- **Bilingual coverage report:** counts items missing `zh` (or `en`), so translation gaps are visible and test-pinned — never silent (mirrors the corpus's pinned dropped-ref counts).

## Authoring harness (prompt-pack, no live API)

`build_draft_prompt.py <PERICOPE_ID>` assembles a self-contained prompt pack to `author/out/<PERICOPE_ID>.prompt.md`:

- the passage text, via `corpus.lib.passage.get_passage` (a public-domain version served through the license gate),
- **the guardrail:** WCF Chapter 1, pulled from the corpus WCF lamppost, injected as a hard constraint,
- the D1–D8 dimension templates and age tiers (encoded once from `docs/design-kit_generator.md`),
- the exact JSON schema the output must satisfy,
- optional MHC/JFB lamppost excerpts for the pericope as factual/devotional reference.

A human (or Claude) runs the pack out-of-band and pastes back draft JSON; the store-level validator checks it before it enters the store as `draft`. `review_checklist.py <ITEM_ID|PERICOPE_ID>` prints the conformity + accuracy + age-fit checklist a reviewer uses to advance `draft -> reviewed -> published`, stamping `provenance`. The machine assembles the guardrail context and records that review happened; the human judges conformity.

## Prototype migration + rewire

- Migrate the items in `prototype/content_bank.json` (three pericopes: Matthew 4:1–11, 5:1–12, 5:13–16) into `content_bank/store/matthew.json`, re-keyed to corpus pericope IDs and to `text:{en: ...}`. Bilingual fields are present; `zh` is added later. Seed at least one `zh` string on one item so the bilingual read path is exercised by tests.
- **Boundary reconciliation:** the prototype's verse ranges must map to corpus seeded pericope ranges. Corpus boundaries derive from BSB section headings and may split differently. The migration maps each prototype item to the closest corpus pericope ID and records any discrepancy in `content_bank/PROVENANCE.md`; it does **not** silently invent a pericope. Exact ID mappings are resolved during implementation by inspecting `corpus/canon/structure/pericopes/mat.json`.
- Repoint `prototype/selector.py` and `prototype/generate_kit.py` to load content via `content_bank.lib.content.get_content` (product mode) and to read pericope titles/refs from the corpus rather than from an embedded pericope list.
- `prototype/test_selector.py` must stay green; update its fixtures to the new keys. Delete `prototype/content_bank.json` once migration parity is verified.

## Error handling

- `get_content` (product mode) never raises on unpublished or missing-translation items — it filters and counts.
- A malformed or dangling `passage` FK is a validation failure, not a read-time exception.
- Invalid store JSON or vocabulary violations fail loudly in the validator/tests (build time), consistent with the corpus's "loud at build, safe at read" split.

## Testing (stdlib `unittest`, matching the corpus)

- **Schema/vocabulary:** every controlled vocabulary enforced; `difficulty` range; `category` only on quests; `text` >= 1 non-empty language.
- **Publish invariant:** a `published` item missing review provenance fails validation.
- **Gate test:** a `draft` item and a `reviewed` item are both invisible in `mode="product"` and visible in `mode="author"`.
- **Referential integrity:** every item's `passage` resolves to a real corpus pericope ID.
- **Migration parity:** every migrated prototype item is present, re-keyed, and still `published`; counts match.
- **Bilingual:** the `zh` read path returns the seeded translation; missing-translation counts are pinned.
- **Prototype suite:** `prototype/test_selector.py` passes after the rewire.

Command (matching the corpus convention):
`python3 -m unittest discover -s content_bank/tests -v`

## Out of scope (this cycle)

- Authoring a real book's worth of `ContentItem`s (a separate spec -> plan -> build cycle).
- A live Claude-API drafter (the prompt-pack path is deliberate; a live drafter would add a network dependency and a third-party SDK).
- SQLite or any derived build artifact.
- Selector/scheduler logic changes beyond repointing the content loader.
- Reflect-phase capture (marks/photos -> `EvidenceItem`).
- Resolving the design's open "authored per language vs. translated pairs" question beyond decision #7 above; and the open reading-sequence / age-tier-boundary questions, which belong to the content-authoring cycle.

## Open items to resolve during implementation

- Exact prototype-ref -> corpus-pericope-ID mappings for Matthew 4:1–11, 5:1–12, 5:13–16, and any boundary discrepancies (recorded in `PROVENANCE.md`).
- The precise shape of the review checklist text (conformity + accuracy + age-fit prompts).
