# Design: Fluency Dimensions and the Session Kit Generator

This document specifies the two foundations of the prepare phase:

1. **The fluency dimension model** — the shared ontology used by question generation, paper activities, the leader's evidence grid, evidence classification, and the longitudinal member record.
2. **The kit generator architecture** — a static content library plus a personal selector/scheduler, not per-session content generation.

It builds on `core_principles.md` and follows its decisions.

---

## Part 1: The Fluency Dimension Model

### Why dimensions come first

The dimensions are one vocabulary used by four subsystems:

```text
Prepare:  questions and activities are indexed per dimension;
          observation targets rotate across dimensions
Gather:   the leader's evidence marks map to dimensions
Reflect:  confirmed evidence is classified by dimension
Record:   each member's fluency profile is tracked per dimension over time
```

If these subsystems use inconsistent vocabularies, the longitudinal record — the product's durable asset — degrades into an unqueryable diary. The dimension set is therefore the one schema that must be designed deliberately and kept stable for years: a family's third year of records must remain comparable with their first.

### Design rules

- **Small and stable.** Eight dimensions. Additions require strong justification; renames and merges of existing dimensions are breaking changes to every family's record.
- **Each dimension is a profile, not a label.** Every dimension defines: what it means, what observable evidence looks like, its question templates, its paper activity types, and how it matures across the learning stages (Familiarity → Recognition → Understanding → Meditation → Wisdom).
- **Observable evidence only.** Every dimension's evidence descriptions must be behaviors a leader can see or hear — never judgments about the person (per core principle 4).

### During-session codes vs. dimensions

The leader's in-session shorthand stays tiny — the six evidence-type codes from the founding design:

```text
Q  question        A  answer attempt   R  recall
C  connection      U  uncertainty      P  personal application
```

Dimensions are richer than codes on purpose. The mapping from a mark to a dimension happens in the **reflect phase**, where the app proposes and the leader confirms. Example: `L-R△` (Liberty, recall, partial) may resolve to *Event Sequence* ("retold the story but reversed two events") or to *Memory* ("recited the verse with hints") — the leader knows which, and confirming takes one tap. The leader never needs the eight-dimension taxonomy at the table.

### The eight dimensions

#### D1. People & Places

Knowing who the people of Scripture are and where events happen; the biblical "cast and map."

- **Observable evidence:** names a person and says who they are; locates an event on a map; distinguishes similar figures (the Johns, the Herods, the Marys); knows relationships (Ruth → David).
- **Question templates:** Who did ___? Who was ___'s father/brother/king? Where did this happen? Which land did they travel from/to?
- **Paper activities:** match people to actions; mark places on a map; family-tree filling; "who am I?" riddle cards.
- **Progression:** recognizes major names → places figures in their book and era → explains a figure's role in the larger story.

#### D2. Event Sequence

The order and flow of events — within a passage, within a book, and across the biblical timeline.

- **Observable evidence:** retells events in order; places a story before/after another; positions an event on the wall timeline; notices narrative cause and effect ("this happened *because*…").
- **Question templates:** What happened first/next/after? What happened right before this passage? Put these in order.
- **Paper activities:** event strips to arrange; timeline placement; comic-panel ordering; "what's missing from this sequence?"
- **Progression:** orders events inside one story → orders stories inside one book → places books and eras on the whole-Bible timeline.

#### D3. Vocabulary

The Bible's own words — key terms, names, and repeated phrases — understood in their biblical sense.

- **Observable evidence:** explains a word in their own words ("blessed," "covenant," "meek"); notices a word repeating within a passage; flags a word as unfamiliar (the Word finder role produces this directly).
- **Question templates:** What does ___ mean here? What word or phrase repeats? Is ___ used the same way as in [earlier passage]?
- **Paper activities:** word-hunt (circle repeats in the printed text); fill in missing words; match word to meaning; the family word list page.
- **Progression:** notices and asks about words → gives own-words definitions → tracks a word's usage across books.

#### D4. Memory

Holding Scripture itself: memory verses, key phrases, and passage recall.

- **Observable evidence:** recites a verse (unaided / with hints / partially); identifies which passage a quoted line comes from; recalls last session's passage content.
- **Question templates:** Which verse did we memorize last time? Finish this sentence: "Blessed are the…" Where is this verse from?
- **Paper activities:** verse cards; arrange cut-up verse strips; write the verse from memory; first-letters prompt sheets.
- **Progression:** recognizes a memorized verse → recites unaided → recalls verse + reference and uses it in discussion unprompted.

#### D5. Connections

Linking the current passage to other passages, to earlier sessions, and to the Bible's larger patterns.

- **Observable evidence:** "this reminds me of…" with a concrete referent; notices a quotation or allusion (Jesus quoting Deuteronomy); links a theme across books; connects to a previous session's material.
- **Question templates:** What does this remind you of? Where have we seen this pattern/word/promise before? How is this like/unlike [earlier story]?
- **Paper activities:** connection cards ("I think this connects to…"); thread lines between passages on the timeline; pattern-pair matching.
- **Progression:** connects to last week → connects across a book → connects across Testaments and recognizes recurring biblical patterns.

