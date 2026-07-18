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
