# Content-bank prototype content: generate, judge, tune — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce the first harness-generated, adversarially-reviewed English content bank for the prototype's four Matthew pericopes via a two-stage, passage-first process — distill the corpus lampposts into a compact reviewed theological brief, then draft items from passage + brief — and tune the authoring machinery from the defects review surfaces.

**Architecture:** Per pericope, two stages. **Stage 1:** `build_brief_prompt.py` assembles a distillation pack (passage + full WCF-1 + commentary + cross-references + confessional proof-text hits); a drafter produces a ~250-word brief; adversarial *fidelity* reviewers verify it faithfully distils the lampposts and keeps the passage primary; the brief is committed to `author/briefs/`. **Stage 2:** `build_draft_prompt.py` carries the foregrounded passage + the committed brief + a compact WCF-1 guardrail; a drafter produces items; adversarial *quality* reviewers score them on the seven-axis rubric with the brief as ground truth; defects triage into fix-item or fix-machinery. Passing items reach `review_status: "reviewed"`; a human confirmation digest gates the flip to `"published"`.

**Tech Stack:** Python 3 standard library only (no third-party packages). `unittest`. The existing `content_bank/` infrastructure and `corpus/` canon are dependencies; `corpus_bridge` gains read-only accessors this cycle.

## Global Constraints

- **Stdlib only.** No third-party packages, no network, no live API calls anywhere in `content_bank/` or `corpus/`. The drafting harness stays offline.
- **English-only this cycle.** Every item carries `text: {"en": "..."}`. No `zh`. Briefs are English.
- **Do not modify:** `content_bank/lib/schema.py`, `content_bank/lib/content.py`, `content_bank/lib/validate.py`, `content_bank/lib/prototype_bank.py`, `prototype/selector.py`, anything under `corpus/` (read-only). `corpus_bridge.py` **is** modified — additively (three new accessors), existing surface untouched.
- **Item types in scope:** `question`, `activity`, `pre_reading_quest`, `memory_verse`, `narration_prompt`. Not `vocab_list` / `key_facts`.
- **Pericopes in scope:** `MAT-009`, `MAT-013`, `MAT-014`, `MAT-015`.
- **Two-stage authoring.** No items are drafted for a pericope until its brief is committed to `content_bank/author/briefs/<pericope>.md` and has passed fidelity review. Draft items are grounded in the brief, not raw lampposts.
- **Passage-first proportion.** The Stage-2 draft pack foregrounds the passage and carries a **compact** WCF-1 guardrail + the brief — never the full ~11k words of lampposts. Full WCF-1 + commentary appear only in the Stage-1 brief pack.
- **Provenance dates:** use `"2026-07-18"` for `reviewed_date`.
- **Answerable-from-this-pericope rule:** every non-D5 item must be answerable from its own pericope's verses. D5 (Connections) may name only a cross-reference that appears in the brief.
- **Coverage restraint:** cover every dimension the passage *genuinely supports*, at the tiers the selector needs — no more. A pericope with no confessional proof-text hit (MAT-013) simply omits the doctrinal anchor — do not invent one.
- **Proof-text safeguard:** a confessional proof-text link means "the divines grounded a doctrine partly here," NOT "this passage is a treatise on that doctrine." The brief uses only the part of a citation that fits the passage's emphasis (verified case: WLC Q172 on the Beatitudes is a Lord's-Supper Q&A — take only its reading of "poor in spirit/mourn").
- **Lampposts are authoring-time grounding only.** Commentary (JFB/MHC), the standards (WCF/WLC/WSC), and cross-references inform the brief, drafter, and reviewers; they are never copied into shipped items (verbatim quotations come from the gated Bible text). No new license surface enters the store.
- **Vocabularies single-sourced** in `schema.py` and `dimensions.py`; `set(dimensions.TEMPLATES) == schema.DIMENSIONS` must stay green.
- **Tests:** `python3 -m unittest discover -s content_bank/tests -v`, `cd prototype && python3 -m unittest test_selector -v`, and `python3 -m unittest discover -s corpus/tests -v` must all pass at the end.

## Corpus asset shapes (verified)

- **Commentary:** `canon/lampposts/{mhc,jfb}/<book>.json` = `{work, book, license, role, blocks: [{range, text}]}`. **MHC per-pericope**, **JFB per-verse**; match by **range overlap**, empty list when nothing overlaps (all four in-scope pericopes have commentary).
- **Cross-references:** `canon/structure/crossrefs.json` = `{role, refs: [{from, to, weight, sources}]}`, ~344k. Filter by `from` in range; rank by `weight` desc; cap.
- **Confessional standards:** `wcf.json` = `{chapters:[{n,title,sections:[{n,text,proof_texts:[...]}]}]}`; `wlc.json`/`wsc.json` = `{questions:[{n,q,a,proof_texts:[...]}]}`. `proof_texts` entries are Scripture refs. Reverse-lookup by proof-text overlap. Verified hit counts: MAT-009 → WCF 4 / WLC 7; MAT-013 → 0; MAT-014 → WCF 19.6 + WLC Q172; MAT-015 → WCF 16.2.
- **Range format:** `BOOK.CH.V` or `BOOK.CH.V-V`. A minimal parser (book, chapter, start, end) suffices; a `from`/proof-text may be a range — use its start verse for membership.

## Shared assets (defined once; referenced by the generation tasks)

**`BRIEF_FIDELITY_REVIEWER`** — Stage-1 reviewer (Agent tool, `subagent_type: general-purpose`, ≥2 concurrent):

```
You are an adversarial fidelity reviewer for a theological brief that will be the
base for family Bible-study content. Try to BREAK it — assume it drifts until proven faithful.

PASSAGE: <id> — <book> (<range>)
PASSAGE TEXT: <passage_text>
LAMPPOSTS THE BRIEF CLAIMS TO DISTILL:
  WCF ch.1 (full): <wcf1>
  COMMENTARY (MHC/JFB): <commentary_blocks>
  CROSS-REFERENCES (ranked): <crossrefs>
  CONFESSIONAL/CATECHISM (proof-text hits, with text): <confessional_refs>

BRIEF UNDER REVIEW:
<brief>

Report every failure:
- FAITHFUL: each claim is supported by the passage or a lamppost above; flag
  anything unsupported or invented (private novelty).
- PASSAGE-PRIMARY: the brief leads with and is governed by THIS passage's own
  emphasis; doctrine and cross-refs are supporting, not driving.
- PROOF-TEXT DISCIPLINE: any confessional citation is used only for the part that
  fits this passage; off-agenda topics are set aside, not imported.
- WCF-1 METHOD: treats Scripture as inspired/infallible/sufficient; Scripture
  interprets Scripture; no hedging.
- LENGTH: <= ~300 words, compact, in the four-part shape.
Return ONLY JSON: {"pass": <bool>, "defects":[{"kind":"...",
  "severity":"critical|major|minor","why":"...","fix":"..."}]}
```

**`ITEM_QUALITY_REVIEWER`** — Stage-2 reviewer (Agent tool, `general-purpose`, ≥2 concurrent):

