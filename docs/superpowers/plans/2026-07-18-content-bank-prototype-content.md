# Content-bank prototype content: generate, judge, tune — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce the first harness-generated, adversarially-reviewed English content bank for the prototype's four Matthew pericopes, and tune the authoring machinery from the defects that review surfaces.

**Architecture:** A per-pericope loop — assemble the offline drafting pack, draft items, break them with independent adversarial reviewer agents scored against a written rubric, triage each confirmed defect into fix-the-item or fix-the-machinery, repair/regenerate until clean. Passing items reach `review_status: "reviewed"`; a human confirmation digest gates the flip to `"published"`, after which the prototype serves them.

**Tech Stack:** Python 3 standard library only (no third-party packages). `unittest`. The existing `content_bank/` infrastructure (schema, content gate, validate, corpus_bridge, prototype_bank) and `corpus/` are fixed dependencies.

## Global Constraints

- **Stdlib only.** No third-party packages, no network, no live API calls anywhere in `content_bank/` or `corpus/`. The drafting harness stays offline.
- **English-only this cycle.** Every item carries `text: {"en": "..."}`. No `zh`. No `zh`-conformity review.
- **Do not modify:** `content_bank/lib/schema.py`, `content_bank/lib/content.py`, `content_bank/lib/validate.py`, `content_bank/lib/corpus_bridge.py`, `content_bank/lib/prototype_bank.py`, `prototype/selector.py`, anything under `corpus/`.
- **Item types in scope:** `question`, `activity`, `pre_reading_quest`, `memory_verse`, `narration_prompt`. Not `vocab_list` / `key_facts` (selector does not render them).
- **Pericopes in scope:** `MAT-009`, `MAT-013`, `MAT-014`, `MAT-015`. No other Matthew pericope.
- **Provenance dates:** use `"2026-07-18"` for `reviewed_date`.
- **Answerable-from-this-pericope rule:** every non-D5 item must be answerable from its own pericope's verses. D5 (Connections) is the sole exception and must name where it reaches.
- **Coverage restraint:** cover every dimension the passage *genuinely supports*, at the tiers the selector needs — no more. Under-covering a thin passage (e.g. MAT-013, 2 verses) is correct, not a gap.
- **Vocabularies are single-sourced** in `schema.py` (`DIMENSIONS`, `TYPES`, `AGE_TIERS`) and `dimensions.py` (`TEMPLATES`). The existing invariant test `set(dimensions.TEMPLATES) == schema.DIMENSIONS` must stay green.
- **Tests:** `python3 -m unittest discover -s content_bank/tests -v` and `cd prototype && python3 -m unittest test_selector -v` and `python3 -m unittest discover -s corpus/tests -v` must all pass at the end.

## Shared assets (defined once; referenced by the generation tasks)

**`RUBRIC_AXES`** — the seven quality axes (full text lives in `content_bank/author/rubric.py`, Task 1): (1) Confessional conformity WCF-1, (2) Accuracy & answerability, (3) Evidence never judgment, (4) Age fitness, (5) Dimension fit, (6) Worship not academy, (7) Pedagogical strength.

**`REVIEWER_PROMPT`** — the adversarial reviewer agent is dispatched (via the Agent tool, `subagent_type: general-purpose`) once per lens, or once with all axes, with this prompt:

```
You are an adversarial content reviewer for a Reformed family Bible-study
preparation tool. Your job is to BREAK the draft items below, not to praise them.
Assume each item is flawed until it survives every check.

PASSAGE: <pericope id> — <book name> (<range>)
PASSAGE TEXT (the ONLY text an item may require to be answerable):
<passage_text>

RUBRIC — score every item against all seven axes:
1. Confessional conformity (WCF-1): affirms, never hedges, Scripture's
   inspiration/infallibility/inerrancy/sufficiency/clarity; Scripture interprets
   Scripture; meaning drawn from the text, not speculation.
2. Accuracy & answerability: claims correct vs the passage; names/places/
   sequence/quotations match; ANSWERABLE FROM THE PASSAGE TEXT ABOVE ALONE
   (exception: a D5 item may reach outside if it names where).
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
[{"id": "...", "verdicts": {"1": "pass|fail", "2": "pass|fail", ...,"7": "pass|fail"},
  "defects": [{"axis": <n>, "severity": "critical|major|minor", "why": "...",
               "fix": "item|machinery", "suggestion": "..."}]}]
An item PASSES only if every axis is "pass". Be specific in "why" — cite the
text. Mark fix="machinery" when the defect would recur across items because the
drafting instructions never told the drafter otherwise.
```

