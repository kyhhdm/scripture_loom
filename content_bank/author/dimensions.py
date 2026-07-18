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