```
You are an adversarial content reviewer for a Reformed family Bible-study tool.
BREAK the draft items — assume each is flawed until it survives every check.

PASSAGE: <id> — <book> (<range>)
PASSAGE TEXT (the ONLY text a non-D5 item may require to be answerable):
<passage_text>
THEOLOGICAL BRIEF (the reviewed base; ground truth for accuracy & doctrine):
<brief>
(The brief's cross-references are the ONLY valid targets for a D5 item.)

RUBRIC — score every item on all seven axes:
1. Confessional conformity (WCF-1): affirms, never hedges, Scripture's
   inspiration/infallibility/inerrancy/sufficiency/clarity; Scripture interprets
   Scripture; meaning from the text, not speculation.
2. Accuracy & answerability: correct vs the passage and the brief; names/places/
   sequence/quotations match; ANSWERABLE FROM THE PASSAGE TEXT ALONE (a D5 item
   may reach out, but only to a cross-reference named in the brief).
3. Evidence never judgment: elicits observable behavior; never assesses faith,
   character, or spiritual state.
4. Age fitness: language + difficulty match age_tier; activities doable on paper.
5. Dimension fit: genuinely exercises its tagged dimension.
6. Worship not academy: serves fluency/the heart; nothing during-session.
7. Pedagogical strength: a good prompt — open where it should be, not leading,
   not trivially yes/no unless a deliberate warm-up.

DRAFT ITEMS (JSON array):
<items_json>

Return ONLY a JSON array, one object per item, same order:
[{"id":"...","verdicts":{"1":"pass|fail",...,"7":"pass|fail"},
  "defects":[{"axis":<n>,"severity":"critical|major|minor","why":"...",
              "fix":"item|machinery","suggestion":"..."}]}]
An item PASSES only if every axis is "pass". Cite the passage/brief in "why".
Mark fix="machinery" when a defect would recur because the brief-builder, the
draft pack, the dimension guidance, or the checklist never told the drafter otherwise.
```

**Working files:** brief drafts, item drafts, and reviewer output live under `<scratchpad>/gen/`. **Committed** outputs: the briefs (`author/briefs/*.md`), the store, the tuning writeup, and machinery/code changes.

**`TUNING_LOG`** — `docs/superpowers/notes/2026-07-18-content-tuning-log.md`, appended as defects are triaged (each machinery fix + the defect that motivated it). Becomes the deliverable writeup (Task 14).

---

### Task 1: Rubric module (single source for the seven axes)

**Files:** Create `content_bank/author/rubric.py`; Test `content_bank/tests/test_author.py`.

**Interfaces:** Produces `rubric.build() -> str` and `rubric.AXES: tuple[str, ...]` (seven ordered titles).

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
Substance is judged (by agent then human), never keyword-linted."""

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
   interprets Scripture (WCF 1.9); no private novelty. Meaning drawn from the
   text, not speculation.
2. Accuracy & answerability. Every factual claim is correct against the passage
   and the theological brief; names, places, sequence, and quotations match. The
   item is answerable from THIS pericope's own verses. A D5 (Connections) item is
   the sole exception and must name a cross-reference from the brief.
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

**Files:** Modify `content_bank/author/review_checklist.py`; Test `content_bank/tests/test_author.py` (replace `TestReviewChecklist`).

**Interfaces:** Consumes `rubric.build()`. Produces `review_checklist.build(guardrail="WCF-1") -> str` covering all seven axes.

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
Expected: FAIL — new axis tokens absent.

- [ ] **Step 3: Write minimal implementation**

Rewrite `content_bank/author/review_checklist.py`:

```python
"""Print the draft -> reviewed -> published review checklist a human fills in.
Mirrors the seven-axis rubric (author/rubric.py)."""
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
- [ ] Scripture interprets Scripture (WCF 1.9); meaning from the text.

## Accuracy & answerability
- [ ] Every factual claim is correct against the passage and the brief.
- [ ] Names, places, sequence, and quotations match the text.
- [ ] Answerable from THIS pericope's verses (D5 may name a brief cross-reference).

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

**Files:** Modify `content_bank/author/dimensions.py`; Test `content_bank/tests/test_author.py` (add `TestDimensions`).

**Interfaces:** `dimensions.TEMPLATES: dict[str,str]` — keys unchanged (== `schema.DIMENSIONS`); values expanded.

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
Source of truth for meaning remains docs/design-kit_generator.md Part 1."""