**Working files:** drafts and reviewer output live under the session scratchpad (`<scratchpad>/gen/`), not git. Only the assembled store, the tuning writeup, and machinery/code changes are committed.

**`TUNING_LOG`** — `docs/superpowers/notes/2026-07-18-content-tuning-log.md`, appended to as defects are triaged: each machinery fix with the defect (pericope + item + axis) that motivated it. Becomes the deliverable writeup (Task 12).

---

### Task 1: Rubric module (single source for the seven axes)

**Files:**
- Create: `content_bank/author/rubric.py`
- Test: `content_bank/tests/test_author.py` (add a class)

**Interfaces:**
- Produces: `rubric.build() -> str` (the seven-axis rubric text) and `rubric.AXES: tuple[str, ...]` (the seven short axis titles, ordered).

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
   and the corpus lampposts; names, places, sequence, and quotations match. The
   item is answerable from THIS pericope's own verses. A D5 (Connections) item is
   the sole exception and must name where it reaches.
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
- Test: `content_bank/tests/test_author.py` (extend `TestReviewChecklist`)

**Interfaces:**
- Consumes: `rubric.build()`, `rubric.AXES` (Task 1).
- Produces: `review_checklist.build(guardrail="WCF-1") -> str` — same signature as today, now covering all seven axes.

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
Expected: FAIL — `answerab`/`dimension`/`worship`/`pedagog` not present in current checklist.

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
- [ ] Answerable from THIS pericope's own verses (D5 Connections may reach out if
      it names where).

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
Expected: PASS (all classes, including the unchanged `TestBuildDraftPrompt` and `TestRubric`)

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/review_checklist.py content_bank/tests/test_author.py
git commit -m "content_bank: review checklist mirrors the seven-axis rubric"
```

---

### Task 3: Expand per-dimension drafting guidance

**Files:**
- Modify: `content_bank/author/dimensions.py`
- Test: `content_bank/tests/test_author.py` (extend `TestBuildDraftPrompt` and the invariant test)

**Interfaces:**
- Produces: `dimensions.TEMPLATES: dict[str, str]` — keys unchanged (`D1`..`D8`, equal to `schema.DIMENSIONS`); values expanded from one-liners into drafting guidance (what a good item for this dimension does, and what to avoid).

- [ ] **Step 1: Write the failing test**

Add to `content_bank/tests/test_author.py`, inside `TestBuildDraftPrompt` (or a new `TestDimensions`):

```python
class TestDimensions(unittest.TestCase):
    def test_keys_still_match_schema(self):
        from content_bank.lib import schema
        self.assertEqual(set(dimensions.TEMPLATES), schema.DIMENSIONS)

    def test_guidance_is_expanded_not_one_liners(self):
        # every template now carries real drafting guidance, not a bare label
        for d, text in dimensions.TEMPLATES.items():
            self.assertGreater(len(text), 60, f"{d} guidance too thin")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest content_bank.tests.test_author.TestDimensions -v`
Expected: FAIL on `test_guidance_is_expanded_not_one_liners` (current values are short labels).

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
          "means here. Avoid importing outside definitions as the 'answer'.",
    "D4": "Memory — memory verses, key phrases, recall. Good items quote or cue a "
          "line from THIS passage. Keep memory verses to one or two verses, "
          "quoted verbatim.",
    "D5": "Connections — links to other passages and larger patterns. The one "
          "dimension allowed to reach outside this pericope; a good item NAMES "
          "the other text it connects to (book/verse or clear reference).",
    "D6": "Questions — the learner's own question-asking, prompted here. Good "
          "items invite the learner to raise a wondering of their own; they do "
          "not smuggle in the leader's answer.",
    "D7": "Interpretation — what the text says, then why. Good items stay anchored "
          "to what the passage states before asking why; meaning from the text, "
          "not speculation. Avoid requiring doctrine the passage does not carry.",
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

### Task 4: Fold the rubric, answerability, and coverage into the drafting pack

**Files:**
- Modify: `content_bank/author/build_draft_prompt.py`
- Test: `content_bank/tests/test_author.py` (extend `TestBuildDraftPrompt`)

**Interfaces:**
- Consumes: `rubric.build()` (Task 1), expanded `dimensions.TEMPLATES` (Task 3), `corpus_bridge`, `schema`.
- Produces: `build_draft_prompt.build(pericope_id, book="MAT") -> str` — same signature; the pack now also states the answerability rule, the coverage-per-supported-dimension guidance, per-type expectations, an evidence-not-judgment constraint, and embeds the rubric.

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
        self.assertIn("pedagog", p)          # rubric embedded
        self.assertIn("observable behavior", p)  # evidence-not-judgment constraint

    def test_gives_per_type_expectations(self):
        p = self.prompt.lower()
        self.assertIn("memory_verse", p)
        self.assertIn("pre_reading_quest", p)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest content_bank.tests.test_author.TestBuildDraftPrompt -v`
