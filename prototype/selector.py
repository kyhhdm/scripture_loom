"""Kit selector: reads the static content bank and a family's member records,
returns the selections for one session kit.

Implements the pipeline from docs/design-kit_generator.md:
  content library (static) + member records -> selector/scheduler -> kit.
Deterministic; no generation at kit time.
"""

DIMENSIONS = {
    "D1": "People & Places",
    "D2": "Event Sequence",
    "D3": "Vocabulary",
    "D4": "Memory",
    "D5": "Connections",
    "D6": "Questions",
    "D7": "Interpretation",
    "D8": "Application",
}

WEAK = ("△", "?")
ROLES = ["Reader (second reading)", "Question keeper", "Word finder",
         "Memory keeper", "Recorder (notebook page)"]

RECENT_SESSIONS = 6  # window for activation and weakness signals


# ---------- helpers ----------

def _published(bank, passage=None, type_=None):
    for item in bank["items"]:
        if item["review_status"] != "published":
            continue
        if passage and item["passage"] != passage:
            continue
        if type_ and item["type"] != type_:
            continue
        yield item


def available_dimensions(bank, passage_id):
    """Dimensions with >= 1 published item for this passage (any type)."""
    return {item["dimension"] for item in _published(bank, passage=passage_id)}


def _recent_evidence(family):
    for session in family["sessions"][-RECENT_SESSIONS:]:
        for ev in session["evidence"]:
            yield ev


def _tier_fits(item, member_tier):
    return item["age_tier"] in (member_tier, "all")


# ---------- selection steps ----------

def next_passage(bank, family):
    """Next unstudied pericope in the family's reading sequence."""
    studied = {s["passage"] for s in _normal_sessions(family)}
    for pid in family["reading_sequence"]:
        if pid not in studied:
            return next(p for p in bank["pericopes"] if p["id"] == pid)
    raise ValueError("Reading sequence exhausted — extend it.")


def activation_stage(family, member_id):
    """Stage 1-4 from unprompted questions in the recent window.
    0 -> 1 (full quest), 1 -> 2 (category only), 2-3 -> 3 (write your own),
    4+ -> 4 (no prompt needed)."""
    unprompted = sum(
        1 for ev in _recent_evidence(family)
        if ev["member"] == member_id and ev["code"] == "Q" and not ev["prompted"]
    )
    if unprompted == 0:
        return 1
    if unprompted == 1:
        return 2
    if unprompted <= 3:
        return 3
    return 4


def weak_dimensions(family):
    """Dimensions where any member showed △/? (or a U code) recently, most-marked first."""
    counts = {}
    for ev in _recent_evidence(family):
        if ev["quality"] in WEAK or ev["code"] == "U":
            counts[ev["dimension"]] = counts.get(ev["dimension"], 0) + 1
    return sorted(counts, key=lambda d: (-counts[d], d))


def select_review_questions(bank, family, limit=3):
    """Spaced review from studied passages, weak dimensions first."""
    studied = [s["passage"] for s in family["sessions"]]
    weak = weak_dimensions(family)
    candidates = [i for p in studied for i in _published(bank, passage=p, type_="question")]

    def rank(item):
        dim_rank = weak.index(item["dimension"]) if item["dimension"] in weak else len(weak)
        used = item["id"] in family["used_item_ids"]
        return (dim_rank, used, item["id"])

    return sorted(candidates, key=rank)[:limit]


def select_observation_targets(family, available_dims, limit=3):
    """(member, dimension) pairs: weakness first, then staleness; never the leader;
    at most two targets per member. Only dimensions in `available_dims` (those the
    upcoming passage publishes content for) are eligible."""
    members = [m for m in family["members"] if not m["leader"]]
    weakness, last_observed = {}, {}
    for idx, session in enumerate(family["sessions"]):
        for ev in session["evidence"]:
            key = (ev["member"], ev["dimension"])
            last_observed[key] = idx
            if ev["quality"] in WEAK or ev["code"] == "U":
                weakness[key] = weakness.get(key, 0) + 1

    n_sessions = len(family["sessions"])
    scored = []
    for m in members:
        for dim in DIMENSIONS:
            if dim not in available_dims:
                continue
            key = (m["id"], dim)
            staleness = n_sessions - 1 - last_observed.get(key, -1)
            score = weakness.get(key, 0) * 10 + staleness
            scored.append((-score, m["id"], dim))

    targets, per_member = [], {}
    for _neg, member_id, dim in sorted(scored):
        if per_member.get(member_id, 0) >= 2:
            continue
        targets.append({"member": member_id, "dimension": dim})
        per_member[member_id] = per_member.get(member_id, 0) + 1
        if len(targets) == limit:
            break
    return targets