TEMPLATES = {
    "D1": "People & Places — who is present and where events happen. Good items "
          "name people/roles/locations the passage itself states. Avoid people "
          "not in this pericope's verses.",
    "D2": "Event Sequence — the order and flow of what happens. Good items ask "
          "for first/next/last, cause-then-effect, or reordering — all "
          "recoverable from this passage. Avoid sequence spanning other pericopes.",
    "D3": "Vocabulary — the Bible's own key terms and repeated phrases. Good items "
          "point at a word/phrase the passage uses and ask its sense here (the "
          "brief may inform it). Avoid importing outside definitions as the answer.",
    "D4": "Memory — memory verses, key phrases, recall. Good items quote or cue a "
          "line from THIS passage. Memory verses: one or two verses, verbatim.",
    "D5": "Connections — links to other passages and patterns. The one dimension "
          "allowed to reach outside this pericope; a good item NAMES the other "
          "text, drawn from the brief's cross-references.",
    "D6": "Questions — the learner's own question-asking, prompted here. Good "
          "items invite the learner's own wondering; they don't smuggle in the "
          "leader's answer.",
    "D7": "Interpretation — what the text says, then why. Good items anchor to "
          "what the passage states before asking why; meaning from the text (the "
          "brief may confirm), not speculation. Avoid doctrine the passage lacks.",
    "D8": "Application — bringing the passage into life, observably. Good items "
          "ask for a concrete, doable response; never assess faith or character, "
          "only observable action.",
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest content_bank.tests.test_author -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/dimensions.py content_bank/tests/test_author.py
git commit -m "content_bank: expand per-dimension drafting guidance"
```

---

### Task 4: corpus_bridge accessors — commentary, cross-references, confessional refs

**Files:** Modify `content_bank/lib/corpus_bridge.py` (additive); Test `content_bank/tests/test_corpus_bridge.py`.

**Interfaces:** Produces
- `commentary(range_str, book="MAT", works=("mhc","jfb")) -> dict[str, list[dict]]` — per work, blocks (`{"range","text"}`) overlapping `range_str`; `[]` when none.
- `crossrefs(range_str, limit=15) -> list[dict]` — refs whose `from` is in `range_str`, sorted by `weight` desc then `to`, capped.
- `confessional_refs(range_str) -> dict` — `{"wcf":[{ref,title,text,via}], "wlc":[{ref,q,a,via}], "wsc":[...]}` for sections/Q&As whose `proof_texts` overlap.
- Helpers `_parse_range`, `_overlaps`.

- [ ] **Step 1: Write the failing test**

Add to `content_bank/tests/test_corpus_bridge.py`:

```python
class TestCommentary(unittest.TestCase):
    def test_exact_block_returned(self):
        from content_bank.lib import corpus_bridge
        c = corpus_bridge.commentary("MAT.4.1-11")
        self.assertTrue(c["mhc"] and "range" in c["mhc"][0] and "text" in c["mhc"][0])

    def test_per_verse_jfb_overlaps_pericope(self):
        from content_bank.lib import corpus_bridge
        self.assertTrue(corpus_bridge.commentary("MAT.5.1-2")["jfb"])  # e.g. MAT.5.2

    def test_no_overlap_is_graceful_empty(self):
        from content_bank.lib import corpus_bridge
        c = corpus_bridge.commentary("MAT.28.99-99")
        self.assertEqual(c["mhc"], [])
        self.assertEqual(c["jfb"], [])


class TestCrossrefs(unittest.TestCase):
    def test_refs_in_range_ranked_and_capped(self):
        from content_bank.lib import corpus_bridge
        refs = corpus_bridge.crossrefs("MAT.5.3-12", limit=5)
        self.assertTrue(refs and len(refs) <= 5)
        weights = [r["weight"] for r in refs]
        self.assertEqual(weights, sorted(weights, reverse=True))
        self.assertTrue(all(r["from"].startswith("MAT.5.") for r in refs))

    def test_empty_range_is_graceful(self):
        from content_bank.lib import corpus_bridge
        self.assertEqual(corpus_bridge.crossrefs("MAT.999.1-2"), [])


class TestConfessionalRefs(unittest.TestCase):
    def test_beatitudes_hits_wcf_and_wlc(self):
        from content_bank.lib import corpus_bridge
        c = corpus_bridge.confessional_refs("MAT.5.3-12")
        refs = [h["ref"] for h in c["wcf"]] + [h["ref"] for h in c["wlc"]]
        self.assertIn("WCF 19.6", refs)
        self.assertIn("WLC Q172", refs)
        wcf = next(h for h in c["wcf"] if h["ref"] == "WCF 19.6")
        self.assertIn("text", wcf)
        self.assertIn("via", wcf)

    def test_setup_pericope_has_no_hits(self):
        from content_bank.lib import corpus_bridge
        c = corpus_bridge.confessional_refs("MAT.5.1-2")
        self.assertEqual(c["wcf"] + c["wlc"] + c["wsc"], [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest content_bank.tests.test_corpus_bridge -v`
Expected: FAIL — `AttributeError: ... has no attribute 'commentary'`.

- [ ] **Step 3: Write minimal implementation**

Append to `content_bank/lib/corpus_bridge.py`:

```python
def _parse_range(range_str):
    """'MAT.5.3-12' or 'MAT.5.3' -> ('MAT', 5, 3, 12)."""
    book, chapter, verses = range_str.split(".", 2)
    v1, v2 = (verses.split("-", 1) if "-" in verses else (verses, verses))
    return book, int(chapter), int(v1), int(v2)


def _overlaps(a, b):
    return a[0] == b[0] and a[1] == b[1] and a[2] <= b[3] and b[2] <= a[3]


def _safe_overlaps(target, ref):
    try:
        return _overlaps(target, _parse_range(ref))
    except (ValueError, AttributeError):
        return False


def commentary(range_str, book="MAT", works=("mhc", "jfb")):
    target = _parse_range(range_str)
    out = {}
    for work in works:
        data = _load(f"canon/lampposts/{work}/{book.lower()}.json")
        blocks = data.get("blocks", []) if isinstance(data, dict) else []
        out[work] = [b for b in blocks if _safe_overlaps(target, b["range"])]
    return out


def crossrefs(range_str, limit=15):
    target = _parse_range(range_str)
    data = _load("canon/structure/crossrefs.json")
    refs = data.get("refs", []) if isinstance(data, dict) else data
    hits = [r for r in refs if _safe_overlaps(target, r["from"])]
    hits.sort(key=lambda r: (-r.get("weight", 0), r.get("to", "")))
    return hits[:limit]


def confessional_refs(range_str):
    target = _parse_range(range_str)

    def _via(proof_texts):
        for pt in proof_texts:
            if _safe_overlaps(target, pt):
                return pt
        return None

    out = {"wcf": [], "wlc": [], "wsc": []}
    wcf = _load("canon/lampposts/wcf.json")
    for ch in wcf["chapters"]:
        for s in ch["sections"]:
            via = _via(s.get("proof_texts", []))
            if via:
                out["wcf"].append({"ref": f"WCF {ch['n']}.{s['n']}",
                                   "title": ch["title"], "text": s["text"], "via": via})
    for key, fname in (("wlc", "wlc.json"), ("wsc", "wsc.json")):
        cat = _load(f"canon/lampposts/{fname}")
        for q in cat["questions"]:
            via = _via(q.get("proof_texts", []))
            if via:
                out[key].append({"ref": f"{key.upper()} Q{q['n']}",
                                 "q": q["q"], "a": q["a"], "via": via})
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest content_bank.tests.test_corpus_bridge -v`
Expected: PASS (verified against the corpus: MAT-014 → WCF 19.6 + WLC Q172; MAT-013 → none).

- [ ] **Step 5: Commit**

```bash
git add content_bank/lib/corpus_bridge.py content_bank/tests/test_corpus_bridge.py
git commit -m "content_bank: corpus_bridge commentary + crossref + confessional accessors"
```

---

### Task 5: Stage-1 brief pack (`build_brief_prompt.py`)

**Files:** Create `content_bank/author/build_brief_prompt.py`; Test `content_bank/tests/test_author.py` (add `TestBuildBriefPrompt`).

**Interfaces:** Consumes `corpus_bridge.{pericopes,book_name,passage_text,wcf_chapter1_text,commentary,crossrefs,confessional_refs}`. Produces `build_brief_prompt.build(pericope_id, book="MAT") -> str` and a `main()` CLI with `--out`.

- [ ] **Step 1: Write the failing test**

Add to `content_bank/tests/test_author.py`:

```python
class TestBuildBriefPrompt(unittest.TestCase):
    def setUp(self):
        from content_bank.author import build_brief_prompt
        self.pack = build_brief_prompt.build("MAT-014", book="MAT")

    def test_includes_passage_and_full_wcf1(self):
        self.assertIn("blessed", self.pack.lower())    # passage text
        self.assertIn("1.1", self.pack)                # full WCF ch.1 sections

    def test_includes_commentary_and_crossrefs(self):
        p = self.pack.lower()
        self.assertIn("commentary", p)
        self.assertIn("cross-reference", p)

    def test_includes_confessional_hits(self):
        self.assertIn("WCF 19.6", self.pack)
        self.assertIn("WLC Q172", self.pack)

    def test_states_brief_shape_and_safeguard(self):
        p = self.pack.lower()
        self.assertIn("~250", self.pack)               # length target
        self.assertIn("emphasis", p)                   # passage-primary shape
        self.assertIn("proof-text", p)                 # safeguard

    def test_setup_pericope_notes_no_confessional(self):
        from content_bank.author import build_brief_prompt
        pack = build_brief_prompt.build("MAT-013", book="MAT")
        self.assertIn("No confessional", pack)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest content_bank.tests.test_author.TestBuildBriefPrompt -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

Create `content_bank/author/build_brief_prompt.py`:

```python
"""Assemble the Stage-1 distillation pack for one pericope.

Offline: prints a self-contained pack a human/Claude runs by hand to produce a
compact theological brief. The brief is fidelity-reviewed and committed to
author/briefs/ before any item is drafted (Stage 2, build_draft_prompt)."""
import argparse

from ..lib import corpus_bridge

_SHAPE = """## Produce the THEOLOGICAL BRIEF

~250 words (hard max 300), in exactly these four parts:

**Passage's own emphasis (primary).** What THIS passage says and stresses, in the
text's own terms. This governs everything else.
**Key terms (from commentary).** A few words/phrases the passage uses, with the
sense the commentary gives them. Ground, don't speculate.
**Doctrinal anchors.** Method: WCF ch.1 — treat the text as inspired, sufficient,
Scripture-interpreting-Scripture. Doctrine: what the cited confessional/catechism
statements say this passage teaches.
**Cross-references.** The vetted links above, each with a one-phrase note.

SAFEGUARD — a proof-text link means "the divines grounded a doctrine partly
here," NOT "this passage is a treatise on that doctrine." Use only the part of a
confessional citation that fits THIS passage's emphasis; set aside off-agenda
topics (e.g. a Lord's-Supper Q&A cited for a phrase about the humble heart
contributes only its reading of that phrase). Add NO doctrine the lampposts do
not support. End with a one-line note of anything set aside as off-agenda."""


def build(pericope_id, book="MAT"):
    peris = {p["id"]: p for p in corpus_bridge.pericopes(book)}
    if pericope_id not in peris:
        raise ValueError(f"{pericope_id} is not a {book} pericope")
    p = peris[pericope_id]
    name = corpus_bridge.book_name(book, "en")
    rng = p["range"]
    parts = [f"# Brief pack — {pericope_id}: {p['title_en']}\n",
             f"Passage: {name} ({rng})\n",
             "## The passage (public-domain text) — the SUBJECT\n",
             corpus_bridge.passage_text(rng) + "\n",
             "## WCF Chapter 1 — the method guardrail (full)\n",
             corpus_bridge.wcf_chapter1_text() + "\n",
             "## Commentary (exegesis — grounding, do not copy verbatim)\n"]
    comm = corpus_bridge.commentary(rng, book)
    if any(comm.values()):
        for work, blocks in comm.items():
            for b in blocks:
                parts.append(f"### {work.upper()} {b['range']}\n{b['text']}\n")
    else:
        parts.append("(No commentary block overlaps this pericope.)\n")
    parts.append("## Cross-references (Scripture interprets Scripture)\n")
    refs = corpus_bridge.crossrefs(rng)
    parts.append("\n".join(f"- {r['from']} -> {r['to']} (weight {r.get('weight')})"
                           for r in refs) if refs else "(none)")
    parts.append("\n## Confessional & catechism references (doctrine, by proof-text)\n")
    conf = corpus_bridge.confessional_refs(rng)
    if conf["wcf"] or conf["wlc"] or conf["wsc"]:
        for h in conf["wcf"]:
            parts.append(f"### {h['ref']} — {h['title']} (cited via {h['via']})\n{h['text']}\n")
        for key in ("wlc", "wsc"):
            for h in conf[key]:
                parts.append(f"### {h['ref']} (cited via {h['via']})\nQ: {h['q']}\nA: {h['a']}\n")
    else:
        parts.append("(No confessional proof-text cites this pericope — omit the "
                     "doctrinal-anchor detail; do not invent one.)\n")
    parts.append("\n" + _SHAPE)
    return "\n".join(parts)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("pericope_id")
    ap.add_argument("--book", default="MAT")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    text = build(args.pericope_id, args.book)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        print(text)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest content_bank.tests.test_author -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/build_brief_prompt.py content_bank/tests/test_author.py
git commit -m "content_bank: Stage-1 brief pack (distills lampposts, passage-first)"
```

---

### Task 6: Stage-2 draft pack (`build_draft_prompt.py`) — passage-first + brief

**Files:** Modify `content_bank/author/build_draft_prompt.py`; Test `content_bank/tests/test_author.py` (rewrite `TestBuildDraftPrompt`).

**Interfaces:** Consumes `rubric.build()`, `dimensions.TEMPLATES`, `corpus_bridge.{pericopes,book_name,passage_text}`, and the committed brief. Produces `build_draft_prompt.build(pericope_id, book="MAT", brief=None) -> str`: if `brief` is None, load `author/briefs/<pericope_lower>.md` (raise `FileNotFoundError` if absent); the pack foregrounds the passage, carries the brief, a compact WCF-1 guardrail, per-dimension guidance, rules, per-type expectations, and the rubric. Full commentary/WCF are NOT in this pack.

- [ ] **Step 1: Write the failing test**

Replace `TestBuildDraftPrompt` in `content_bank/tests/test_author.py` (it no longer builds without a brief):

```python
class TestBuildDraftPrompt(unittest.TestCase):
    def setUp(self):
        self.brief = ("**Passage's own emphasis.** Jesus pronounces blessing...\n"
                      "**Cross-references.** Ps 37:11 — the meek inherit.\n")
        self.prompt = build_draft_prompt.build("MAT-014", book="MAT", brief=self.brief)

    def test_foregrounds_passage_text(self):
        self.assertIn("MAT-014", self.prompt)
        self.assertIn("blessed", self.prompt.lower())          # passage present
        self.assertIn("subject", self.prompt.lower())          # foregrounded label

    def test_carries_the_brief(self):
        self.assertIn("pronounces blessing", self.prompt)      # brief injected

    def test_compact_wcf_guardrail_not_full_chapter(self):
        p = self.prompt.lower()
        self.assertIn("westminster", p)
        self.assertNotIn("1.10", self.prompt)                  # full ch.1 absent
        self.assertLess(len(self.prompt), 6000)                # pack stays lean

    def test_states_rules_types_and_rubric(self):
        p = self.prompt.lower()
        self.assertIn("answerable", p)
        self.assertTrue("genuinely support" in p or "only the dimensions" in p)
        self.assertIn("observable behavior", p)
        self.assertIn("memory_verse", p)
        self.assertIn("pedagog", p)                            # rubric embedded

    def test_all_dimension_templates_present(self):
        for d in dimensions.TEMPLATES:
            self.assertIn(d, self.prompt)

    def test_missing_brief_raises(self):
        with self.assertRaises(FileNotFoundError):
            build_draft_prompt.build("MAT-999-nobrief", book="MAT", brief=None)
```

(Note: `MAT-999-nobrief` is not a pericope, but the brief lookup happens first and raises `FileNotFoundError`; if implementation validates the pericope before the brief, use a real id whose brief file is absent, e.g. `MAT-015`, ensuring `author/briefs/mat-015.md` does not exist at test time.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest content_bank.tests.test_author.TestBuildDraftPrompt -v`
Expected: FAIL — current `build()` has no `brief` param and injects full WCF/commentary.

- [ ] **Step 3: Write minimal implementation**

Rewrite `content_bank/author/build_draft_prompt.py`:

```python
"""Assemble the Stage-2 drafting pack for one pericope.

Passage-first: the pericope's verses are the subject; the theological base is the
committed brief (author/briefs/<pericope>.md, produced by Stage 1). The full
lampposts are NOT here — only a compact WCF-1 guardrail. Offline, no API."""
import argparse
import pathlib

from ..lib import corpus_bridge, schema
from . import dimensions, rubric

_BRIEFS = pathlib.Path(__file__).parent / "briefs"

_WCF1_GUARDRAIL = """Draft WITHIN the Westminster Confession's doctrine of Scripture
(WCF ch.1): Scripture is God-inspired, infallible, inerrant, sufficient, and clear;
Scripture interprets Scripture. Content that hedges on this fails review. (The full
chapter and this passage's doctrinal anchors are distilled in the brief above.)"""

_RULES_BLOCK = """## How to draft (hard rules)

- ANSWERABLE FROM THIS PASSAGE: every item except a D5 (Connections) item must be
  answerable from the verses above and nothing else. A D5 item may reach out only
  to a cross-reference named in the brief, and must name it.
- COVER ONLY WHAT THE TEXT SUPPORTS: draft for a dimension only if this passage
  genuinely supports it. A short setup passage may support D1/D2/D6 and not
  D7/D8 — that is correct, not a gap. Do not pad.
- EVIDENCE, NEVER JUDGMENT: prompts elicit observable behavior; never assess
  faith, character, or spiritual state.
- STAY ON THE PASSAGE: the brief is your base, but the items are about the PASSAGE.
- TIERS: give the selector real choice — spread items across age_tiers
  (pre_reader / child / youth / adult / all) and difficulties (1-3)."""

_TYPE_BLOCK = """## What each type should be

- question: one clear question; tag the dimension it exercises.
- activity: doable on paper with ordinary materials; include a pre_reader variant
  when the passage allows one.
- pre_reading_quest: a "listen for X" prompt handed out before reading; include a
  short `category` label. Draft at child / youth / adult tiers.
- memory_verse: one or two verses from THIS passage, verbatim, with the reference.
- narration_prompt: "retell in your own words" for the passage as a whole."""

_SCHEMA_BLOCK = """Each item MUST be a JSON object with these fields:
  id, passage (the pericope id), dimension (one of: {dimensions}),
  type (one of: {types}), age_tier (one of: {tiers}), difficulty (1|2|3),
  review_status "draft", text {{ "en": "..." }}, version 1,
  category {{ "en": "..." }} ONLY for pre_reading_quest.
Do not add provenance; the reviewer stamps it."""


def _load_brief(pericope_id):
    f = _BRIEFS / f"{pericope_id.lower()}.md"
    if not f.exists():
        raise FileNotFoundError(
            f"No brief for {pericope_id}; run Stage 1 (build_brief_prompt) and "
            f"commit {f} first.")
    return f.read_text(encoding="utf-8")


def build(pericope_id, book="MAT", brief=None):
    if brief is None:
        brief = _load_brief(pericope_id)
    peris = {p["id"]: p for p in corpus_bridge.pericopes(book)}
    if pericope_id not in peris:
        raise ValueError(f"{pericope_id} is not a {book} pericope")
    p = peris[pericope_id]
    name = corpus_bridge.book_name(book, "en")
    parts = [f"# Drafting pack — {pericope_id}: {p['title_en']}\n",
             f"Passage: {name} ({p['range']})\n",
             "## THE PASSAGE — this is your SUBJECT; draft about THIS\n",
             corpus_bridge.passage_text(p["range"]) + "\n",
             "## Theological base (reviewed brief — consult; do not draft about it)\n",
             brief + "\n",
             "## Confessional guardrail\n",
             _WCF1_GUARDRAIL + "\n",
             "## Fluency dimensions to cover\n"]
    for d, desc in dimensions.TEMPLATES.items():
        parts.append(f"- {d}: {desc}")
    parts.append("")
    parts.append(_RULES_BLOCK)
    parts.append("")
    parts.append(_TYPE_BLOCK)
    parts.append("")
    parts.append("## Quality rubric (every item must pass all seven axes)\n")
    parts.append(rubric.build())
    parts.append("")
    parts.append("## Output schema\n")
    parts.append(_SCHEMA_BLOCK.format(
        dimensions=", ".join(sorted(schema.DIMENSIONS)),
        types=", ".join(sorted(schema.TYPES)),
        tiers=", ".join(sorted(schema.AGE_TIERS))))
    parts.append("")
    parts.append("Return a JSON array of draft items for this pericope.")
    return "\n".join(parts)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("pericope_id")
    ap.add_argument("--book", default="MAT")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    text = build(args.pericope_id, args.book)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        print(text)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest content_bank.tests.test_author -v`
Expected: PASS (all classes)

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/build_draft_prompt.py content_bank/tests/test_author.py
git commit -m "content_bank: Stage-2 draft pack (passage-first, brief-grounded, compact WCF)"
```

---

### Task 7: MAT-009 — brief + items (pilot for both stages)

The pilot: tunes both the brief-builder and the draft pack. Gates = fidelity review (brief) and quality review + `schema.validate_item` (items).

**Files:** Create `content_bank/author/briefs/mat-009.md`; scratchpad `<scratchpad>/gen/reviewed_MAT-009.json`; append `TUNING_LOG`; possibly modify `content_bank/author/*` or `corpus_bridge.py`.

**Interfaces:** Consumes Tasks 4-6 + `BRIEF_FIDELITY_REVIEWER`, `ITEM_QUALITY_REVIEWER`. Produces the committed brief + `<scratchpad>/gen/reviewed_MAT-009.json` (items structurally valid, `review_status:"reviewed"`).

**Stage 1 — brief**

- [ ] **Step 1: Build the brief pack** — `python3 -m content_bank.author.build_brief_prompt MAT-009 --out <scratchpad>/gen/brief_pack_MAT-009.md` (passage 4:1-11 + full WCF-1 + MHC/JFB + crossrefs + WCF 1.1/5.3/21.1-2 + WLC hits).
- [ ] **Step 2: Distill the brief** — write a ~250-word brief in the four-part shape; observe the safeguard (the Temptation's confessional hits include worship WCF 21 — anchor it as *supporting*, keep the pericope's own emphasis, Christ's obedience/victory, primary). Save `<scratchpad>/gen/brief_MAT-009.md`.
- [ ] **Step 3: Fidelity review** — dispatch ≥2 `BRIEF_FIDELITY_REVIEWER` agents concurrently with the pack's lampposts + the brief. Fix any unfaithful/novel/over-reaching claims; if a defect is systemic (the brief-builder never told the drafter something), append `TUNING_LOG` and edit `build_brief_prompt.py` (re-run `python3 -m unittest content_bank.tests.test_author -v`).
- [ ] **Step 4: Commit the brief** — copy to `content_bank/author/briefs/mat-009.md`:
```bash
git add content_bank/author/briefs/mat-009.md docs/superpowers/notes/2026-07-18-content-tuning-log.md content_bank/
git commit -m "content_bank: MAT-009 theological brief (fidelity-reviewed)"
```

**Stage 2 — items**

- [ ] **Step 5: Build the draft pack** — `python3 -m content_bank.author.build_draft_prompt MAT-009 --out <scratchpad>/gen/pack_MAT-009.md` (now loads the committed brief; passage foregrounded; compact WCF-1).
- [ ] **Step 6: Draft items** to the coverage the passage supports (D1 people/places, D2 the three temptations in order, D3 "It is written", D4 recall Jesus answered with Scripture, D5 the OT sources from the brief, D6 a learner question, D7 why Jesus answered with Scripture, D8 an observable application), across tiers, + 1 child/youth `activity` + 1 `pre_reader`, `pre_reading_quest` at child/youth/adult, one `memory_verse`, one `narration_prompt`. Each: `passage:"MAT-009"`, `review_status:"draft"`, `text:{"en":...}`, `version:1`. Write `<scratchpad>/gen/draft_MAT-009.json`.
- [ ] **Step 7: Validate structure** —
```bash
python3 -c "import json,sys; sys.path.insert(0,'.'); from content_bank.lib import schema; \
d=json.load(open('<scratchpad>/gen/draft_MAT-009.json')); \
[print(i['id'], schema.validate_item(i)) for i in d]"
```
Expected: every line `[]`.
- [ ] **Step 8: Quality review** — dispatch ≥2 `ITEM_QUALITY_REVIEWER` agents concurrently with passage + committed brief + `draft_MAT-009.json`. Union defects.
- [ ] **Step 9: Triage** — `fix="item"` → correct the item; `fix="machinery"` → append `TUNING_LOG` and edit the relevant file (`build_brief_prompt.py` / `build_draft_prompt.py` / `dimensions.py` / `review_checklist.py`), re-run `python3 -m unittest content_bank.tests.test_author content_bank.tests.test_corpus_bridge -v`, and regenerate. If a brief-builder fix changes the brief, re-run Stage 1 for MAT-009.
- [ ] **Step 10: Re-review until clean; stamp** each item `review_status:"reviewed"`, `provenance:{"drafted_by":"claude","reviewed_by":"claude-adversarial","reviewed_date":"2026-07-18","guardrail":"WCF-1","brief":"author/briefs/mat-009.md"}`. Write `<scratchpad>/gen/reviewed_MAT-009.json`.
- [ ] **Step 11: Commit** machinery/log:
```bash
git add docs/superpowers/notes/2026-07-18-content-tuning-log.md content_bank/
git commit -m "content_bank: MAT-009 items generated + reviewed; pilot tuning findings"
```

---

### Task 8: MAT-013 — brief + items (thin-passage restraint)

Same two-stage loop as Task 7 for `MAT-013` (5:1-2). Confessional hits: **none** — the brief omits the doctrinal anchor (no invention). Coverage: D1 (crowds/disciples/mountain), D2, D6 only; not D5/D7/D8. Commentary is present (MHC 5:1-2, JFB 5:2), so the brief still has exegetical grounding.

**Files:** Create `content_bank/author/briefs/mat-013.md`; scratchpad `reviewed_MAT-013.json`; append `TUNING_LOG`; possibly modify machinery.

- [ ] **Step 1: Brief pack** — `python3 -m content_bank.author.build_brief_prompt MAT-013 --out <scratchpad>/gen/brief_pack_MAT-013.md` (confessional section reads "No confessional proof-text…").
- [ ] **Step 2: Distill brief** — four-part shape; doctrinal-anchor part notes reliance on WCF-1 method only (no proof-text doctrine). Save `<scratchpad>/gen/brief_MAT-013.md`.
- [ ] **Step 3: Fidelity review** — ≥2 `BRIEF_FIDELITY_REVIEWER`; a reviewer demanding invented doctrine is wrong here — record restraint held.
- [ ] **Step 4: Commit brief** → `content_bank/author/briefs/mat-013.md`:
```bash
git add content_bank/author/briefs/mat-013.md docs/superpowers/notes/2026-07-18-content-tuning-log.md content_bank/
git commit -m "content_bank: MAT-013 theological brief (no proof-text doctrine; restraint)"
```
- [ ] **Step 5: Draft pack** — `python3 -m content_bank.author.build_draft_prompt MAT-013 --out <scratchpad>/gen/pack_MAT-013.md`.
- [ ] **Step 6: Draft** D1/D2/D6 only (+ `narration_prompt` if supported); a D1 `pre_reading_quest` ("who is on the mountain?") at child/adult, a D1/D2 `question`. No D5/D7/D8. Write `<scratchpad>/gen/draft_MAT-013.json`.
- [ ] **Step 7: Validate structure** — the Task 7 Step 7 one-liner on `draft_MAT-013.json`; expect `[]`.
- [ ] **Step 8: Quality review** — ≥2 `ITEM_QUALITY_REVIEWER`; "missing D7/D8" is not a defect here.
- [ ] **Step 9: Triage** — item vs machinery (Task 7 Step 9).
- [ ] **Step 10: Re-review, stamp `reviewed` + provenance** (`brief":"author/briefs/mat-013.md"`); write `reviewed_MAT-013.json`.
- [ ] **Step 11: Commit**:
```bash
git add docs/superpowers/notes/2026-07-18-content-tuning-log.md content_bank/
git commit -m "content_bank: MAT-013 items generated + reviewed"
```

---

### Task 9: MAT-014 — brief + items (Beatitudes, flagship)

Same two-stage loop for `MAT-014` (5:3-12). Confessional hits: WCF 19.6 (law's promises), WLC Q172 (**safeguard case** — use only its reading of poor-in-spirit/mourn; drop the Lord's-Supper topic). A reference brief already drafted in design discussion may seed Step 2. Richest coverage (D1-D8 as the text supports).

**Files:** Create `content_bank/author/briefs/mat-014.md`; scratchpad `reviewed_MAT-014.json`; append `TUNING_LOG`; possibly modify machinery.

- [ ] **Step 1: Brief pack** — `python3 -m content_bank.author.build_brief_prompt MAT-014 --out <scratchpad>/gen/brief_pack_MAT-014.md`.
- [ ] **Step 2: Distill brief** — four-part shape; explicitly apply the WLC Q172 safeguard and end with the off-agenda note. Save `<scratchpad>/gen/brief_MAT-014.md`.
- [ ] **Step 3: Fidelity review** — ≥2 `BRIEF_FIDELITY_REVIEWER`; confirm the sacramentology is excluded and no novelty added.
- [ ] **Step 4: Commit brief** → `content_bank/author/briefs/mat-014.md`:
```bash
git add content_bank/author/briefs/mat-014.md docs/superpowers/notes/2026-07-18-content-tuning-log.md content_bank/
git commit -m "content_bank: MAT-014 Beatitudes brief (proof-text safeguard applied)"
```
- [ ] **Step 5: Draft pack** — `python3 -m content_bank.author.build_draft_prompt MAT-014 --out <scratchpad>/gen/pack_MAT-014.md`.
- [ ] **Step 6: Draft** the full supported coverage across tiers; D5 items name a brief cross-reference (e.g. Ps 37:11 → v.5). Write `<scratchpad>/gen/draft_MAT-014.json`.
- [ ] **Step 7: Validate structure** — one-liner; expect `[]`.
- [ ] **Step 8: Quality review** — ≥2 `ITEM_QUALITY_REVIEWER` with passage + brief.
- [ ] **Step 9: Triage** — item vs machinery.
- [ ] **Step 10: Re-review, stamp `reviewed` + provenance** (`brief":"author/briefs/mat-014.md"`); write `reviewed_MAT-014.json`.
- [ ] **Step 11: Commit**:
```bash
git add docs/superpowers/notes/2026-07-18-content-tuning-log.md content_bank/
git commit -m "content_bank: MAT-014 Beatitudes items generated + reviewed"
```

---

### Task 10: MAT-015 — brief + items (Salt & Light)

Same two-stage loop for `MAT-015` (5:13-16). Confessional hit: WCF 16.2 (good works glorify God, via v.16 — on point). Coverage: D3 salt/light, D7 what the light is for (v16), D4 the v16 memory verse, D8 observable "let your light shine", D6, D1/D2 as supported.

**Files:** Create `content_bank/author/briefs/mat-015.md`; scratchpad `reviewed_MAT-015.json`; append `TUNING_LOG`; possibly modify machinery.

- [ ] **Step 1: Brief pack** — `python3 -m content_bank.author.build_brief_prompt MAT-015 --out <scratchpad>/gen/brief_pack_MAT-015.md`.
- [ ] **Step 2: Distill brief** — four-part shape; anchor WCF 16.2 to v.16. Save `<scratchpad>/gen/brief_MAT-015.md`.
- [ ] **Step 3: Fidelity review** — ≥2 `BRIEF_FIDELITY_REVIEWER`.
- [ ] **Step 4: Commit brief** → `content_bank/author/briefs/mat-015.md`:
```bash
git add content_bank/author/briefs/mat-015.md docs/superpowers/notes/2026-07-18-content-tuning-log.md content_bank/
git commit -m "content_bank: MAT-015 Salt and Light brief"
```
- [ ] **Step 5: Draft pack** — `python3 -m content_bank.author.build_draft_prompt MAT-015 --out <scratchpad>/gen/pack_MAT-015.md`.
- [ ] **Step 6: Draft** the supported coverage across tiers; write `<scratchpad>/gen/draft_MAT-015.json`.
- [ ] **Step 7: Validate structure** — one-liner; expect `[]`.
- [ ] **Step 8: Quality review** — ≥2 `ITEM_QUALITY_REVIEWER` with passage + brief.
- [ ] **Step 9: Triage** — item vs machinery.
- [ ] **Step 10: Re-review, stamp `reviewed` + provenance** (`brief":"author/briefs/mat-015.md"`); write `reviewed_MAT-015.json`.
- [ ] **Step 11: Commit**:
```bash
git add docs/superpowers/notes/2026-07-18-content-tuning-log.md content_bank/
git commit -m "content_bank: MAT-015 Salt and Light items generated + reviewed"
```

---

### Task 11: Assemble the store; validate; prove the gate

**Files:** Modify `content_bank/store/mat.json`; Test `content_bank/tests/test_store_matthew.py`, `content_bank/tests/test_prototype_bank.py`.

**Interfaces:** Consumes `reviewed_MAT-009/013/014/015.json`; `validate.validate_store`, `content.get_content`. Produces a store of the four pericopes' reviewed items; `validate_store("MAT")["errors"] == []`.

- [ ] **Step 1: Assemble** — concatenate the four scratchpad arrays into `{"book":"MAT","items":[...]}`, write `content_bank/store/mat.json`. All `review_status:"reviewed"` (Task 13 publishes). Verify id uniqueness.

- [ ] **Step 2: Rewrite the seed-dependent store tests** — replace `TestMatthewStore` in `content_bank/tests/test_store_matthew.py`:

```python
class TestMatthewStore(unittest.TestCase):
    def test_store_validates_clean(self):
        self.assertEqual(validate.validate_store("MAT")["errors"], [])

    def test_only_scoped_pericopes_present(self):
        store = content.load_book_store("MAT")
        self.assertEqual({i["passage"] for i in store["items"]},
                         {"MAT-009", "MAT-013", "MAT-014", "MAT-015"})

    def test_every_item_reviewed_before_confirmation(self):
        self.assertEqual(content.get_content("MAT", mode="product"), [])
        self.assertTrue(content.get_content("MAT", mode="author"))
```
(`validate`, `content` already imported.)

- [ ] **Step 3: Fix `test_prototype_bank.py`** — `TestLoadBank` references deleted seed ids and a `zh` test; `TestDisplayRef` is fine. Replace `TestLoadBank`:

```python
class TestLoadBank(unittest.TestCase):
    def setUp(self):
        self.bank = pb.load_bank("MAT", lang="en")

    def test_pericopes_include_corpus_ids_with_display_refs(self):
        by_id = {p["id"]: p for p in self.bank["pericopes"]}
        self.assertEqual(by_id["MAT-014"]["ref"], "Matthew 5:3–12")
        self.assertEqual(by_id["MAT-014"]["title"], "The Beatitudes")

    def test_items_flattened_to_body_and_product_gated(self):
        self.assertTrue(self.bank["items"])                 # green after Task 13
        item = self.bank["items"][0]
        self.assertIsInstance(item["body"], str)
        self.assertNotIn("text", item)
        self.assertNotIn("draft", {i["review_status"] for i in self.bank["items"]})
```
Delete `test_quest_category_flattened`, `test_zh_bank_uses_translation`. `test_content.py` (temp fixtures) needs no change.

- [ ] **Step 4: Run tests** —
Run: `python3 -m unittest content_bank.tests.test_store_matthew -v` → the three PASS.
Run: `python3 -m unittest discover -s content_bank/tests -v` → PASS **except** `test_items_flattened_to_body_and_product_gated` (needs a non-empty product bank; green after Task 13).

- [ ] **Step 5: Commit**

```bash
git add content_bank/store/mat.json content_bank/tests/
git commit -m "content_bank: assemble MAT store (reviewed), replace seed; gate proven"
```

---

### Task 12: Wire MAT-013 into the sequence; resolve the demo passage

**Files:** Modify `prototype/family.json`; Test `prototype/test_selector.py`; manual `generate_kit.py`.

**Interfaces:** Consumes the published store (after Task 13), `selector.build_kit`. Produces `reading_sequence == ["MAT-009","MAT-013","MAT-014","MAT-015"]` with the demo still on the Beatitudes.

- [ ] **Step 1: Update sequence + preserve demo** — set `"reading_sequence": ["MAT-009","MAT-013","MAT-014","MAT-015"]`. Append a studied MAT-013 session so `next_passage` returns MAT-014:

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

- [ ] **Step 2: Write the failing test** — add to `prototype/test_selector.py`:

```python
    def test_reading_sequence_includes_mat013_before_beatitudes(self):
        import json, pathlib
        fam = json.loads((pathlib.Path(__file__).parent / "family.json").read_text())
        self.assertIn("MAT-013", fam["reading_sequence"])
        self.assertEqual(fam["reading_sequence"].index("MAT-013"),
                         fam["reading_sequence"].index("MAT-014") - 1)
```

- [ ] **Step 3: Run the selector suite** — `cd prototype && python3 -m unittest test_selector -v`. The new test PASSES; the existing next-passage tests still hold via the added session. **These read the live store and go fully green only after Task 13 publishes.**

- [ ] **Step 4: Verify the kit end-to-end** (after Task 13) — `cd prototype && python3 generate_kit.py -o <scratchpad>/gen/kit_demo.md`. Expect a coherent MAT-014 kit (review from 009/013, discussion across dimensions, activity + younger variant, quests per member, memory verse, narration). Read it; confirm every referenced item exists.

- [ ] **Step 5: Commit**

```bash
git add prototype/family.json prototype/test_selector.py
git commit -m "prototype: add MAT-013 to reading sequence; keep Beatitudes as demo"
```

---

### Task 13: Human confirmation digest → publish

**Files:** Create `<scratchpad>/gen/confirmation_digest.md`; Modify `content_bank/store/mat.json`.

**Interfaces:** Consumes the assembled store (Task 11). Produces a published store.

- [ ] **Step 1: Build the digest** — `<scratchpad>/gen/confirmation_digest.md`: one line per item (`id · passage · dimension · type · age_tier · difficulty · en text`), grouped by pericope, with per-pericope dimension coverage and counts, and a link to each brief.
- [ ] **Step 2: Present the digest and STOP for human approval** — present to the user; ask to approve, or list items to hold/edit. **Do not proceed without an explicit answer.** Apply requested edits (re-review edited items via the relevant Stage-2 quality step if substance changed).
- [ ] **Step 3: Stamp published** — for each approved item: `review_status:"published"`, add `provenance.confirmed_by:"kyhhdm"`. Held items stay `reviewed`.
- [ ] **Step 4: Prove the gate** —
```bash
python3 -c "import sys; sys.path.insert(0,'.'); from content_bank.lib import content; \
print('published:', len(content.get_content('MAT', mode='product')))"
```
Expected: positive count = approved items.
- [ ] **Step 5: Update the gate test; run all gated suites** — rename `test_every_item_reviewed_before_confirmation` → `test_gate_serves_published` (product non-empty, holds no `reviewed`/`draft`). Then:
```
python3 -m unittest discover -s content_bank/tests -v      # incl. test_prototype_bank green
cd prototype && python3 -m unittest test_selector -v && cd ..
```
Expected: all PASS (satisfies the Task 11 / Task 12 items gated on publish).
- [ ] **Step 6: Commit**

```bash
git add content_bank/store/mat.json content_bank/tests/test_store_matthew.py
git commit -m "content_bank: publish confirmed MAT items (human gate)"
```

---

### Task 14: Provenance, tuning writeup, final verification

**Files:** Modify `content_bank/PROVENANCE.md`; Finalize `docs/superpowers/notes/2026-07-18-content-tuning-log.md`.

- [ ] **Step 1: Record provenance** — append to `content_bank/PROVENANCE.md`: this cycle — MAT-009/013/014/015, drafted_by claude, each item grounded in a committed brief distilled from BSB + WCF-1 + JFB/MHC + cross-references + WCF/WLC/WSC proof-texts, adversarially reviewed (fidelity + quality), human-confirmed by kyhhdm 2026-07-18, English-only, seed replaced. List the four briefs.
- [ ] **Step 2: Finalize the writeup** — complete the tuning log: (a) fidelity defects (Stage 1) and quality defects (Stage 2) by axis; (b) each machinery change + the defect that motivated it (brief-builder, draft pack, dimensions, checklist); (c) residual limits (English-only; zh deferred; lexicon absent; thin-passage coverage; the WLC-Q172-style proof-text discipline; any axis the agents were weak at).
- [ ] **Step 3: Run every suite** —
```
python3 -m unittest discover -s content_bank/tests -v
cd prototype && python3 -m unittest test_selector -v && cd ..
python3 -m unittest discover -s corpus/tests -v
```
Expected: all PASS, no regressions.
- [ ] **Step 4: Final kit smoke test** — `cd prototype && python3 generate_kit.py` — a coherent Beatitudes kit, no missing items.
- [ ] **Step 5: Commit**

```bash
git add content_bank/PROVENANCE.md docs/superpowers/notes/2026-07-18-content-tuning-log.md
git commit -m "content_bank: provenance + quality/tuning writeup for prototype content"
```

---

## Self-Review

**Spec coverage:**
- Rubric → Task 1; checklist mirrors it → Task 2; dimension guidance → Task 3.
- `corpus_bridge` commentary + crossrefs + **confessional_refs** → Task 4.
- **Stage-1 brief pack** (`build_brief_prompt`, full lampposts, ~250-word shape, safeguard) → Task 5.
- **Stage-2 draft pack** (passage-first, brief-grounded, compact WCF-1) → Task 6.
- Per-pericope two-stage generate + fidelity/quality review + triage → Tasks 7-10; thin-passage restraint (Task 8), safeguard case (Task 9).
- Committed briefs → Tasks 7-10 (`author/briefs/*.md`).
- Store assembly + gate → Task 11; MAT-013 sequence + demo → Task 12; human gate → Task 13; provenance + writeup + verification → Task 14.
- Two-stage, passage-first proportion, WLC/WSC in scope, lampposts-not-shipped → Global Constraints.

**Placeholder scan:** No TBD/TODO. Generation tasks (7-10) are generative, not code-TDD; each has concrete gates (fidelity review; `validate_item`; quality review) and concrete commands. `<scratchpad>` is a real path supplied at execution.

**Type consistency:** `rubric.build()`/`AXES` (Task 1) → Tasks 2, 6. `dimensions.TEMPLATES` keys == `schema.DIMENSIONS` (Task 3), invariant kept. `corpus_bridge.commentary/crossrefs/confessional_refs` (Task 4) → Task 5's brief pack (and Task 6 does not re-inject them). `build_brief_prompt.build(pericope_id, book)` (Task 5) → Tasks 7-10 Stage 1. `build_draft_prompt.build(pericope_id, book, brief=None)` loads `author/briefs/<lower>.md` (Task 6) → Tasks 7-10 Stage 2, which commit those briefs first. Provenance keys (`drafted_by`, `reviewed_by`, `reviewed_date`, `guardrail`, `brief`, `confirmed_by`) consistent across Tasks 7-10, 13; satisfy `schema.validate_item`.

**Ordering dependencies (flagged in-plan):**
1. Per pericope, the **brief must be committed (Stage 1) before Stage 2** — `build_draft_prompt` raises `FileNotFoundError` otherwise. Tasks 7-10 order their steps accordingly.
2. The live-store checks — Task 11 Step 4's `test_items_flattened...`, Task 12 Step 3's selector tests, Task 12 Step 4's kit run — depend on **Task 13 having published**. Task 13 Step 5 is where the full suites are expected green. Intentional: content assembled (11) and MAT-013 sequenced (12) before a coherent demo can be judged, but nothing publishes until the human confirms (13).