Expected: FAIL on the new assertions (`answerable`, coverage, `observable behavior`, per-type block absent).

- [ ] **Step 3: Write minimal implementation**

Edit `content_bank/author/build_draft_prompt.py`. Add `rubric` to the import and insert new blocks. Replace the body of `build()` between the dimensions loop and the schema block, and add constants:

```python
from ..lib import corpus_bridge, schema
from . import dimensions, rubric
```

Add these module constants above `build()`:

```python
_RULES_BLOCK = """## How to draft (hard rules)

- ANSWERABLE FROM THIS PASSAGE: every item except a D5 (Connections) item must be
  answerable from the verses printed above and nothing else. A D5 item may reach
  to other Scripture but must name where.
- COVER ONLY WHAT THE TEXT SUPPORTS: draft an item for a dimension only if this
  passage genuinely supports it. A short setup passage may support D1/D2/D6 and
  not D7/D8 — that is correct, not a gap. Do not pad.
- EVIDENCE, NEVER JUDGMENT: prompts elicit observable behavior; never assess
  faith, character, or spiritual state.
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
```

Then in `build()`, after the dimensions loop (`parts.append("")` that follows it) and before the `## Output schema` block, insert:

```python
    parts.append(_RULES_BLOCK)
    parts.append("")
    parts.append(_TYPE_BLOCK)
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
git commit -m "content_bank: drafting pack states answerability, coverage, rubric"
```

---

### Task 5: Generate + adversarially review MAT-009 (pilot)

This is the first content task and the pilot for the tuning loop. It is not unit-TDD; its gate is the adversarial review plus `schema.validate_item`.

**Files:**
- Create (scratchpad, not git): `<scratchpad>/gen/reviewed_MAT-009.json`
- Create/append: `docs/superpowers/notes/2026-07-18-content-tuning-log.md` (`TUNING_LOG`)
- Possibly modify (only if the pilot reveals a systemic gap): `content_bank/author/{build_draft_prompt,dimensions,rubric}.py`

**Interfaces:**
- Consumes: `build_draft_prompt.build("MAT-009")`, `REVIEWER_PROMPT`, `RUBRIC_AXES`.
- Produces: a JSON array of `review_status: "reviewed"` items for MAT-009 at `<scratchpad>/gen/reviewed_MAT-009.json`, each structurally valid per `schema.validate_item`.

- [ ] **Step 1: Build the drafting pack**

Run: `python3 -m content_bank.author.build_draft_prompt MAT-009 --out <scratchpad>/gen/pack_MAT-009.md`
Expected: a self-contained pack (passage 4:1-11, WCF-1, dimensions, rules, types, rubric, schema).

- [ ] **Step 2: Draft items to the coverage target**

