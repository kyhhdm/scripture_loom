# Content-bank prototype content: generate, judge, tune — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce the first harness-generated, adversarially-reviewed English content bank for the prototype's four Matthew pericopes — grounded in the corpus lampposts (Bible text, WCF, commentary, cross-references) — and tune the authoring machinery from the defects that review surfaces.

**Architecture:** A per-pericope loop — assemble the offline drafting pack (passage + WCF-1 + commentary + cross-references), draft items, break them with independent adversarial reviewer agents scored against a written rubric and handed the same lampposts as ground truth, triage each confirmed defect into fix-the-item or fix-the-machinery, repair/regenerate until clean. Passing items reach `review_status: "reviewed"`; a human confirmation digest gates the flip to `"published"`, after which the prototype serves them.

**Tech Stack:** Python 3 standard library only (no third-party packages). `unittest`. The existing `content_bank/` infrastructure and `corpus/` canon are dependencies; `corpus_bridge` gains read-only accessors this cycle.

## Global Constraints

- **Stdlib only.** No third-party packages, no network, no live API calls anywhere in `content_bank/` or `corpus/`. The drafting harness stays offline.
- **English-only this cycle.** Every item carries `text: {"en": "..."}`. No `zh`. No `zh`-conformity review.
- **Do not modify:** `content_bank/lib/schema.py`, `content_bank/lib/content.py`, `content_bank/lib/validate.py`, `content_bank/lib/prototype_bank.py`, `prototype/selector.py`, anything under `corpus/` (read-only). `corpus_bridge.py` **is** modified — additively (two new accessors), existing surface untouched.
- **Item types in scope:** `question`, `activity`, `pre_reading_quest`, `memory_verse`, `narration_prompt`. Not `vocab_list` / `key_facts` (selector does not render them).
- **Pericopes in scope:** `MAT-009`, `MAT-013`, `MAT-014`, `MAT-015`. No other Matthew pericope.
- **Provenance dates:** use `"2026-07-18"` for `reviewed_date`.
- **Answerable-from-this-pericope rule:** every non-D5 item must be answerable from its own pericope's verses. D5 (Connections) is the sole exception and must name where it reaches (grounded in the real cross-references).
- **Coverage restraint:** cover every dimension the passage *genuinely supports*, at the tiers the selector needs — no more. Under-covering a thin passage (e.g. MAT-013, 2 verses) is correct, not a gap.
- **Lampposts are authoring-time grounding only.** Commentary (JFB/MHC, public domain) and cross-references (CC-BY) inform the drafter and reviewers; they are never copied into shipped items (verbatim quotations come from the gated Bible text). No new license surface enters the store.
- **Vocabularies are single-sourced** in `schema.py` and `dimensions.py`. The invariant test `set(dimensions.TEMPLATES) == schema.DIMENSIONS` must stay green.
- **Tests:** `python3 -m unittest discover -s content_bank/tests -v`, `cd prototype && python3 -m unittest test_selector -v`, and `python3 -m unittest discover -s corpus/tests -v` must all pass at the end.

## Corpus asset shapes (verified)

- **Commentary:** `canon/lampposts/{mhc,jfb}/<book>.json` = `{work, book, license, role, blocks: [{range: "MAT.4.1-11", text}]}`. Keying differs by work: **MHC is per-pericope** (`MAT.5.1-2`, `MAT.5.3-12`, …), **JFB is per-verse** (`MAT.5.3`, `MAT.5.4`, …), and neither always aligns to pericope boundaries. Match by **range overlap**, not equality; return an empty list for a work with no overlapping block (robustness — all four in-scope pericopes do have commentary).
- **Cross-references:** `canon/structure/crossrefs.json` = `{license, role, refs: [{from: "MAT.5.3", to: "PSA.37.11", weight, sources}]}`, ~344k refs. Filter by `from` within the pericope range; rank by `weight` desc; cap the count.
- **Range format:** `BOOK.CH.V` or `BOOK.CH.V-V` (same as pericope `range`). A minimal parser (book, chapter, start-verse, end-verse) is enough for overlap/membership; a `from`/`to` may itself be a range — use its start verse for membership.

## Shared assets (defined once; referenced by the generation tasks)

**`REVIEWER_PROMPT`** — the adversarial reviewer agent is dispatched (Agent tool, `subagent_type: general-purpose`), ≥2 concurrently per pericope for independence, with this prompt:

```
You are an adversarial content reviewer for a Reformed family Bible-study
preparation tool. Your job is to BREAK the draft items below, not to praise them.
Assume each item is flawed until it survives every check.

PASSAGE: <pericope id> — <book name> (<range>)
PASSAGE TEXT (the ONLY text a non-D5 item may require to be answerable):
<passage_text>

GROUND TRUTH — check factual and interpretive claims against these:
COMMENTARY (JFB / MHC, overlapping this pericope):
<commentary_blocks>
CROSS-REFERENCES (openbible, ranked; the valid targets for a D5 item):
<crossrefs>

RUBRIC — score every item against all seven axes:
1. Confessional conformity (WCF-1): affirms, never hedges, Scripture's
   inspiration/infallibility/inerrancy/sufficiency/clarity; Scripture interprets
   Scripture; meaning drawn from the text, not speculation.
2. Accuracy & answerability: claims correct vs the passage AND the commentary
   above; names/places/sequence/quotations match; ANSWERABLE FROM THE PASSAGE
   TEXT ALONE (exception: a D5 item may reach outside, but only to a cross-
   reference listed above, and must name it).
3. Evidence never judgment: elicits observable behavior; never assesses faith,
   character, or spiritual state.
4. Age fitness: language + difficulty match age_tier; activities doable on paper.
5. Dimension fit: genuinely exercises its tagged dimension.
6. Worship not academy: serves fluency/the heart; nothing during-session
   (live scoring, gamification, dashboards, per-person screens).
7. Pedagogical strength: a good prompt — open where it should be, not leading,
   not trivially yes/no unless a deliberate warm-up.

DRAFT ITEMS (JSON array):
<items_json>

Return ONLY a JSON array, one object per item, in the same order:
[{"id": "...", "verdicts": {"1": "pass|fail", ..., "7": "pass|fail"},
  "defects": [{"axis": <n>, "severity": "critical|major|minor", "why": "...",
               "fix": "item|machinery", "suggestion": "..."}]}]
An item PASSES only if every axis is "pass". Cite the text/commentary in "why".
Mark fix="machinery" when the defect would recur across items because the
drafting instructions never told the drafter otherwise.
```

