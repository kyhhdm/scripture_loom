# Genre × dimension probe — findings

**Date:** 2026-07-19
**Question:** How does the genre of a book or pericope influence the content bank?
**Method:** Empirical probe. Rather than design a genre system up front, hand-author
content items across all eight fluency dimensions (D1–D8) for two deliberately
*non-narrative* passages and observe which dimensions have a natural home, which
strain, and which find no home at all. All shipped content to date (Matthew) is
narrative; the framework had never been stressed against another genre.

Passages (real BSB public-domain text, served through the corpus license gate),
drafted under the WCF-1 guardrail and the author harness's own dimension guidance
(including its standing rule: *"ONLY THE DIMENSIONS THIS PASSAGE GENUINELY SUPPORTS…
Do not pad"*):

- **Psalm 23** — pure Hebrew poetry (shepherd + host metaphors, first person).
- **Philippians 2:1–11** — epistle exhortation with an embedded Christ-hymn
  (v6–11), chosen because it also tests whether genre partitions cleanly per
  pericope.

## Starting thesis (being pressure-tested)

Genre does not add new dimensions; the eight are universal, and genre merely
**reweights** which dimensions are load-bearing per pericope and **reshapes the
question/activity templates** inside a surviving dimension. The systematic version
of this idea was a `genre → dimension-profile` table consulted by the author
harness and the selector. The probe was run to decide whether that table is worth
building.

## Result — Psalm 23 (Hebrew poetry)

| Dim | Representative item drafted | Verdict |
|---|---|---|
| D1 People/Places | "Who is the shepherd in this psalm?" (the LORD) | **△ forced** — one item works, but it is really a D7 "what does *shepherd* say about God" wearing a D1 hat. No cast, no map; "green pastures / valley of the shadow" are images, not geography. |
| D2 Sequence | "Does the valley come before or after the green pastures?" | **△ forced** — constructable, but measures *verse-order recall*, not narrative cause-and-effect. The psalm's meaning does not depend on the order. |
| D3 Vocabulary | "What does *I shall not want* mean here?" ('want' = lack) | **✓ load-bearing** |
| D4 Memory | Whole psalm as memory verse | **✓ strongest** — poetry is built to be memorized |
| D5 Connections | "Where else is God called a shepherd?" (John 10, Ezek 34) | **✓ strong** |
| D6 Questions | "What do you wonder about the valley of the shadow of death?" | **✓** (genre-neutral by design) |
| D7 Interpretation | "What is God compared to, and what does that say about His care?" | **✓ load-bearing but overloaded** |
| D8 Application | "Name one worry you could bring to the Shepherd this week." | **✓** |

Load-bearing genre skill with **no native dimension**: figurative/metaphor structure,
including the *shift* from the shepherd metaphor (v1–4) to the host/banquet metaphor
(v5). Absorbed silently into D3 + D7.

## Result — Philippians 2:1–11 (epistle + embedded hymn)

| Dim | Representative item drafted | Verdict |
|---|---|---|
| D1 People/Places | "Whose mind are the readers told to have?" (Christ's) | **△ strains** — persons exist, but this is argument-subject ID, not cast-and-map |
| D2 Sequence | v1–4: none possible · v6–11: "Put in order: form of God → emptied → servant → death → exalted" | **✗ / ✓ SPLIT within one pericope** |
| D3 Vocabulary | "What does *emptied Himself* mean?" (kenosis) | **✓ load-bearing** |
| D4 Memory | The hymn (v5–11) | **✓** — the poetic sub-section is the memorable one |
| D5 Connections | v10–11 directly quotes Isaiah 45:23 | **✓ strong** |
| D6 Questions | "What question does 'became obedient to death' raise for you?" | **✓** |
| D7 Interpretation | "Trace the *therefore* in v9 — why did God exalt Him?" | **✓ load-bearing but overloaded** |
| D8 Application | "One way to 'consider others more important' this week?" | **✓ possibly strongest** — paraenesis is applied ethics |

Load-bearing genre skill with **no native dimension**: argument-connective tracing
(*therefore / if-then / but / so that*). Absorbed silently into D7.

## Findings

1. **D1 and D2 are the narrative-specific dimensions — confirmed empirically.** In
   both passages they went vacuous or forced; D3–D8 carried the entire load. The
   eight dimensions are narrative-shaped at their root (an ontology of cast, map,
   and event sequence). This is not a flaw to fix — it is a fact to design around.

2. **No genre needed a ninth dimension.** Every passage was fully authorable within
   D1–D8. What each non-narrative genre has instead is a **load-bearing reading-move
   with no native home**, absorbed silently by D7 (and D3):
   - Poetry → figurative/metaphor structure and metaphor shifts.
   - Epistle → argument-connective tracing.

   This did not break authoring. But it is **invisible in the longitudinal record**:
   a child brilliant at retelling a story and a child brilliant at tracing an
   argument both score "D7." The dimension conflates distinct competencies across
   genres. This is the only finding with a real product consequence.

3. **Genre does not partition cleanly per pericope.** In Philippians 2, D2 is dead
   in v1–4 (paraenesis) and alive in v6–11 (the hymn's kenosis→exaltation arc) — in
   the *same pericope* — and the embedded hymn even partially *revives* D1/D2 inside
   an epistle. Genre is sub-pericope. **This kills the `genre → dimension-profile`
   table**: keyed at book or pericope level, it would mislabel half of this passage.

4. **The reweighting already happens at authoring time, with no genre system.** The
   harness already instructs the drafter not to pad unsupported dimensions, which is
   why the shipped Beatitudes items (MAT-014) carry zero D1 while the narrative
   temptation pericope (MAT-009) uses all eight. The authors reweighted by instinct
   from the text itself. The passage *is* the genre signal.

## Implications for design

- **No new dimensions. No `genre` field. No dimension-profile table.** The probe
  killed the systematic version of the original idea — which is the outcome we
  wanted before building it.
- **Two changes are real, cheap, and worth specifying:**
  - **Availability-driven selector.** The selector should offer a dimension for a
    pericope only when a published item exists for that pericope × dimension. This
    kills the concrete failure mode (assigning a D2 event-sequence observation
    target on a psalm that has no D2 content) with zero genre knowledge, because the
    author simply never drafted the unsupported dimension.
  - **Genre-specific brief templates for D3/D7 drafting.** Guidance in
    `author/briefs/`, not schema: "for poetry, D7 = image→referent and metaphor
    shift"; "for epistle, D7 = trace the connective." This shapes templates inside a
    surviving dimension, matching how authors already work.
- **One open product question the probe surfaced but cannot decide:** should the
  longitudinal member record distinguish *kinds* of D7 (narrative-meaning vs.
  argument-tracing vs. figurative-reading)? That would be an optional sub-label on
  existing items, not a schema overhaul — and is only worth it if per-genre fluency
  resolution in the member record is a product goal. Left for a separate decision.

## Status

Exploratory probe. No content committed; no schema changed. Drafted items above are
illustrative, not reviewed or published. Input to a possible future spec for the two
cheap changes.