Draft a JSON array covering the dimensions MAT-009 supports (D1 people/places, D2 the three temptations in order, D3 key terms e.g. "It is written", D4 memory of Jesus answering with Scripture, D5 the OT sources quoted, D6 a learner question, D7 why Jesus answered with Scripture, D8 an observable application), spread across tiers, plus: 1 child/youth `activity` + 1 `pre_reader` variant, `pre_reading_quest` at child/youth/adult, one `memory_verse` from this passage, one `narration_prompt`. Every item: `passage:"MAT-009"`, `review_status:"draft"`, `text:{"en":...}`, `version:1`, difficulty 1-3, `category` only on quests. Write to `<scratchpad>/gen/draft_MAT-009.json`.

- [ ] **Step 3: Validate structure before review**

Run:
```bash
python3 -c "import json,sys; sys.path.insert(0,'.'); from content_bank.lib import schema; \
d=json.load(open('<scratchpad>/gen/draft_MAT-009.json')); \
[print(i['id'], schema.validate_item(i)) for i in d]"
```
Expected: every line ends `[]` (no structural errors). Fix any that don't.

- [ ] **Step 4: Adversarially review**

Dispatch adversarial reviewer agent(s) with `REVIEWER_PROMPT`, substituting the MAT-009 passage text (from the pack) and `draft_MAT-009.json`. Use the Agent tool, `subagent_type: general-purpose`. For independence, run at least two reviewers concurrently (one message, multiple Agent calls) and union their defects.

- [ ] **Step 5: Triage every confirmed defect**

For each defect the reviewers return: if `fix="item"`, correct the item text/tier/dimension/difficulty. If `fix="machinery"` (recurs, or the drafter was never told), append an entry to `TUNING_LOG` naming the pericope + item + axis + the change, edit the relevant `author/` file, and re-run its test (`python3 -m unittest content_bank.tests.test_author -v` → PASS). Re-draft affected items.

- [ ] **Step 6: Re-review until clean**

Repeat Steps 4-5 until every item passes all seven axes. Then set each item's `review_status` to `"reviewed"` and add `"provenance": {"drafted_by":"claude","reviewed_by":"claude-adversarial","reviewed_date":"2026-07-18","guardrail":"WCF-1"}`. Write the final array to `<scratchpad>/gen/reviewed_MAT-009.json`.

- [ ] **Step 7: Commit the machinery/log changes (content stays in scratchpad until Task 9)**

```bash
git add docs/superpowers/notes/2026-07-18-content-tuning-log.md content_bank/author/ content_bank/tests/
git commit -m "content_bank: MAT-009 generated + reviewed; tuning-log pilot findings"
```
(If no machinery changed, commit only the tuning log.)

---

### Task 6: Generate + adversarially review MAT-013 (thin-passage restraint check)

Same loop as Task 5 for `MAT-013` (5:1-2, the Sermon-on-the-Mount setup). This passage validates the coverage-restraint principle: it supports D1 (crowds, disciples, mountain), D2 (saw crowds → went up → sat → disciples came → opened his mouth → taught), and D6, but **not** D5/D7/D8 in any answerable way. Under-covering here is correct.

**Files:**
- Create (scratchpad): `<scratchpad>/gen/reviewed_MAT-013.json`
- Append: `TUNING_LOG`; possibly modify `content_bank/author/*` if a new systemic defect appears.

**Interfaces:**
- Consumes: same as Task 5, for `MAT-013`.
- Produces: reviewed items for MAT-013 at `<scratchpad>/gen/reviewed_MAT-013.json`.