**Working files:** drafts and reviewer output live under the session scratchpad (`<scratchpad>/gen/`), not git. Only the assembled store, the tuning writeup, and machinery/code changes are committed.

**`TUNING_LOG`** — `docs/superpowers/notes/2026-07-18-content-tuning-log.md`, appended to as defects are triaged: each machinery fix with the defect (pericope + item + axis) that motivated it. Becomes the deliverable writeup (Task 13).

---

### Task 1: Rubric module (single source for the seven axes)

**Files:**
- Create: `content_bank/author/rubric.py`
- Test: `content_bank/tests/test_author.py` (add a class)

**Interfaces:**
- Produces: `rubric.build() -> str` (the seven-axis rubric text) and `rubric.AXES: tuple[str, ...]` (seven short axis titles, ordered).

- [ ] **Step 1: Write the failing test**

Add to `content_bank/tests/test_author.py`:

```python
class TestRubric(unittest.TestCase):
    def test_axes_are_seven_ordered_titles(self):
        from content_bank.author import rubric
        self.assertEqual(len(rubric.AXES), 7)
        self.assertEqual(rubric.AXES[0].lower()[:11], "confessiona")

    def test_build_names_every_axis_and_key_rules(self):
        from content_bank.author import rubric
        text = rubric.build().lower()
        for token in ("wcf-1", "answerable", "judgment", "age", "dimension",
                      "worship", "pedagog"):
            self.assertIn(token, text)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest content_bank.tests.test_author.TestRubric -v`
Expected: FAIL — `ModuleNotFoundError: content_bank.author.rubric`

- [ ] **Step 3: Write minimal implementation**

Create `content_bank/author/rubric.py`:

```python
"""The content quality rubric: seven axes, single-sourced.

Both the adversarial reviewers and author/review_checklist.py score against this.
Substance is judged (by agent then human), never keyword-linted; this text is the
standard they judge against. Meaning of the fluency dimensions themselves lives in
docs/design-kit_generator.md Part 1 and author/dimensions.py."""

AXES = (
    "Confessional conformity (WCF-1)",
    "Accuracy & answerability",
    "Evidence, never judgment",
    "Age fitness",
    "Dimension fit",
    "Worship, not academy",
    "Pedagogical strength",
)

_BODY = """# Content quality rubric

Score every item against all seven axes. An item passes only when it passes every
axis.

1. Confessional conformity (WCF-1). Affirms, and never hedges on, Scripture's
   inspiration, infallibility, inerrancy, sufficiency, and clarity. Scripture
   interprets Scripture (WCF 1.9); no private novelty. Meaning is drawn from the
   text, not from speculation.
2. Accuracy & answerability. Every factual claim is correct against the passage
   and the corpus lampposts (commentary); names, places, sequence, and quotations
   match. The item is answerable from THIS pericope's own verses. A D5
   (Connections) item is the sole exception and must name a real cross-reference.
3. Evidence, never judgment. Prompts elicit observable behavior; they never ask
   for or imply assessments of faith, character, or spiritual state.
4. Age fitness. Language and difficulty match the item's age_tier; activities are
   doable on paper with ordinary materials.
5. Dimension fit. The item genuinely exercises its tagged fluency dimension.
6. Worship, not academy. Serves fluency and the heart, not academic trivia; never
   anything that belongs during the gathering (live scoring, gamification,
   dashboards, per-participant screens).
7. Pedagogical strength. A genuinely good prompt: open where it should be open,
   not leading, not trivially yes/no unless a deliberate warm-up.
"""


def build():
    return _BODY
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest content_bank.tests.test_author.TestRubric -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/rubric.py content_bank/tests/test_author.py
git commit -m "content_bank: seven-axis quality rubric (single source)"
```

---

### Task 2: Review checklist sources from the rubric

**Files:**
- Modify: `content_bank/author/review_checklist.py`
- Test: `content_bank/tests/test_author.py` (replace `TestReviewChecklist`)

**Interfaces:**
- Consumes: `rubric.build()`, `rubric.AXES` (Task 1).
- Produces: `review_checklist.build(guardrail="WCF-1") -> str` — same signature, now covering all seven axes.

- [ ] **Step 1: Write the failing test**

Replace `TestReviewChecklist` in `content_bank/tests/test_author.py` with:

```python
class TestReviewChecklist(unittest.TestCase):
    def test_checklist_covers_all_seven_rubric_axes(self):
        text = review_checklist.build().lower()
        for token in ("westminster", "answerab", "judgment", "age",
                      "dimension", "worship", "pedagog"):
            self.assertIn(token, text)

    def test_checklist_still_takes_guardrail(self):
        self.assertIn("WCF-1", review_checklist.build(guardrail="WCF-1"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest content_bank.tests.test_author.TestReviewChecklist -v`
Expected: FAIL — `answerab`/`dimension`/`worship`/`pedagog` absent in current checklist.

- [ ] **Step 3: Write minimal implementation**

Rewrite `content_bank/author/review_checklist.py`:

```python
"""Print the draft -> reviewed -> published review checklist a human fills in.

Mirrors the seven-axis rubric (author/rubric.py) so the human confirmation gate
and the adversarial reviewers judge against the same standard."""
import argparse

from . import rubric

_HEAD = """# Content review checklist ({guardrail})

Advance an item draft -> reviewed -> published only when every box is checked.
Judged against the seven-axis rubric:

"""

_BOXES = """
## Confessional conformity ({guardrail}: Westminster Confession, Chapter 1)
- [ ] Affirms, and does not hedge on, Scripture's inspiration, infallibility,
      inerrancy, sufficiency, and clarity.
- [ ] Scripture interprets Scripture (WCF 1.9); meaning from the text, not
      speculation.

## Accuracy & answerability
- [ ] Every factual claim is correct against the passage and the corpus lampposts.
- [ ] Names, places, sequence, and quotations match the text.
- [ ] Answerable from THIS pericope's own verses (D5 Connections may name a real
      cross-reference).

## Evidence, never judgment
- [ ] Elicits observable behavior; never assesses faith, character, or state.

## Age fitness
- [ ] Language and difficulty match age_tier; activities doable on paper.

## Dimension fit
- [ ] Genuinely exercises its tagged fluency dimension.

## Worship, not academy
- [ ] Serves fluency and the heart; nothing during-session.

## Pedagogical strength
- [ ] A good prompt: open where it should be, not leading, not trivially yes/no.

On pass, stamp provenance:
  reviewed_by, reviewed_date, guardrail={guardrail}, and set review_status.
"""


def build(guardrail="WCF-1"):
    return _HEAD + rubric.build() + _BOXES.format(guardrail=guardrail)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--guardrail", default="WCF-1")
    args = ap.parse_args(argv)
    print(build(args.guardrail))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest content_bank.tests.test_author -v`
Expected: PASS (all classes)

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/review_checklist.py content_bank/tests/test_author.py
git commit -m "content_bank: review checklist mirrors the seven-axis rubric"
```

---

### Task 3: Expand per-dimension drafting guidance

**Files:**
- Modify: `content_bank/author/dimensions.py`
- Test: `content_bank/tests/test_author.py` (add `TestDimensions`)

**Interfaces:**
- Produces: `dimensions.TEMPLATES: dict[str, str]` — keys unchanged (`D1`..`D8`, equal to `schema.DIMENSIONS`); values expanded into drafting guidance.

- [ ] **Step 1: Write the failing test**

Add to `content_bank/tests/test_author.py`:

```python
class TestDimensions(unittest.TestCase):
    def test_keys_still_match_schema(self):
        from content_bank.lib import schema
        self.assertEqual(set(dimensions.TEMPLATES), schema.DIMENSIONS)

    def test_guidance_is_expanded_not_one_liners(self):
        for d, text in dimensions.TEMPLATES.items():
            self.assertGreater(len(text), 60, f"{d} guidance too thin")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest content_bank.tests.test_author.TestDimensions -v`
Expected: FAIL on `test_guidance_is_expanded_not_one_liners`.

- [ ] **Step 3: Write minimal implementation**

Rewrite `content_bank/author/dimensions.py`:

```python
"""The eight fluency dimensions, with drafting guidance for the prompt pack.
Source of truth for meaning remains docs/design-kit_generator.md Part 1; this
adds "what a good item does / what to avoid" so drafts fit the dimension and stay
answerable from the passage's own text."""

