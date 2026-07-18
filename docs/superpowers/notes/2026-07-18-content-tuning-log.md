# Content quality / tuning log — prototype content cycle (2026-07-18)

Defects found by adversarial review, and the machinery changes each motivated.
Stage 1 = theological brief (fidelity review); Stage 2 = items (quality review).

## Stage 1 — MAT-009 brief (pilot)

Two independent fidelity reviewers, both found real theological drift:

- **MAJOR (item + machinery)** — Key term "It is written" glossed as "honoring
  Scripture's sufficiency *over his own authority*." MHC (v.4) says the opposite
  nuance: Christ *is* the eternal Word who could have spoken on his own authority
  but *voluntarily* honored Scripture as an example. The brief overstated it into
  a Christological error (Jesus needing Scripture's warrant).
  → item: reword to voluntary condescension.
  → machinery: added "PRESERVE THE COMMENTARY'S NUANCE — do not sharpen, flatten,
    or overstate a claim beyond what the lamppost says" to `build_brief_prompt._SHAPE`.
- **MAJOR (item + machinery)** — "correcting Satan's misquotation with a fuller
  word (WCF 1.9)." JFB explicitly rejects the misquotation-correction reading;
  the relation is one text (precept Deu 6:16) *governing the application of*
  another (promise Ps 91), i.e. Scripture interpreting Scripture.
  → item: reword to precept-governs-promise.
  → machinery: same PRESERVE-NUANCE addition (cites this exact case).
- **MINOR (item + machinery)** — Greek gloss "peirazō" introduced under "Key
  terms (from commentary)" though no lamppost supplies it (private scholarship).
  → item: drop the Greek.
  → machinery: "Key terms — use only words that appear in the passage or the
    commentary; do NOT introduce original-language glosses unless the commentary
    supplies them" added to `build_brief_prompt._SHAPE`.

Machinery file changed: `content_bank/author/build_brief_prompt.py` (`_SHAPE`).

## Stage 2 — MAT-009 items (pilot), first quality pass

Two adversarial quality reviewers, 20 items. Axes 1/3/6 clean across all items.
Machinery defects (fixed, benefit all pericopes):

- **MAJOR (machinery)** — `passage_text` served verses in STRING order (4.1, 4.10,
  4.11, 4.2, …) not numeric, misleading the drafter about agency (two items wrongly
  said the devil led Jesus to the wilderness — the Spirit did, v.1). Root-caused by
  a reviewer. → `corpus_bridge.passage_text` now sorts by (chapter, verse);
  regression test `TestPassageOrdering` added.
- **MAJOR (machinery)** — `pre_reading_quest` "listen-for" prompts are inherently
  fact-noticing but were tagged D2/D7 they can't carry. → `build_draft_prompt`
  `_TYPE_BLOCK` now steers quests to D1-D4 and requires a why/connection/question
  clause for any D5/D6/D7 quest.
- **process (machinery)** — the `build_draft_prompt` pack `<6000`-char test bound
  (flagged fragile in Task 6) broke when the type guidance grew; relaxed to `<9000`
  with the full-WCF-absent assertion documented as the real leanness gate.

Item-level defects (fixed in the repair pass): false devil-agency (2 items);
"same phrase" overstatement (wording varies); D3-tagged interpretive item; trivial
D4 binary (not recall); false "rather than commanding the devil" alternative;
D8 item that was memorization mechanics (dup of memory_verse); child-tier activity
with too-heavy writing load; memory_verse dropped nested quotation marks;
D2 multiple-choice with options in passage order (position gives it away).

## Stage 1+2 — MAT-013 (thin setup, restraint check)

Brief: both fidelity reviewers PASS; only low-severity cross-ref polish (a
mis-grouped parallel scene; added the JFB "opened his mouth" Acts parallels).
Restraint held — empty confessional section reported, no doctrine invented,
D5/D7/D8 explicitly not forced. 8 items, D1/D2/D6 only.
Item defects (fixed, no machinery): a D2 ordering activity printed its options in
passage order (scrambled it); two items asserted the crowd's position ("nearby"/
"farther away") — a spatial detail not in 5:1-2 (removed). No machinery change —
these were content slips already covered by the answerable-from-passage rule.