- [ ] **Step 1: Build pack** — `python3 -m content_bank.author.build_draft_prompt MAT-013 --out <scratchpad>/gen/pack_MAT-013.md`
- [ ] **Step 2: Draft** — cover only D1/D2/D6 (and a memory-lite / narration if the two verses support it); include a D1 `pre_reading_quest` ("who is on the mountain?") at child/adult tiers and a D1/D2 `question`. Do NOT force D5/D7/D8. Write `<scratchpad>/gen/draft_MAT-013.json`.
- [ ] **Step 3: Validate structure** — same one-liner as Task 5 Step 3, on `draft_MAT-013.json`; expect every line `[]`.
- [ ] **Step 4: Adversarially review** — `REVIEWER_PROMPT` with MAT-013 text + drafts; ≥2 concurrent reviewers. A reviewer flagging "missing D7/D8" is NOT a defect here — record that the restraint held.
- [ ] **Step 5: Triage** — item vs machinery, as Task 5 Step 5.
- [ ] **Step 6: Re-review until clean; stamp `reviewed` + provenance**; write `<scratchpad>/gen/reviewed_MAT-013.json`.
- [ ] **Step 7: Commit** machinery/log changes:
```bash
git add docs/superpowers/notes/2026-07-18-content-tuning-log.md content_bank/author/ content_bank/tests/
git commit -m "content_bank: MAT-013 generated + reviewed; coverage-restraint holds"
```

---

### Task 7: Generate + adversarially review MAT-014 (Beatitudes, flagship)

Same loop for `MAT-014` (5:3-12). The richest passage — expect the fullest dimension coverage (D1 blessed-are groups, D2 the eight in order + the "they/you" shift in 11-12, D3 "blessed"/"kingdom of heaven", D4 a Beatitude memory verse, D5 OT echoes named, D6, D7 who Jesus calls blessed vs the world, D8). Multiple questions, an `activity` + `pre_reader` variant, quests at child/youth/adult.

**Files:**
- Create (scratchpad): `<scratchpad>/gen/reviewed_MAT-014.json`
- Append: `TUNING_LOG`; possibly modify `content_bank/author/*`.

**Interfaces:**
- Consumes: same as Task 5, for `MAT-014`.
- Produces: reviewed items for MAT-014 at `<scratchpad>/gen/reviewed_MAT-014.json`.

- [ ] **Step 1: Build pack** — `python3 -m content_bank.author.build_draft_prompt MAT-014 --out <scratchpad>/gen/pack_MAT-014.md`
- [ ] **Step 2: Draft** the full supported coverage (above), across tiers/difficulties. D5 items must name the OT text (e.g. Ps 37:11 "inherit the earth"). Write `<scratchpad>/gen/draft_MAT-014.json`.
- [ ] **Step 3: Validate structure** — one-liner on `draft_MAT-014.json`; expect `[]`.
- [ ] **Step 4: Adversarially review** — `REVIEWER_PROMPT` with MAT-014 text + drafts; ≥2 concurrent reviewers.
- [ ] **Step 5: Triage** — item vs machinery.
- [ ] **Step 6: Re-review until clean; stamp `reviewed` + provenance**; write `<scratchpad>/gen/reviewed_MAT-014.json`.
- [ ] **Step 7: Commit** machinery/log changes:
```bash
git add docs/superpowers/notes/2026-07-18-content-tuning-log.md content_bank/author/ content_bank/tests/
git commit -m "content_bank: MAT-014 Beatitudes generated + reviewed"
```

---

### Task 8: Generate + adversarially review MAT-015 (Salt & Light)

Same loop for `MAT-015` (5:13-16): D3 salt/light imagery, D7 what the light is for (v16), D4 the v16 memory verse, D8 observable "let your light shine", D6, D1/D2 as supported.

**Files:**
- Create (scratchpad): `<scratchpad>/gen/reviewed_MAT-015.json`
- Append: `TUNING_LOG`; possibly modify `content_bank/author/*`.

**Interfaces:**
- Consumes: same as Task 5, for `MAT-015`.
- Produces: reviewed items for MAT-015 at `<scratchpad>/gen/reviewed_MAT-015.json`.