def select_discussion_questions(bank, family, passage, targets, limit=4):
    """Questions for the new passage: target dimensions and D6 first, unused first,
    tier must fit some family member."""
    tiers = {m["age_tier"] for m in family["members"]} | {"all"}
    preferred = [t["dimension"] for t in targets] + ["D6"]
    candidates = [i for i in _published(bank, passage=passage, type_="question")
                  if i["age_tier"] in tiers]

    def rank(item):
        dim_rank = preferred.index(item["dimension"]) if item["dimension"] in preferred else len(preferred)
        used = item["id"] in family["used_item_ids"]
        return (used, dim_rank, item["difficulty"], item["id"])

    chosen, seen_dims = [], set()
    for item in sorted(candidates, key=rank):  # one question per dimension
        if item["dimension"] in seen_dims:
            continue
        chosen.append(item)
        seen_dims.add(item["dimension"])
        if len(chosen) == limit:
            break
    return chosen


def select_activity(bank, family, passage):
    """Main activity for the youngest reading tier present, plus a pre-reader
    variant if the family needs one."""
    order = {"pre_reader": 0, "child": 1, "youth": 2, "adult": 3}
    tiers = sorted({m["age_tier"] for m in family["members"] if not m["leader"]},
                   key=order.get)
    activities = sorted(_published(bank, passage=passage, type_="activity"),
                        key=lambda i: (i["id"] in family["used_item_ids"], i["id"]))
    main = next((a for a in activities
                 if a["age_tier"] in tiers and a["age_tier"] != "pre_reader"), None)
    young = next((a for a in activities if a["age_tier"] == "pre_reader"), None) \
        if "pre_reader" in tiers or "child" in tiers else None
    return main, young


def select_quests(bank, family, passage):
    """One quest per member, scaled to activation stage. The leader always
    receives a full adult quest — it doubles as modeling."""
    quests, taken = [], set()
    items = sorted(_published(bank, passage=passage, type_="pre_reading_quest"),
                   key=lambda i: (i["id"] in family["used_item_ids"], i["id"]))

    def pick(member):
        for item in items:
            if item["id"] not in taken and _tier_fits(item, member["age_tier"]):
                taken.add(item["id"])
                return item
        return None

    for member in family["members"]:
        stage = 1 if member["leader"] else activation_stage(family, member["id"])
        item = pick(member) if stage <= 2 else None
        if stage == 1:
            text = item["body"] if item else None
        elif stage == 2:
            text = (item["category"] + "  Write your own question, then listen "
                    "for the answer.\n  My question: ________________?") if item else None
        elif stage == 3:
            text = "Write your own quest before we read. What will you listen for?"
        else:
            text = None  # stage 4: no prompt needed
        quests.append({
            "member": member["id"], "stage": stage, "text": text,
            "item_id": item["id"] if item else None,
            "leader": member["leader"],
        })
    return quests


def personalized_lines(family):
    """Templated composition from last session's notable / unresolved evidence."""
    if not family["sessions"]:
        return []
    names = {m["id"]: m["name"] for m in family["members"]}
    lines = []
    for ev in family["sessions"][-1]["evidence"]:
        name = names[ev["member"]]
        if ev["code"] == "Q" and ev["quality"] == "★":
            lines.append(f'Last session, {name} asked: "{ev["note"]}" — '
                         "return to it together if there is a natural moment.")
        elif ev["quality"] == "?":
            lines.append(f"Review with {name}: {ev['note']}")
    return lines


def assign_roles(family):
    """Rotate roles across non-leader members by session count."""
    members = [m for m in family["members"] if not m["leader"]]
    offset = len(family["sessions"])
    return [{"role": role, "member": members[(offset + i) % len(members)]["name"]}
            for i, role in enumerate(ROLES)]


