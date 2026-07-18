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