- [ ] **Step 1: Build pack** — `python3 -m content_bank.author.build_draft_prompt MAT-015 --out <scratchpad>/gen/pack_MAT-015.md`
- [ ] **Step 2: Draft** the supported coverage across tiers; write `<scratchpad>/gen/draft_MAT-015.json`.
- [ ] **Step 3: Validate structure** — one-liner on `draft_MAT-015.json`; expect `[]`.
- [ ] **Step 4: Adversarially review** — `REVIEWER_PROMPT` with MAT-015 text + drafts; ≥2 concurrent reviewers.
- [ ] **Step 5: Triage** — item vs machinery.
- [ ] **Step 6: Re-review until clean; stamp `reviewed` + provenance**; write `<scratchpad>/gen/reviewed_MAT-015.json`.
- [ ] **Step 7: Commit** machinery/log changes:
```bash
git add docs/superpowers/notes/2026-07-18-content-tuning-log.md content_bank/author/ content_bank/tests/
git commit -m "content_bank: MAT-015 Salt and Light generated + reviewed"
```

---

### Task 9: Assemble the store; validate; prove the gate

**Files:**
- Modify: `content_bank/store/mat.json` (replace the 25 seed items with the assembled reviewed items)
- Test: `content_bank/tests/test_store_matthew.py` (extend)

**Interfaces:**
- Consumes: `reviewed_MAT-009/013/014/015.json` from scratchpad; `validate.validate_store`, `content.get_content`.
- Produces: a store whose only items are the four pericopes' reviewed items; `validate_store("MAT")["errors"] == []`.

- [ ] **Step 1: Assemble the store**

Concatenate the four scratchpad arrays into `{"book":"MAT","items":[...]}` and write `content_bank/store/mat.json`. Every item currently `review_status:"reviewed"` (Task 11 flips to published). Verify ids are globally unique.

- [ ] **Step 2: Rewrite the seed-dependent store tests**

`content_bank/tests/test_store_matthew.py` is entirely seed-specific (all five methods assert the 25 seed items / deleted ids like `mt4-q-who-tempted`, `mt5a-*`, and `test_expected_counts` asserts 25/24/1). Replace the whole `TestMatthewStore` body with:

```python
class TestMatthewStore(unittest.TestCase):
    def test_store_validates_clean(self):
        self.assertEqual(validate.validate_store("MAT")["errors"], [])

    def test_only_scoped_pericopes_present(self):
        store = content.load_book_store("MAT")
        passages = {i["passage"] for i in store["items"]}
        self.assertEqual(passages, {"MAT-009", "MAT-013", "MAT-014", "MAT-015"})

    def test_every_item_reviewed_before_confirmation(self):
        # after assembly (Task 9) nothing is published yet -> product serves nothing
        self.assertEqual(content.get_content("MAT", mode="product"), [])
        self.assertTrue(content.get_content("MAT", mode="author"))
```
(`validate` and `content` are already imported at the top of the file.)

- [ ] **Step 3: Run test to verify state**

Run: `python3 -m unittest content_bank.tests.test_store_matthew -v`
Expected: the three tests PASS.

- [ ] **Step 4: Fix `test_prototype_bank.py` (seed ids + the zh test)**

`content_bank/tests/test_prototype_bank.py::TestLoadBank` references deleted seed ids (`mt5a-q-who-blessed`, `mt5a-quest-tally`, `mt5a-mv-peacemakers`, `mt5a-q-draft-kingdom`) and `test_zh_bank_uses_translation` requires a `zh` item — impossible under English-only. `TestDisplayRef` is store-independent; leave it. Rewrite `TestLoadBank` to assert *shape*, not specific ids:

```python
class TestLoadBank(unittest.TestCase):
    def setUp(self):
        self.bank = pb.load_bank("MAT", lang="en")

    def test_pericopes_include_corpus_ids_with_display_refs(self):
        by_id = {p["id"]: p for p in self.bank["pericopes"]}
        self.assertEqual(by_id["MAT-014"]["ref"], "Matthew 5:3–12")
        self.assertEqual(by_id["MAT-014"]["title"], "The Beatitudes")

    def test_items_flattened_to_body_and_product_gated(self):
        # after publish (Task 11) product mode serves items with a flat 'body'
        self.assertTrue(self.bank["items"])
        item = self.bank["items"][0]
        self.assertIsInstance(item["body"], str)
        self.assertNotIn("text", item)
        self.assertNotIn("draft", {i["review_status"] for i in self.bank["items"]})
```
(Delete `test_quest_category_flattened` and `test_zh_bank_uses_translation`, or re-point the former at a known published quest id once the store exists. `test_content.py` uses temp fixtures and needs no change.)