#### D6. Questions

The learner's own question-asking — a leading indicator of engagement and growing understanding, tracked as a skill in itself.

- **Observable evidence:** asks a factual question; asks an interpretive question ("why does Jesus say…"); asks an application question; refines or follows up on an earlier question.
- **Question templates:** (prompts, since the learner supplies the questions) What is confusing? What do you wonder about? Write one question for the family.
- **Paper activities:** question cards (Question keeper role); the exit card's "one thing I still wonder"; question round.
- **Progression:** asks factual "what" questions → interpretive "why" questions → questions that connect passages or probe application.

#### D7. Interpretation

Understanding what the text means — first observing what it actually says, then explaining why.

- **Observable evidence:** accurately narrates the passage's point in own words; answers a "why" question from the text rather than guessing; corrects a misreading; distinguishes what the text says from what they assumed.
- **Question templates:** What is the main thing this passage says? Why did ___ do/say that? What in the text tells you so? What surprised you?
- **Paper activities:** narration (retell, then the family checks against the text); sort statements into "the text says / the text doesn't say"; choose the best summary.
- **Progression:** accurate observation of what is written → explains meaning within the passage → explains the passage within its larger context — the book's argument, the psalm's movement, or the proverb's contrast, according to the passage's kind.

#### D8. Application

Bringing the passage into the learner's own life — kept observable and never graded as spirituality.

- **Observable evidence:** states a concrete personal application ("I could make peace with my classmate"); recalls a past application and reports on it; turns the passage into a prayer topic.
- **Question templates:** Is there anything here for us to do or remember this week? How would this look at school/home? What should we pray from this passage?
- **Paper activities:** application card; prayer-topic slip; "this week I will…" line on the exit card.
- **Progression:** offers an application when prompted → applies unprompted → reports back on a previous application.

**Boundary (core principle 4):** the record stores *stated applications and reports*, never assessments of sincerity, faith, or maturity.

---

## Part 2: Kit Generator Architecture

### The kit's two identities: evidence and activation

The kit serves the leader as **evidence infrastructure** (what to observe, where marks land). It serves the reader as **activation infrastructure** — the questions, quests, and memory work exist to break passive scroll-mode reading and put a question in the reader's mind before the text arrives (core principle 7). Same paper, two functions; the activation function serves the learner directly and is the primary one.

Activation is a scaffold designed to fade. Its arc is dimension D6's progression made operational:

```text
Stage 1  kit supplies each member's full pre-reading quest
Stage 2  kit supplies only a category ("find something that repeats");
         the member forms the specific question
Stage 3  the sheet says only: "Write your own quest before we read."
Stage 4  no prompt — the member asks unprompted
```

Advancement is triggered by evidence the system already collects: when a member's questions and noticings begin appearing **unprompted**, the scheduler fades their scaffold. An unprompted question is the single clearest signal that the active-reading habit is forming — notable (`★`) by definition.

### The decision: static library, personal selection

The Bible is a finite, unchanging corpus. Good recall questions, event-ordering activities, and vocabulary lists for a given passage do not vary per family. Therefore:

> **Content is static, authored once, and human-reviewed — like a book.
> Personalization is selection and scheduling, not generation.**

This is the Anki model: the cards are fixed; the scheduling is personal.

Why this is right for this product:

- **Doctrinal safety and quality.** Live LLM generation would place unreviewed theological content on a family's table. A static library is reviewed once by a human before any family sees it.
- **Near-zero marginal cost per session** — consistent with the decision to deprioritize transcription for cost reasons.
- **Printability.** Static content is typeset once, correctly; generated content produces layout surprises on paper.
- **Offline capability** — fits both the unplugged ethos and mainland-China network realities.
- **A de-risking path:** the library plus a default reading sequence is already shippable as a physical study guide before any app exists.

AI's role is **at library-build time** (drafting per-passage content for human review) and **in the reflect phase** (proposing classifications for photographed evidence) — never at session time.

### The pipeline

```text
Content library                Member records
(static, versioned)            (evidence history per dimension)
        \                          /
         \                        /
          Selector / Scheduler
   (dimension rotation, spaced review,
    weakness targeting, age tiering)
                  |
            Kit composer
   (fills page templates with selections)
                  |
        Printable session kit
   (leader guide, observation sheets,
    recall activity, evidence grid)
```

### The content library

Indexed by **passage × dimension × age tier**, versioned, human-reviewed.

```text
ContentItem
  id
  passage        e.g. Matthew 5:1–12 (pericope-level, not verse-level)
  dimension      D1–D8
  age_tier       pre-reader | child | youth | adult
  type           question | activity | vocab_list | memory_verse
                 | key_facts | narration_prompt | pre_reading_quest
  body           the content itself (print-ready)
  difficulty     within-tier level, for progression
  review_status  draft (AI-assisted) | reviewed | published
  version
```

Notes:

- **Pericope-level indexing** matches how sessions actually consume Scripture (whole scenes, not verses) and keeps the library finite: roughly 1,000–1,500 pericopes cover the whole Bible; the library grows book by book following the default reading sequence.
- **`key_facts`** items (people, places, events, repeated words per pericope) are the raw material for auto-assembling matching/ordering activities without new authoring.
- **`pre_reading_quest`** items are handed out *before* the passage is read: a look-for, a prediction, a count, a character to track — one per member, indexed by dimension like everything else. Many can be auto-assembled from `key_facts` ("this passage has a repeated phrase — find it").
- Only `published` items are ever selectable for a kit.

### The theological guardrail

The library is **not theologically agnostic**. All content authoring and review is anchored to a fixed confessional standard: the **Westminster Confession of Faith, especially Chapter 1** on Holy Scripture — its inspiration, infallibility, inerrancy, sufficiency, clarity, and the principle that Scripture interprets Scripture (WCF 1.9, which is dimension D5 stated confessionally).

The guardrail operates at both stages of the content pipeline:

- **AI-assisted drafting:** the confession (and derived guidance) is injected into every drafting prompt as a hard constraint — the model drafts *within* the tradition, not neutrally.
- **Human review:** the `draft → reviewed → published` gate includes explicit conformity checking against the standard, alongside accuracy and age-appropriateness. Content that hedges on what the confession affirms (e.g., treating the text's reliability as an open question) fails review.

A guardrail must be fixed to function: v1 commits to this one standard rather than making theology configurable. The evidence system is unaffected — per the governing conviction in `core_principles.md`, the app records observable fluency and never measures faith.

### The member record

The other input to selection — what reflect-phase confirmations accumulate into:

```text
EvidenceItem
  member, date, passage
  dimension       D1–D8 (confirmed by leader)
  code            Q | A | R | C | U | P
  quality         ✓ clear | △ partial | ? needs follow-up | ★ notable
  prompted        yes | no — was this elicited by a kit question/quest,
                  or did the member produce it unprompted?
  note            one confirmed sentence
  followup_ref    optional pointer to a ContentItem or review target
```

Per-member, per-dimension aggregation over these items yields the fluency profile: recent strength, open follow-ups, items due for review, and stage of progression. The prompted/unprompted ratio over time is the activation metric: the product's success measure per member is movement from prompted toward unprompted, not questions answered correctly. An app whose members stay dependent on its questions forever is failing even while looking engaged.

### The selector/scheduler

Deterministic rules first; no model needed at session time.

1. **Passage:** next pericope in the family's reading sequence (continuous reading through whole books, per the pedagogy).
2. **Review questions (2–3):** spaced review drawn from the member records — items marked `△`/`?` recently, plus older `✓` items due for reinforcement. Longer gaps for solid items, short gaps for shaky ones; simple fixed intervals are sufficient for v1.
3. **Observation targets (2–3, never more):** rotate through D1–D8 across sessions, biased toward each member's weakest recent dimensions and any dimension not observed for several sessions.
4. **Discussion questions and activity:** from the library at `passage × selected dimensions × each member's age tier`, preferring items not used with this family before.
5. **Pre-reading quests (one per member):** selected like discussion questions, but scaled to each member's activation stage — full quest, category-only, "write your own," or omitted entirely for members who now ask unprompted. The activation stage is derived from the member's recent `prompted: no` evidence in D6 and related dimensions.
6. **Personalized lines** are templated composition, not generation — slots filled from the member record:

```text
Last session, {member} asked: "{question}" — return to it together.
Ask {member} to retell {previous_passage} before reading the new passage.
```

### The kit composer

Fills the four fixed page templates from the founding design — leader guide, family observation sheet, recall activity, leader observation grid — with the selector's output.

The **leader guide opens with heart preparation, before any logistics**: a prayer prompt and an instruction to read the passage devotionally once — as a hearer, not yet as a teacher — before reviewing the plan. The leader is leading worship, not delivering a lesson; the page order should say so. Layout templates are static; only slot content varies. Output is print-ready (and hand-copyable: every kit must degrade gracefully to "copy these five lines onto index cards").

The observation grid's columns are the six evidence codes, not the eight dimensions — the taxonomy stays out of the leader's way at the table.

---

## MVP sequencing

1. **Freeze the dimension model** (this document) — the schema everything else keys on.
2. **Author the library for one book** (suggested: a Gospel), pericope by pericope, AI-drafted and human-reviewed.
3. **Kit composer with fixed templates** — even manual selection producing a beautiful printable kit is already useful.
4. **Member record + reflect flow** — confirmation UI that turns marks and photos into `EvidenceItem`s.
5. **Selector/scheduler** — once records exist to select against.

Steps 2–3 alone constitute a shippable paper product.

## Open questions

- Default reading sequence for the first library: single Gospel start (Mark or Matthew) vs. a Genesis + Gospel pair.
- Age tiers: are four tiers right, and where are the boundaries?
- Bilingual content (中文/English): authored per language, or translated pairs with shared indexing? (The confessional standard has established Chinese translations — 威斯敏斯特信条 — so the guardrail itself is not a localization obstacle.)
- How the family notebook page interacts with the kit — preprinted spread in the kit vs. fully handwritten.
