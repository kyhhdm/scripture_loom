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