- [ ] **Step 5: Run the full content_bank suite**

Run: `python3 -m unittest discover -s content_bank/tests -v`
Expected: PASS. Note: `test_prototype_bank`'s new `test_items_flattened_to_body_and_product_gated` asserts a non-empty product bank, so it only passes after Task 11 publishes — run it green after Task 11 (flagged in the ordering dependency below).

- [ ] **Step 6: Commit**

```bash
git add content_bank/store/mat.json content_bank/tests/
git commit -m "content_bank: assemble MAT store (reviewed), replace seed; gate proven"
```

---

### Task 10: Wire MAT-013 into the sequence; resolve the demo passage

**Files:**
- Modify: `prototype/family.json`
- Test: `prototype/test_selector.py` (extend); manual `generate_kit.py` run

**Interfaces:**
- Consumes: the store (Task 9, temporarily made servable — see Step 1 note), `selector.build_kit`.
- Produces: `reading_sequence == ["MAT-009","MAT-013","MAT-014","MAT-015"]`; a coherent demo kit.

- [ ] **Step 1: Update the reading sequence and resolve the demo passage**

Edit `prototype/family.json`: set `"reading_sequence": ["MAT-009", "MAT-013", "MAT-014", "MAT-015"]`. Because `next_passage` returns the first *unstudied* pericope and only MAT-009 is studied, the demo kit would feature the thin MAT-013 setup. To keep the flagship demo on the Beatitudes, add a second studied session for MAT-013 (minimal evidence) so `next_passage` returns MAT-014:

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

