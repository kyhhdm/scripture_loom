# Kit Generator Prototype

Executable proof of the pipeline in `docs/design-kit_generator.md`:

```text
content_bank.json  (static, human-reviewed content: pericope × dimension × age tier)
family.json        (member records: evidence history, reading sequence, used items)
        ↓
selector.py        (deterministic selection: spaced review, dimension rotation,
                    weakness targeting, activation-stage quest scaling)
        ↓
generate_kit.py    (composes the four-page kit as markdown)
```

No LLM, no network, no dependencies — Python 3 stdlib only. Personalization is
selection over static content, never generation.

## Run

```bash
python3 generate_kit.py                 # print the kit for the next passage
python3 generate_kit.py -o kit.md       # write it to a file
python3 -m unittest test_selector -v    # run the tests
```

`sample_output.md` is a checked-in example of the generated kit.

## What it demonstrates

- **Passage** comes from the family's reading sequence (continuous reading).
- **Review questions** target dimensions where members marked `△`/`?` last time
  (Liberty's shaky event order and vocabulary drive the Matthew 4 review picks).
- **Observation targets** (max 3, never the leader) combine weakness and staleness.
- **Quests scale to activation stage**, derived from each member's unprompted-question
  history: full quest → category only → "write your own" → omitted. Edit
  `family.json` (add unprompted `Q` evidence for Grace) and regenerate — her
  quest slip changes. That behavior is the central acceptance test.
- **Only `published` items** are selectable; used items are not re-picked for
  discussion; personalized lines are templated from evidence, not generated.

## Deliberately out of scope

Reflect-phase capture (marks/photos → EvidenceItem), print layout (see the HTML
artifact samples), the real content bank (this one covers three pericopes), and
any persistence of `used_item_ids` after a session (append the kit's listed ids
manually for now).
