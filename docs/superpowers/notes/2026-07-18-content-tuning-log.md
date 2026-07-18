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

## Stage 1 — MAT-014 brief (Beatitudes, flagship)

Both fidelity reviewers caught the same HIGH-severity defect: WCF 19.6 (cited in
the pack "via MAT.5.5", the meek inheriting the earth) was mis-attached to
vv.10-12 AND its qualifier "not as due... by the law as a covenant of works" was
dropped — the exact guard against reading the Beatitudes as works-righteousness.
- item: reattached WCF 19.6 to v.5, restored the covenant-of-works qualifier,
  softened the v.12 extension to an explicit inference.
- machinery: added to build_brief_prompt._SHAPE — "CITE CONFESSIONAL STATEMENTS
  FAITHFULLY: attach each citation to the verse the pack says it was cited via,
  and keep its qualifying clauses; never quote only the half that suits the point."
The WLC Q172 safeguard was applied correctly by the drafter (poor/mourning-heart
reading only; Lord's-Supper subject off-agenda) — the flagship safeguard case held.

## Stage 2 — MAT-014 items (Beatitudes)

18 items. Axes 1/3/6 clean. Machinery: the draft pack's schema block offered all
seven schema types, so the drafter emitted an out-of-scope `vocab_list` item; added
an in-scope-types line to build_draft_prompt._TYPE_BLOCK (bars vocab_list/key_facts).
Item fixes: D1 "blessed groups" mislabel → retagged D4 (character-groups aren't
people/places; D1 correctly = 0 for 5:3-12, the setting being in MAT-013);
vocab_list → question anchored to each term's stated promise; first/last saying
disambiguated; D7 kingdom item made text-anchored (declarative "for theirs is..."
grammar, no works-righteousness, no leader-only reference); child quest made
unambiguous (count all 8 third-person sayings, not the literal word "those").

## Stage 1+2 — MAT-015 (Salt and Light)

Brief: both fidelity reviewers PASS; WCF 16.2 cited at v.16 with its "fruits and
evidences, not the ground of standing" qualifier intact. Low polish only
(over-symmetrized salt/light warning; a cross-ref gloss; dropped a duplicate ref).
Items: 16, D2-D8 (D1 correctly omitted). Most important quality fixes were axis-1
(self-display): two D8 application items framed good deeds around "being seen"
without v.16's "so they glorify God" purpose — restored the God-glory aim in both.
Also: three D3-tag/answerability slips (a "why did Jesus pick this image" question
not answerable from the text; consequence-facts mis-tagged D3) retagged/reworded;
a compound D2 item split to a clean ordering task; a pre_reader activity retagged
D3. No new machinery (all item-level).