TEMPLATES = {
    "D1": "People & Places — who is present and where events happen. Good items "
          "name people/roles/locations the passage itself states. Avoid asking "
          "about people not in this pericope's verses.",
    "D2": "Event Sequence — the order and flow of what happens. Good items ask "
          "for first/next/last, cause-then-effect, or reordering — all "
          "recoverable from this passage. Avoid sequence that spans other "
          "pericopes.",
    "D3": "Vocabulary — the Bible's own key terms and repeated phrases. Good "
          "items point at a word/phrase the passage actually uses and ask what it "
          "means here (commentary may inform the sense). Avoid importing outside "
          "definitions as the 'answer'.",
    "D4": "Memory — memory verses, key phrases, recall. Good items quote or cue a "
          "line from THIS passage. Keep memory verses to one or two verses, "
          "quoted verbatim.",
    "D5": "Connections — links to other passages and larger patterns. The one "
          "dimension allowed to reach outside this pericope; a good item NAMES "
          "the other text it connects to, drawn from the cross-references.",
    "D6": "Questions — the learner's own question-asking, prompted here. Good "
          "items invite the learner to raise a wondering of their own; they do "
          "not smuggle in the leader's answer.",
    "D7": "Interpretation — what the text says, then why. Good items stay anchored "
          "to what the passage states before asking why; meaning from the text "
          "(commentary may confirm), not speculation. Avoid requiring doctrine "
          "the passage does not carry.",
    "D8": "Application — bringing the passage into life, observably. Good items "
          "ask for a concrete, doable response; never assess faith or character, "
          "only observable action.",
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest content_bank.tests.test_author -v`
Expected: PASS (all classes)

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/dimensions.py content_bank/tests/test_author.py
git commit -m "content_bank: expand per-dimension drafting guidance"
```

---

### Task 4: corpus_bridge accessors for commentary and cross-references

**Files:**
- Modify: `content_bank/lib/corpus_bridge.py` (additive)
- Test: `content_bank/tests/test_corpus_bridge.py` (add classes)

**Interfaces:**
- Produces:
  - `corpus_bridge.commentary(range_str, book="MAT", works=("mhc", "jfb")) -> dict[str, list[dict]]` — per work, the blocks whose `range` overlaps `range_str` (each block `{"range","text"}`); a work with no overlap maps to `[]`.
  - `corpus_bridge.crossrefs(range_str, limit=15) -> list[dict]` — refs whose `from` verse falls in `range_str`, sorted by `weight` desc then `to`, capped at `limit`.
  - Internal helper `corpus_bridge._parse_range(range_str) -> (book, chapter, v_start, v_end)`.

- [ ] **Step 1: Write the failing test**

Add to `content_bank/tests/test_corpus_bridge.py`:

```python
class TestCommentary(unittest.TestCase):
    def test_exact_block_returned(self):
        from content_bank.lib import corpus_bridge
        c = corpus_bridge.commentary("MAT.4.1-11")
        self.assertIn("mhc", c)
        self.assertTrue(c["mhc"])                      # a block overlaps 4:1-11
        self.assertIn("range", c["mhc"][0])
        self.assertIn("text", c["mhc"][0])

    def test_per_verse_jfb_overlaps_pericope(self):
        from content_bank.lib import corpus_bridge
        # JFB is keyed per verse; a pericope range must gather all overlapping verses
        c = corpus_bridge.commentary("MAT.5.1-2")
        self.assertIn("jfb", c)
        self.assertTrue(c["jfb"])                      # e.g. MAT.5.2 overlaps 5:1-2

    def test_no_overlap_is_graceful_empty(self):
        from content_bank.lib import corpus_bridge
        c = corpus_bridge.commentary("MAT.28.99-99")   # no such verses -> no blocks
        self.assertEqual(c["mhc"], [])
        self.assertEqual(c["jfb"], [])

    def test_beatitudes_block(self):
        from content_bank.lib import corpus_bridge
        c = corpus_bridge.commentary("MAT.5.3-12")
        self.assertTrue(any("5.3-12" in b["range"] for b in c["mhc"]))


class TestCrossrefs(unittest.TestCase):
    def test_refs_in_range_ranked(self):
        from content_bank.lib import corpus_bridge
        refs = corpus_bridge.crossrefs("MAT.5.3-12", limit=5)
        self.assertLessEqual(len(refs), 5)
        self.assertTrue(refs)                          # Beatitudes have OT echoes
        weights = [r["weight"] for r in refs]
        self.assertEqual(weights, sorted(weights, reverse=True))
        for r in refs:
            self.assertTrue(r["from"].startswith("MAT.5."))

    def test_empty_range_is_graceful(self):
        from content_bank.lib import corpus_bridge
        self.assertEqual(corpus_bridge.crossrefs("MAT.999.1-2"), [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest content_bank.tests.test_corpus_bridge -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'commentary'`.

- [ ] **Step 3: Write minimal implementation**

Append to `content_bank/lib/corpus_bridge.py`:

```python
def _parse_range(range_str):
    """'MAT.5.3-12' or 'MAT.5.3' -> ('MAT', 5, 3, 12)."""
    book, chapter, verses = range_str.split(".", 2)
    if "-" in verses:
        v1, v2 = verses.split("-", 1)
    else:
        v1 = v2 = verses
    return book, int(chapter), int(v1), int(v2)


def _overlaps(a, b):
    """Do two (book, chapter, start, end) tuples overlap?"""
    return (a[0] == b[0] and a[1] == b[1] and a[2] <= b[3] and b[2] <= a[3])


def commentary(range_str, book="MAT", works=("mhc", "jfb")):
    target = _parse_range(range_str)
    out = {}
    for work in works:
        data = _load(f"canon/lampposts/{work}/{book.lower()}.json")
        blocks = data.get("blocks", []) if isinstance(data, dict) else []
        out[work] = [b for b in blocks
                     if _overlaps(target, _parse_range(b["range"]))]
    return out


def crossrefs(range_str, limit=15):
    target = _parse_range(range_str)
    data = _load("canon/structure/crossrefs.json")
    refs = data.get("refs", []) if isinstance(data, dict) else data
    hits = [r for r in refs if _overlaps(target, _parse_range(r["from"]))]
    hits.sort(key=lambda r: (-r.get("weight", 0), r.get("to", "")))
    return hits[:limit]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest content_bank.tests.test_corpus_bridge -v`
Expected: PASS (commentary overlap for MHC per-pericope + JFB per-verse; crossrefs ranked and capped; graceful empty on non-overlapping ranges — all verified against the corpus).

- [ ] **Step 5: Commit**

```bash
git add content_bank/lib/corpus_bridge.py content_bank/tests/test_corpus_bridge.py
git commit -m "content_bank: corpus_bridge commentary + crossref accessors"
```

---

### Task 5: Fold rubric, answerability, coverage, and lampposts into the drafting pack

**Files:**
- Modify: `content_bank/author/build_draft_prompt.py`
- Test: `content_bank/tests/test_author.py` (extend `TestBuildDraftPrompt`)

**Interfaces:**
- Consumes: `rubric.build()` (Task 1), expanded `dimensions.TEMPLATES` (Task 3), `corpus_bridge.commentary` / `corpus_bridge.crossrefs` (Task 4), `schema`.
- Produces: `build_draft_prompt.build(pericope_id, book="MAT") -> str` — same signature; the pack now also states the answerability rule, coverage guidance, per-type expectations, an evidence-not-judgment constraint, embeds the rubric, and injects the pericope's commentary + top cross-references.

- [ ] **Step 1: Write the failing test**

Add to `TestBuildDraftPrompt` in `content_bank/tests/test_author.py`:

```python
    def test_states_answerability_rule(self):
        self.assertIn("answerable", self.prompt.lower())

    def test_states_coverage_restraint(self):
        p = self.prompt.lower()
        self.assertTrue("genuinely support" in p or "only the dimensions" in p)

    def test_embeds_rubric_and_evidence_rule(self):
        p = self.prompt.lower()
        self.assertIn("pedagog", p)                   # rubric embedded
        self.assertIn("observable behavior", p)       # evidence-not-judgment

    def test_gives_per_type_expectations(self):
        p = self.prompt.lower()
        self.assertIn("memory_verse", p)
        self.assertIn("pre_reading_quest", p)

    def test_injects_commentary_and_crossrefs(self):
        p = self.prompt.lower()
        self.assertIn("commentary", p)                # MAT-014 has MHC/JFB blocks
        self.assertIn("cross-reference", p)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest content_bank.tests.test_author.TestBuildDraftPrompt -v`
Expected: FAIL on the new assertions.

- [ ] **Step 3: Write minimal implementation**

Edit `content_bank/author/build_draft_prompt.py`. Update the import and add constants + blocks:

```python
from ..lib import corpus_bridge, schema
from . import dimensions, rubric
```

Add module constants above `build()`:

```python
_RULES_BLOCK = """## How to draft (hard rules)

- ANSWERABLE FROM THIS PASSAGE: every item except a D5 (Connections) item must be
  answerable from the verses printed above and nothing else. A D5 item may reach
  to other Scripture but only to one of the cross-references listed below, and
  must name it.
- COVER ONLY WHAT THE TEXT SUPPORTS: draft an item for a dimension only if this
  passage genuinely supports it. A short setup passage may support D1/D2/D6 and
  not D7/D8 — that is correct, not a gap. Do not pad.
- EVIDENCE, NEVER JUDGMENT: prompts elicit observable behavior; never assess
  faith, character, or spiritual state.
- USE THE LAMPPOSTS: let the commentary inform accuracy and interpretation; do
  not copy it into items (quotations come from the passage text above).
- TIERS: give the selector real choice — spread items across age_tiers
  (pre_reader / child / youth / adult / all) and difficulties (1-3)."""

_TYPE_BLOCK = """## What each type should be

- question: one clear question; tag the dimension it exercises.
- activity: doable on paper with ordinary materials; include a pre_reader variant
  when the passage allows one.
- pre_reading_quest: a "listen for X" prompt handed out before reading; include a
  short `category` label. Draft these at child / youth / adult tiers.
- memory_verse: one or two verses from THIS passage, quoted verbatim, with the
  reference.
- narration_prompt: "retell in your own words" for the passage as a whole."""


def _lamppost_block(range_str, book):
    parts = ["## Commentary (lampposts — grounding, do not copy verbatim)\n"]
    comm = corpus_bridge.commentary(range_str, book)
    any_block = False
    for work, blocks in comm.items():
        for b in blocks:
            any_block = True
            parts.append(f"### {work.upper()} {b['range']}\n{b['text']}\n")
    if not any_block:
        parts.append("(No commentary block overlaps this pericope.)\n")
    parts.append("## Cross-references (the valid targets for a D5 item)\n")
    refs = corpus_bridge.crossrefs(range_str)
    if refs:
        for r in refs:
            parts.append(f"- {r['from']} -> {r['to']} (weight {r.get('weight')})")
    else:
        parts.append("(No cross-references for this pericope.)")
    return "\n".join(parts)
```

Then in `build()`, after the dimensions loop's trailing `parts.append("")` and before the `## Output schema` block, insert:

```python
    parts.append(_RULES_BLOCK)
    parts.append("")
    parts.append(_TYPE_BLOCK)
    parts.append("")
    parts.append(_lamppost_block(p["range"], book))
    parts.append("")
    parts.append("## Quality rubric (every item must pass all seven axes)\n")
    parts.append(rubric.build())
    parts.append("")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest content_bank.tests.test_author -v`
Expected: PASS (all classes)

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/build_draft_prompt.py content_bank/tests/test_author.py
git commit -m "content_bank: drafting pack adds rules, rubric, and lamppost grounding"
```

---

### Task 6: Generate + adversarially review MAT-009 (pilot)

The first content task and the pilot for the tuning loop. Gate = adversarial review + `schema.validate_item`.

**Files:**
- Create (scratchpad): `<scratchpad>/gen/reviewed_MAT-009.json`
- Create/append: `docs/superpowers/notes/2026-07-18-content-tuning-log.md` (`TUNING_LOG`)
- Possibly modify (only if the pilot reveals a systemic gap): `content_bank/author/*`, `content_bank/lib/corpus_bridge.py`

**Interfaces:**
- Consumes: `build_draft_prompt.build("MAT-009")`, `REVIEWER_PROMPT`.
- Produces: a JSON array of `review_status: "reviewed"` items for MAT-009 at `<scratchpad>/gen/reviewed_MAT-009.json`, each structurally valid per `schema.validate_item`.

- [ ] **Step 1: Build the drafting pack**

Run: `python3 -m content_bank.author.build_draft_prompt MAT-009 --out <scratchpad>/gen/pack_MAT-009.md`
Expected: a self-contained pack — passage 4:1-11, WCF-1, dimension guidance, rules, types, **commentary (MHC/JFB 4:1-11) + cross-references**, rubric, schema.

- [ ] **Step 2: Draft items to the coverage target**

Draft a JSON array covering the dimensions MAT-009 supports (D1 people/places, D2 the three temptations in order, D3 "It is written" and key terms, D4 recall of Jesus answering with Scripture, D5 the OT sources — grounded in the pack's cross-references, D6 a learner question, D7 why Jesus answered with Scripture, D8 an observable application), spread across tiers, plus 1 child/youth `activity` + 1 `pre_reader` variant, `pre_reading_quest` at child/youth/adult, one `memory_verse` from this passage, one `narration_prompt`. Every item: `passage:"MAT-009"`, `review_status:"draft"`, `text:{"en":...}`, `version:1`, difficulty 1-3, `category` only on quests. Write `<scratchpad>/gen/draft_MAT-009.json`.

- [ ] **Step 3: Validate structure before review**

Run:
```bash
python3 -c "import json,sys; sys.path.insert(0,'.'); from content_bank.lib import schema; \
d=json.load(open('<scratchpad>/gen/draft_MAT-009.json')); \
[print(i['id'], schema.validate_item(i)) for i in d]"
```
Expected: every line ends `[]`. Fix any that don't.

- [ ] **Step 4: Adversarially review**

Dispatch ≥2 adversarial reviewer agents concurrently (one message, multiple Agent calls, `subagent_type: general-purpose`) with `REVIEWER_PROMPT`, substituting the MAT-009 passage text, the commentary blocks and cross-references (all from the pack), and `draft_MAT-009.json`. Union their defects.

- [ ] **Step 5: Triage every confirmed defect**

For each defect: if `fix="item"`, correct the item. If `fix="machinery"` (recurs, or the drafter/reviewer was never given what it needed — including a lamppost gap), append a `TUNING_LOG` entry (pericope + item + axis + the change), edit the relevant `author/` or `corpus_bridge.py` file, re-run its test (`python3 -m unittest content_bank.tests.test_author content_bank.tests.test_corpus_bridge -v` → PASS), and re-draft affected items.

- [ ] **Step 6: Re-review until clean**

Repeat Steps 4-5 until every item passes all seven axes. Then set each item's `review_status` to `"reviewed"` and add `"provenance": {"drafted_by":"claude","reviewed_by":"claude-adversarial","reviewed_date":"2026-07-18","guardrail":"WCF-1"}`. Write the final array to `<scratchpad>/gen/reviewed_MAT-009.json`.

- [ ] **Step 7: Commit the machinery/log changes**

```bash
git add docs/superpowers/notes/2026-07-18-content-tuning-log.md content_bank/
git commit -m "content_bank: MAT-009 generated + reviewed; tuning-log pilot findings"
```
(If no machinery changed, commit only the tuning log.)

---

### Task 7: Generate + adversarially review MAT-013 (thin-passage restraint check)

Same loop as Task 6 for `MAT-013` (5:1-2). Validates the coverage-restraint principle: supports D1 (crowds, disciples, mountain), D2 (saw crowds → went up → sat → disciples came → opened his mouth → taught), D6 — but **not** D5/D7/D8 answerably. Under-covering is correct. Commentary is available (MHC `5.1-2` + JFB `5.2`), so grounding is present even though coverage is deliberately thin.

**Files:**
- Create (scratchpad): `<scratchpad>/gen/reviewed_MAT-013.json`; Append `TUNING_LOG`; possibly modify `content_bank/*`.

**Interfaces:** Consumes same as Task 6, for `MAT-013`. Produces `<scratchpad>/gen/reviewed_MAT-013.json`.

- [ ] **Step 1: Build pack** — `python3 -m content_bank.author.build_draft_prompt MAT-013 --out <scratchpad>/gen/pack_MAT-013.md`
- [ ] **Step 2: Draft** — cover only D1/D2/D6 (plus a `narration_prompt` if the two verses support it); include a D1 `pre_reading_quest` ("who is on the mountain?") at child/adult and a D1/D2 `question`. Do NOT force D5/D7/D8. Write `<scratchpad>/gen/draft_MAT-013.json`.
- [ ] **Step 3: Validate structure** — the Task 6 Step 3 one-liner on `draft_MAT-013.json`; expect every line `[]`.
- [ ] **Step 4: Adversarially review** — `REVIEWER_PROMPT` with MAT-013 text + lampposts + drafts; ≥2 concurrent reviewers. A reviewer flagging "missing D7/D8" is NOT a defect here — record that restraint held.
- [ ] **Step 5: Triage** — item vs machinery, as Task 6 Step 5.
- [ ] **Step 6: Re-review until clean; stamp `reviewed` + provenance**; write `<scratchpad>/gen/reviewed_MAT-013.json`.
- [ ] **Step 7: Commit**:
```bash
git add docs/superpowers/notes/2026-07-18-content-tuning-log.md content_bank/
git commit -m "content_bank: MAT-013 generated + reviewed; coverage-restraint holds"
```

---

### Task 8: Generate + adversarially review MAT-014 (Beatitudes, flagship)

Same loop for `MAT-014` (5:3-12) — the richest passage, fullest supported coverage (D1 blessed-are groups, D2 the eight + the "they/you" shift in 11-12, D3 "blessed"/"kingdom of heaven", D4 a Beatitude memory verse, D5 OT echoes from the cross-references, D6, D7 who Jesus calls blessed vs the world, D8). Multiple questions, `activity` + `pre_reader` variant, quests at child/youth/adult.

**Files:**
- Create (scratchpad): `<scratchpad>/gen/reviewed_MAT-014.json`; Append `TUNING_LOG`; possibly modify `content_bank/*`.

**Interfaces:** Consumes same as Task 6, for `MAT-014`. Produces `<scratchpad>/gen/reviewed_MAT-014.json`.

- [ ] **Step 1: Build pack** — `python3 -m content_bank.author.build_draft_prompt MAT-014 --out <scratchpad>/gen/pack_MAT-014.md`
- [ ] **Step 2: Draft** the full supported coverage across tiers/difficulties. D5 items must name a cross-reference from the pack (e.g. Ps 37:11 for "inherit the earth"). Write `<scratchpad>/gen/draft_MAT-014.json`.
- [ ] **Step 3: Validate structure** — one-liner on `draft_MAT-014.json`; expect `[]`.
- [ ] **Step 4: Adversarially review** — `REVIEWER_PROMPT` with MAT-014 text + lampposts + drafts; ≥2 concurrent reviewers.
- [ ] **Step 5: Triage** — item vs machinery.
- [ ] **Step 6: Re-review until clean; stamp `reviewed` + provenance**; write `<scratchpad>/gen/reviewed_MAT-014.json`.
- [ ] **Step 7: Commit**:
```bash
git add docs/superpowers/notes/2026-07-18-content-tuning-log.md content_bank/
git commit -m "content_bank: MAT-014 Beatitudes generated + reviewed"
```

---

### Task 9: Generate + adversarially review MAT-015 (Salt & Light)

Same loop for `MAT-015` (5:13-16): D3 salt/light imagery, D7 what the light is for (v16), D4 the v16 memory verse, D8 observable "let your light shine", D6, D1/D2 as supported.

**Files:**
- Create (scratchpad): `<scratchpad>/gen/reviewed_MAT-015.json`; Append `TUNING_LOG`; possibly modify `content_bank/*`.

**Interfaces:** Consumes same as Task 6, for `MAT-015`. Produces `<scratchpad>/gen/reviewed_MAT-015.json`.

- [ ] **Step 1: Build pack** — `python3 -m content_bank.author.build_draft_prompt MAT-015 --out <scratchpad>/gen/pack_MAT-015.md`
- [ ] **Step 2: Draft** the supported coverage across tiers; write `<scratchpad>/gen/draft_MAT-015.json`.
- [ ] **Step 3: Validate structure** — one-liner on `draft_MAT-015.json`; expect `[]`.
- [ ] **Step 4: Adversarially review** — `REVIEWER_PROMPT` with MAT-015 text + lampposts + drafts; ≥2 concurrent reviewers.
- [ ] **Step 5: Triage** — item vs machinery.
- [ ] **Step 6: Re-review until clean; stamp `reviewed` + provenance**; write `<scratchpad>/gen/reviewed_MAT-015.json`.
- [ ] **Step 7: Commit**:
```bash
git add docs/superpowers/notes/2026-07-18-content-tuning-log.md content_bank/
git commit -m "content_bank: MAT-015 Salt and Light generated + reviewed"
```

---

### Task 10: Assemble the store; validate; prove the gate

**Files:**
- Modify: `content_bank/store/mat.json` (replace the 25 seed items with the assembled reviewed items)
- Test: `content_bank/tests/test_store_matthew.py`, `content_bank/tests/test_prototype_bank.py`

**Interfaces:**
- Consumes: `reviewed_MAT-009/013/014/015.json`; `validate.validate_store`, `content.get_content`.
- Produces: a store whose only items are the four pericopes' reviewed items; `validate_store("MAT")["errors"] == []`.

- [ ] **Step 1: Assemble the store**

Concatenate the four scratchpad arrays into `{"book":"MAT","items":[...]}` and write `content_bank/store/mat.json`. Every item currently `review_status:"reviewed"` (Task 12 flips to published). Verify ids are globally unique.

- [ ] **Step 2: Rewrite the seed-dependent store tests**

`content_bank/tests/test_store_matthew.py` is entirely seed-specific (all five methods assert the 25 seed items / deleted ids; `test_expected_counts` asserts 25/24/1). Replace the whole `TestMatthewStore` body with:

```python
class TestMatthewStore(unittest.TestCase):
    def test_store_validates_clean(self):
        self.assertEqual(validate.validate_store("MAT")["errors"], [])

    def test_only_scoped_pericopes_present(self):
        store = content.load_book_store("MAT")
        passages = {i["passage"] for i in store["items"]}
        self.assertEqual(passages, {"MAT-009", "MAT-013", "MAT-014", "MAT-015"})

    def test_every_item_reviewed_before_confirmation(self):
        # after assembly nothing is published yet -> product serves nothing
        self.assertEqual(content.get_content("MAT", mode="product"), [])
        self.assertTrue(content.get_content("MAT", mode="author"))
```
(`validate` and `content` are already imported at the top of the file.)

- [ ] **Step 3: Fix `test_prototype_bank.py` (seed ids + the zh test)**

`TestLoadBank` references deleted seed ids and `test_zh_bank_uses_translation` requires a `zh` item — impossible under English-only. `TestDisplayRef` is store-independent; leave it. Rewrite `TestLoadBank` to assert shape, not ids:

```python
class TestLoadBank(unittest.TestCase):
    def setUp(self):
        self.bank = pb.load_bank("MAT", lang="en")

    def test_pericopes_include_corpus_ids_with_display_refs(self):
        by_id = {p["id"]: p for p in self.bank["pericopes"]}
        self.assertEqual(by_id["MAT-014"]["ref"], "Matthew 5:3–12")
        self.assertEqual(by_id["MAT-014"]["title"], "The Beatitudes")

    def test_items_flattened_to_body_and_product_gated(self):
        # after publish (Task 12) product mode serves items with a flat 'body'
        self.assertTrue(self.bank["items"])
        item = self.bank["items"][0]
        self.assertIsInstance(item["body"], str)
        self.assertNotIn("text", item)
        self.assertNotIn("draft", {i["review_status"] for i in self.bank["items"]})
```
Delete `test_quest_category_flattened` and `test_zh_bank_uses_translation`. `test_content.py` uses temp fixtures and needs no change.

- [ ] **Step 4: Run the tests for state**

Run: `python3 -m unittest content_bank.tests.test_store_matthew -v`
Expected: the three `TestMatthewStore` tests PASS.
Run: `python3 -m unittest discover -s content_bank/tests -v`
Expected: PASS **except** `test_items_flattened_to_body_and_product_gated`, which asserts a non-empty product bank and only goes green after Task 12 publishes (flagged in the ordering dependency below).

- [ ] **Step 5: Commit**

```bash
git add content_bank/store/mat.json content_bank/tests/
git commit -m "content_bank: assemble MAT store (reviewed), replace seed; gate proven"
```

---

### Task 11: Wire MAT-013 into the sequence; resolve the demo passage

**Files:**
- Modify: `prototype/family.json`
- Test: `prototype/test_selector.py` (extend); manual `generate_kit.py` run

**Interfaces:**
- Consumes: the published store (after Task 12), `selector.build_kit`.
- Produces: `reading_sequence == ["MAT-009","MAT-013","MAT-014","MAT-015"]`; a coherent demo kit that still features the Beatitudes.

- [ ] **Step 1: Update the reading sequence and preserve the demo passage**

Edit `prototype/family.json`: set `"reading_sequence": ["MAT-009", "MAT-013", "MAT-014", "MAT-015"]`. Because `next_passage` returns the first *unstudied* pericope and only MAT-009 is studied, the demo kit would otherwise feature the thin MAT-013 setup. To keep the flagship demo on the Beatitudes, append a second studied session for MAT-013 so `next_passage` returns MAT-014:

```json
    {
      "date": "2026-07-15",
      "passage": "MAT-013",
      "evidence": [
        { "member": "liberty", "dimension": "D1", "code": "R", "quality": "✓", "prompted": true,
          "note": "Named the crowds and the disciples on the mountain." }
      ]
    }
```
(Append to `sessions`, after the MAT-009 session.)

- [ ] **Step 2: Write the failing test**

Add to `prototype/test_selector.py`:

```python
    def test_reading_sequence_includes_mat013_before_beatitudes(self):
        import json, pathlib
        fam = json.loads((pathlib.Path(__file__).parent / "family.json").read_text())
        self.assertIn("MAT-013", fam["reading_sequence"])
        self.assertEqual(fam["reading_sequence"].index("MAT-013"),
                         fam["reading_sequence"].index("MAT-014") - 1)
```

- [ ] **Step 3: Run the selector suite**

Run: `cd prototype && python3 -m unittest test_selector -v`
Expected: the new test PASSES. The existing `test_next_passage_follows_reading_sequence` (expects MAT-014) and `test_after_studying_beatitudes_next_is_salt_and_light` (expects MAT-015) still hold because of the added MAT-013 session. **These selector tests read the live store and only pass once Task 12 has published** — run this step green after Task 12.

- [ ] **Step 4: Verify the kit end-to-end** (after Task 12)

Run: `cd prototype && python3 generate_kit.py -o <scratchpad>/gen/kit_demo.md`
Expected: a kit for MAT-014 (Beatitudes) — review questions drawn from MAT-009/013, discussion questions across dimensions, an activity + younger variant, quests per member, a memory verse, a narration prompt. Read it; confirm coherence and that every referenced item exists.

- [ ] **Step 5: Commit**

```bash
git add prototype/family.json prototype/test_selector.py
git commit -m "prototype: add MAT-013 to reading sequence; keep Beatitudes as demo"
```

---

### Task 12: Human confirmation digest → publish

**Files:**
- Create: `<scratchpad>/gen/confirmation_digest.md`
- Modify: `content_bank/store/mat.json` (flip `reviewed` → `published`; add `confirmed_by`)

**Interfaces:**
- Consumes: the assembled store (Task 10).
- Produces: a published store; `get_content("MAT", mode="product")` non-empty.

- [ ] **Step 1: Build the confirmation digest**

Generate `<scratchpad>/gen/confirmation_digest.md`: one line per item — `id · passage · dimension · type · age_tier · difficulty · the en text` — grouped by pericope, with per-pericope dimension coverage and counts. This is what the human skims.

- [ ] **Step 2: Present the digest and STOP for human approval**

Present the digest to the user. Ask for approval to publish, or a list of items to hold/edit. **Do not proceed without an explicit answer.** Apply any edits requested (re-review edited items via the relevant generation task's Step 4 if substance changed).

- [ ] **Step 3: Stamp published**

For every approved item in `content_bank/store/mat.json`: set `review_status:"published"` and add `"confirmed_by":"kyhhdm"` to `provenance`. Leave any held item as `reviewed`.

- [ ] **Step 4: Prove the gate serves published content**

Run:
```bash
python3 -c "import sys; sys.path.insert(0,'.'); from content_bank.lib import content; \
print('published:', len(content.get_content('MAT', mode='product')))"
```
Expected: a positive count equal to the approved items.

- [ ] **Step 5: Update the gate test; run everything gated on publish**

Update `content_bank/tests/test_store_matthew.py::test_every_item_reviewed_before_confirmation` to reflect the published state (rename to `test_gate_serves_published` asserting `content.get_content("MAT", mode="product")` is non-empty and holds no `reviewed`/`draft`). Then:
```
python3 -m unittest discover -s content_bank/tests -v      # incl. test_prototype_bank now green
cd prototype && python3 -m unittest test_selector -v && cd ..
```
Expected: all PASS (this satisfies the Task 10 / Task 11 items that were gated on publish).

- [ ] **Step 6: Commit**

```bash
git add content_bank/store/mat.json content_bank/tests/test_store_matthew.py
git commit -m "content_bank: publish confirmed MAT items (human gate)"
```

---

### Task 13: Provenance, tuning writeup, final verification

**Files:**
- Modify: `content_bank/PROVENANCE.md`
- Finalize: `docs/superpowers/notes/2026-07-18-content-tuning-log.md`

**Interfaces:**
- Consumes: everything above.
- Produces: recorded provenance + a quality/tuning writeup; all three suites green.

- [ ] **Step 1: Record provenance**

Append to `content_bank/PROVENANCE.md`: this authoring cycle — pericopes MAT-009/013/014/015, drafted_by claude, grounded in BSB + WCF-1 + JFB/MHC commentary + cross-references, adversarially reviewed, human-confirmed by kyhhdm on 2026-07-18, English-only, seed replaced.

- [ ] **Step 2: Finalize the tuning writeup**

Complete `docs/superpowers/notes/2026-07-18-content-tuning-log.md`: (a) defects found by axis, (b) the machinery change each recurring defect motivated (file + what changed + why — including any lamppost-wiring adjustment), (c) residual known limitations (English-only; zh-conformity deferred; catechisms + lexicon not wired; thin-passage coverage; any axis the agents were weak at).

- [ ] **Step 3: Run every suite**

Run:
```bash
python3 -m unittest discover -s content_bank/tests -v
cd prototype && python3 -m unittest test_selector -v && cd ..
python3 -m unittest discover -s corpus/tests -v
```
Expected: all PASS, no regressions.

- [ ] **Step 4: Final kit smoke test**

Run: `cd prototype && python3 generate_kit.py` — confirm it prints a coherent Beatitudes kit with no missing items.

- [ ] **Step 5: Commit**

```bash
git add content_bank/PROVENANCE.md docs/superpowers/notes/2026-07-18-content-tuning-log.md
git commit -m "content_bank: provenance + quality/tuning writeup for prototype content"
```

---

## Self-Review

**Spec coverage:**
- Rubric (7 axes) → Task 1. Checklist mirrors it → Task 2. Dimension guidance → Task 3.
- Lamppost wiring: `corpus_bridge` commentary + crossref accessors → Task 4; injected into the drafting pack → Task 5; handed to reviewers as ground truth → `REVIEWER_PROMPT` (used in Tasks 6-9).
- Drafting-pack tuning (answerability, coverage, per-type, evidence, rubric) → Task 5.
- Generate + adversarial review per pericope, with triage/tuning → Tasks 6-9 (009/013/014/015); coverage-restraint exercised in Task 7.
- Regenerate-all-replace-seed + store validation + gate proof → Task 10.
- MAT-013 into sequence + demo-passage resolution → Task 11.
- `reviewed` → confirmation digest → `published` human gate → Task 12.
- Provenance + tuning writeup + full verification → Task 13. English-only, stdlib-only, scope limits, lampposts-not-shipped → Global Constraints.

**Placeholder scan:** No TBD/TODO. Generation tasks (6-9) are inherently generative, not code-TDD; each still has a concrete gate (structural `validate_item` + adversarial pass) and concrete commands. `<scratchpad>` is a real path supplied at execution time.

**Type consistency:** `rubric.build()`/`rubric.AXES` (Task 1) consumed in Tasks 2, 5. `dimensions.TEMPLATES` keys == `schema.DIMENSIONS` preserved (Task 3), invariant test kept green. `corpus_bridge.commentary(range_str, book, works)` / `corpus_bridge.crossrefs(range_str, limit)` defined in Task 4, consumed in Task 5's `_lamppost_block` and in the reviewer prompt. `build_draft_prompt.build(pericope_id, book)` signature unchanged (Task 5). Provenance keys (`drafted_by`, `reviewed_by`, `reviewed_date`, `guardrail`, `confirmed_by`) consistent across Tasks 6-9, 12, and satisfy `schema.validate_item`.

**Ordering dependency (flagged in-plan):** the live-store checks — Task 10 Step 4's `test_items_flattened_to_body_and_product_gated`, Task 11 Step 3's selector tests, and Task 11 Step 4's kit run — depend on Task 12 having published. Task 12 Step 5 is the point at which the full suites are expected green. This ordering is intentional: MAT-013 must be in the sequence (Task 11) and content assembled (Task 10) before a coherent demo can be judged, but nothing is published until the human confirms (Task 12).