# ---------- the kit ----------

def build_kit(bank, family):
    passage = next_passage(bank, family)
    available = available_dimensions(bank, passage["id"])
    targets = select_observation_targets(family, available)
    review = select_review_questions(bank, family)
    discussion = select_discussion_questions(bank, family, passage["id"], targets)
    main_act, young_act = select_activity(bank, family, passage["id"])
    quests = select_quests(bank, family, passage["id"])
    verse = next(iter(_published(bank, passage=passage["id"], type_="memory_verse")), None)
    narration = next(iter(_published(bank, passage=passage["id"], type_="narration_prompt")), None)

    selected = [i["id"] for i in review + discussion]
    selected += [a["id"] for a in (main_act, young_act, verse, narration) if a]
    selected += [q["item_id"] for q in quests if q["item_id"]]

    return {
        "family": family["name"],
        "passage": passage,
        "review_questions": review,
        "observation_targets": targets,
        "discussion_questions": discussion,
        "activity": main_act,
        "activity_young": young_act,
        "quests": quests,
        "memory_verse": verse,
        "narration_prompt": narration,
        "personalized_lines": personalized_lines(family),
        "roles": assign_roles(family),
        "selected_item_ids": selected,
    }


def _normal_sessions(family):
    return [s for s in family["sessions"] if s.get("kind", "normal") == "normal"]


def due_zoom_out(sections, family):
    """The Section to zoom out on, or None. Fires when the most-recently-studied
    pericope is a section's last_pericope and no zoom_out session exists for it."""
    normal = _normal_sessions(family)
    if not normal:
        return None
    last_pid = normal[-1]["passage"]
    zoomed = {s["section"] for s in family["sessions"] if s.get("kind") == "zoom_out"}
    for section in sections:
        if section["last_pericope"] == last_pid and section["id"] not in zoomed:
            return section
    return None


def _section_pericope_ids(section, order):
    """Pericope ids in a section, in reading order (order = bank pericope ids)."""
    i, j = order.index(section["first_pericope"]), order.index(section["last_pericope"])
    return order[i:j + 1]


def _section_of(sections, bank, pericope_id):
    order = [p["id"] for p in bank["pericopes"]]
    for section in sections:
        if pericope_id in _section_pericope_ids(section, order):
            return section
    return None


def arc_recap(sections, bank, family):
    """'The story so far' within the current section: its title and the ordered
    titles of its pericopes the family has already studied. Pure derived."""
    passage = next_passage(bank, family)
    section = _section_of(sections, bank, passage["id"])
    if not section:
        return None
    order = [p["id"] for p in bank["pericopes"]]
    title_by = {p["id"]: p["title"] for p in bank["pericopes"]}
    section_ids = _section_pericope_ids(section, order)
    studied = {s["passage"] for s in _normal_sessions(family)}
    studied_ids = [pid for pid in section_ids if pid in studied]
    return {
        "section": section["title"],
        "studied": [title_by[pid] for pid in studied_ids],
        "position": f"{len(studied_ids)} of {len(section_ids)}",
    }


def build_zoom_out_kit(bank, family, sections, section):
    """A derived consolidation session over a completed section. No new passage.
    The family physically shuffles the printed cards and reorders them; the kit
    carries the cards in reading order plus the correct order for the leader."""
    order = [p["id"] for p in bank["pericopes"]]
    by_id = {p["id"]: p for p in bank["pericopes"]}
    section_ids = _section_pericope_ids(section, order)
    studied = {s["passage"] for s in _normal_sessions(family)}

    cards = [{"id": pid, "title": by_id[pid]["title"], "ref": by_id[pid]["ref"]}
             for pid in section_ids]
    memory_recall = [i for i in _published(bank, type_="memory_verse")
                     if i["passage"] in section_ids and i["passage"] in studied]

    return {
        "family": family["name"],
        "kind": "zoom_out",
        "section": section["title"],
        "section_id": section["id"],
        "sequence_cards": cards,
        "correct_order": [c["id"] for c in cards],
        "memory_recall": memory_recall,
        "throughline_prompt": f"In one sentence, what was “{section['title']}” about?",
        "roles": assign_roles(family),
        "selected_item_ids": [i["id"] for i in memory_recall],
    }
