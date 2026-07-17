# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository state

Pre-implementation. There is no source code, build system, dependency manifest, or test suite yet — only `README.md` (a stub) and the design documents in `docs/`. Do not invent build/test commands; when the first code lands, add the real ones here.

## What the product is

Scripture Loom is **a preparation and reflection system for unplugged family Bible study** — not an app used *during* worship. The design docs are the spec:

- `docs/core_principles.md` — distilled principles and methods reflecting current decisions; read this first, it wins where documents disagree.
- `docs/design-kit_generator.md` — the eight fluency dimensions (D1–D8, the product's schema) and the kit generator architecture: static human-reviewed content library + personal selector/scheduler; no content generation at session time.
- `docs/motto.md` — the Bible Fluency Method, the pedagogy the product serves.
- `docs/unplug_assitant.md` — the invisible-assistant product design and MVP scope. (Filename is misspelled; leave it unless renaming is requested.)
- `docs/feature-listening_transcription.md` — the optional audio/transcription evidence-capture feature. **Explicitly low priority** (owner decision, 2026-07): high cost, and the unplugged paper workflow is preferred and must stand on its own without it. Do not scope MVP work around transcription.

## The constraint that governs design decisions

> **Prepare digitally. Gather physically. Reflect intelligently.** The app prepares the table, then leaves the room.

Three phases, and the phase determines whether computing is allowed at all:

- **Prepare** (app active) — leader picks a passage; app generates objective, review questions, discussion prompts, 2–3 observation targets, and a printable paper session kit.
- **Gather** (app invisible) — paper, Bibles, pencils, index cards. Screens are absent. Audio recording, if used, is passive and out of sight.
- **Reflect** (app active) — leader photographs paper artifacts and expands shorthand marks (`G-C★`) into records. Target: ~5 minutes, not 20.

Anything proposed as a during-session feature is presumptively wrong: live AI questions, live scoring, live transcript, dashboards, per-participant tablets, notifications, gamification. `docs/unplug_assitant.md` §16 is the explicit denylist.

## Design invariants to preserve

**Paper is the primary artifact, not a fallback.** The deliverable of preparation is a printable kit; children's written cards and the Family Bible Fluency Notebook are stronger evidence than a transcript. Audio is *secondary* evidence; automatic transcription is an *optional enhancement*. Don't let a feature invert that hierarchy.

**Worship, not academy — and content is not theologically agnostic.** The app trains fluency (the natural means); revelation belongs to the Spirit; the leader's faith is the unautomatable factor, so the prepare phase addresses the leader's heart before logistics. All Bible-study content (questions, activities, any AI-drafted material) is anchored to the Westminster Confession, especially Chapter 1 on Scripture (infallibility, inerrancy, sufficiency; Scripture interprets Scripture) — inject it as a constraint when drafting, check conformity when reviewing. Theology is not configurable in v1.

**Evidence, never judgment.** Records state observable behavior ("could not remember which book Jesus quoted"), never character or spiritual conclusions ("lacks faith", "spiritually mature"). AI proposes; the leader confirms before anything enters a permanent record.

**The durable value is the longitudinal per-member fluency record**, not any single session's output. Transcripts and photos are inputs that get discarded; confirmed evidence persists.

**The leader is not a data-entry clerk.** During a session they make marks of a few characters. Anything requiring more typing during the gathering is a design failure.

## Privacy requirements (non-negotiable — recordings contain children)

Guardian control over children's data; encryption in transit and at rest; configurable audio retention with easy deletion; no model training on family recordings by default; leader review before any record is permanent. **No permanent child voiceprints** — speaker labels are temporary and mapped to members by the leader after each recording.

## Audience and locale

Mainland-China families are a first-class target: Chinese/English code-switching in speech, mainland ASR providers (Alibaba Fun-ASR, Volcano Engine, Tencent Cloud, Baidu, iFlytek), and in-China storage/processing where appropriate. Batch transcription of recorded files is authoritative over real-time.