Add to `prototype/test_selector.py` (match the file's existing bank-loading fixture; it builds the bank via `prototype_bank.load_bank` or a fixture — follow the pattern already there):

```python
    def test_reading_sequence_includes_mat013(self):
        import json, pathlib
        fam = json.loads((pathlib.Path(__file__).parent / "family.json").read_text())
        self.assertIn("MAT-013", fam["reading_sequence"])
        self.assertEqual(fam["reading_sequence"].index("MAT-013"),
                         fam["reading_sequence"].index("MAT-014") - 1)
```

- [ ] **Step 3: Run test to verify it passes**

Run: `cd prototype && python3 -m unittest test_selector -v`
Expected: PASS. If existing selector tests break because the store now serves nothing in product mode (Task 9 left items `reviewed`), temporarily publish for local verification: run the whole of Task 11 first, OR point the test at a fixture bank. Prefer running Task 11, then returning here — note this ordering dependency.

- [ ] **Step 4: Verify the kit end-to-end** (after Task 11 has published)

Run: `cd prototype && python3 generate_kit.py -o <scratchpad>/gen/kit_demo.md`
Expected: a kit for MAT-014 (Beatitudes) with review questions from MAT-009/013, discussion questions across dimensions, an activity + younger variant, quests per member, a memory verse, a narration prompt. Read it; confirm it is coherent and every referenced item exists.

- [ ] **Step 5: Commit**

```bash
git add prototype/family.json prototype/test_selector.py
git commit -m "prototype: add MAT-013 to reading sequence; keep Beatitudes as demo"
```

---

### Task 11: Human confirmation digest → publish

**Files:**
- Create: `<scratchpad>/gen/confirmation_digest.md`
- Modify: `content_bank/store/mat.json` (flip `reviewed` → `published`; add `confirmed_by`)

**Interfaces:**
- Consumes: the assembled store (Task 9).
- Produces: a published store; `get_content("MAT", mode="product")` non-empty.

- [ ] **Step 1: Build the confirmation digest**

Generate `<scratchpad>/gen/confirmation_digest.md`: one line per item — `id · passage · dimension · type · age_tier · difficulty · the en text` — grouped by pericope, with the per-pericope dimension coverage and the count. This is what the human skims (respects "the leader is not a data-entry clerk").

- [ ] **Step 2: Present the digest and STOP for human approval**

Present the digest to the user. Ask for approval to publish, or a list of items to hold/edit. **Do not proceed without an explicit answer.** Apply any edits the human requests (re-review edited items via Step 4 of the relevant generation task if substance changed).

- [ ] **Step 3: Stamp published**

For every approved item in `content_bank/store/mat.json`: set `review_status:"published"` and add `"confirmed_by":"kyhhdm"` to `provenance`. Leave any held item as `reviewed`.

- [ ] **Step 4: Prove the gate serves published content**

Run:
```bash
python3 -c "import sys; sys.path.insert(0,'.'); from content_bank.lib import content; \
print('published:', len(content.get_content('MAT', mode='product')))"
```
Expected: a positive count equal to the approved items.

- [ ] **Step 5: Update the gate test and commit**

Update `content_bank/tests/test_store_matthew.py::test_gate_hides_reviewed_from_product` (from Task 9) to reflect that product now serves the published items (or add `test_gate_serves_published`). Run `python3 -m unittest discover -s content_bank/tests -v` → PASS.

```bash
git add content_bank/store/mat.json content_bank/tests/test_store_matthew.py
git commit -m "content_bank: publish confirmed MAT items (human gate)"
```

---

### Task 12: Provenance, tuning writeup, final verification

**Files:**
- Modify: `content_bank/PROVENANCE.md`
- Finalize: `docs/superpowers/notes/2026-07-18-content-tuning-log.md` (the deliverable writeup)

**Interfaces:**
- Consumes: everything above.
- Produces: recorded provenance + a quality/tuning writeup; all three suites green.

- [ ] **Step 1: Record provenance**

Append to `content_bank/PROVENANCE.md`: this authoring cycle — pericopes MAT-009/013/014/015, drafted_by claude, adversarially reviewed, human-confirmed by kyhhdm on 2026-07-18, English-only, seed replaced.

- [ ] **Step 2: Finalize the tuning writeup**

Complete `docs/superpowers/notes/2026-07-18-content-tuning-log.md`: (a) defects found by axis, (b) the machinery change each recurring defect motivated (file + what changed + why), (c) residual known limitations (English-only; zh-conformity deferred; thin-passage coverage; any axis the agents were weak at).

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
- Rubric (7 axes) → Task 1. Checklist mirrors it → Task 2. Dimension guidance → Task 3. Drafting-pack tuning (answerability, coverage, per-type, evidence) → Task 4.
- Generate + adversarial review, per pericope, with triage/tuning → Tasks 5-8 (009/013/014/015). Coverage-restraint principle exercised explicitly in Task 6.
- Regenerate-all-replace-seed → Task 9. Store validation + gate proof → Task 9.
- MAT-013 into sequence + demo-passage resolution → Task 10.
- `reviewed` → confirmation digest → `published` human gate → Task 11.
- Provenance model + tuning writeup + full verification → Task 12. English-only, stdlib-only, scope limits → Global Constraints.

**Placeholder scan:** No TBD/TODO. Generation tasks (5-8) are inherently generative, not code-TDD; each still has a concrete gate (structural `validate_item` + adversarial pass) and concrete commands. `<scratchpad>` is a real path supplied at execution time, not a placeholder.

**Type consistency:** `rubric.build()`/`rubric.AXES` defined in Task 1, consumed in Tasks 2 and 4. `dimensions.TEMPLATES` (keys == `schema.DIMENSIONS`) preserved in Task 3, invariant test kept green. `build_draft_prompt.build(pericope_id, book)` signature unchanged (Task 4). `validate.validate_store` / `content.get_content` used as defined in the existing infrastructure. Provenance keys (`drafted_by`, `reviewed_by`, `reviewed_date`, `guardrail`, `confirmed_by`) consistent across Tasks 5-8, 11, and satisfy `schema.validate_item`'s not-draft requirements.

**Known ordering dependency (flagged in-plan):** Task 10's end-to-end kit verification and any selector test that reads the live store depend on Task 11 having published. Run Task 11 before Task 10 Step 4. Left explicit rather than reordering, because MAT-013 must be in the sequence (Task 10 Step 1) before a coherent demo can be judged.
