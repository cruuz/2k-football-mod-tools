# The module agent charter

**Every brief for work on a game module references this file instead of restating it.**
A brief says what to build, on which module, and what evidence the result must carry. It does
not repeat the gates, the commit rules, the retail-free rule, the shared-file rules or the
report shape: they are here, they are the same for every agent, and restating them in fourteen
briefs is fourteen chances to state one of them differently.

If a brief contradicts this file, the brief wins and should say that it does, in one line, with
the reason. Silence means this file applies.

---

## 1. Read these, in this order, and stop

1. `AGENTS.md` — the contract boundary and the frozen files.
2. This charter.
3. `docs/product/GAME_MODULE_CONTRACT.md` — the normative spec, when you are writing a lane.
4. `docs/product/ADDING_A_GAME_MODULE.md` — the steps, when you are adding a module.
5. The **one** module document for the game you are touching
   (`docs/product/<GAME>_MODULE.md`), and nothing else under `docs/product/`.

`docs/product/` holds 81 files and 1.2 MB. Reading it whole is roughly 300,000 tokens and
almost all of it is about a game you are not touching. Search it; do not sweep it.

## 2. Do not re-measure what has been measured

Facts about a disc, a container or a format are recorded, with their provenance, in files meant
to be read rather than regenerated:

| Question | The file that already answers it |
|---|---|
| What is on disc `<SERIAL>`, container by container | `docs/owner/disc_maps/<SERIAL>.<label>.map.md` |
| How far the shipped readers get on disc `<SERIAL>` | `docs/owner/scoping/readiness/<SERIAL>.<label>.readiness.json` |
| The same, across the fleet, in one table | `docs/owner/scoping/READINESS_SUMMARY.md` |
| What a module claims, and on what rung | `mod_editor/capabilities/registry.v1.json` |
| What a module ships and how many rows it has | `mod_editor/games/<game>/pins.json` |
| A container's schema as measured | `docs/product/measured/<game>/*.json` |

The JSON files are the source and the Markdown is rendered from them; quote the JSON. If a
number you need is not in one of them, measure it **once**, write it into the relevant file with
its evidence tag, and say in your report that you added it. Three agents measured the
preload-cache semantics of the same disc separately in one day; that is three times the tokens
for one fact, and three chances to record it differently.

**Evidence tags are not decoration.** `[M]` measured, by you, on the artefact named. `[S]`
sourced from a named document. `[A]` assumed. A claim with no tag is read as `[A]`.

## 3. Retail-free, without exception

Names, offsets, lengths, counts, schema field names and widths, and digests. **Never payload.**
No decoded pixel, no game string, no audio sample, no database record, no save file, no ISO,
and nothing extracted from one, enters the repository — not in a test, not in a fixture, not in
a docstring, not in a commit message, and not in a report. A test builds the bytes it looks at.

A lane that cannot be proved on a source it synthesises is not ready to be committed.

## 4. The gates

Run these before every commit, not just the last one. They are cheap; a rebase that discovers a
broken gate five commits later is not.

```bash
export QT_QPA_PLATFORM=offscreen
python -m mod_editor.games conformance --game <game>      # for each game you touched
python -m mod_editor.games fragments <game> --check       # for each game you touched
python -m mod_editor.games pins --check
python mod_editor/capabilities/validate_registry.py --skip-file-checks
```

If you touched the registry, the allowlist, a packaging checker or a count pin, also run the
release gate against a scratch directory outside the worktree, and delete it afterwards:

```bash
python packaging/stage_release.py packaging/release-allowlist.txt "$STAGE" .
python packaging/check_2k5_mod_studio_release.py "$STAGE"
python "$STAGE/packaging/check_2k5_mod_studio_runtime.py"
```

**Run a validator you changed inside the staged tree, not only in the checkout.** `tests/` is
not shipped, so a validator that imports a test framework passes in a checkout and fails in a
release. Four validators in this repository have that defect today; do not add a fifth.

Test files are `tests/mod_editor/test_*.py`, each runnable on its own
(`PYTHONPATH=. python tests/mod_editor/test_<name>.py`). Run the ones your change can affect —
the module's own, the format packages it imports, and the packaging suites if you touched
packaging. The whole suite belongs on the shared runner, not in your loop.

## 5. Shared files: touch your own package, and one command for the rest

Everything a game needs lives under `mod_editor/games/<game_id>/` and
`tests/mod_editor/test_<game_id>_*.py`.

Twelve upstream files still carry per-game facts — the canonical registry, the coverage rule,
both runtime gates, the release allowlist, two packaging tests, the capability validator's count
pins, and four documents that print a row count in prose. **Never edit any of them by hand.**
`tools/registry_add_rows.py` computes every edit, asserts each one matches exactly once, and
writes nothing if any assertion fails:

```bash
python3 tools/registry_add_rows.py --game <game> --row rows/<row>.json \
    [--widen <surface>] [--module <dotted.module>] \
    --allowlist-fragment mod_editor/games/<game>/allowlist.fragment.txt [--dry-run]
python -m mod_editor.games fragments <game> --write
```

Then commit **those files in their own commit**, separately from your lane work. Six branches
that each hand-edited the same sixteen files spent as much of a day being rebased as they spent
being written, and every union of two hand edits had to be read line by line for duplicates. A
single mechanical commit rebases cleanly or conflicts loudly; a hand edit does neither.

If you believe an upstream file needs a change the tool cannot make, **stop and say so in your
report**. Do not make it.

## 6. What a lane owes

One lane is one registry row and one entry in the game's `validators.json`. It owes:

- a **catalogue** tool, a **patcher** and an **independent verifier** that imports none of the
  patcher and fails on a byte outside the declared ranges;
- a **synthetic source** it can be proved on with no game data, and a known-good edit;
- **refusals of one sentence that name the fix**, re-raised verbatim, never re-worded;
- a **classification its evidence earns** — `read-only-mapped`, `extract-only`,
  `offline-writer-proved`, `runtime-proved` — and not one rung higher. `unknown` stays hidden.

Its validator is not a new script. Add the lane to `mod_editor/games/<game>/validators.json`
and write the two wrappers; `tools/validate_game_lane.py` is the behaviour, and the pass token
is derived from the game id and the lane name:

```bash
python3 tools/validate_game_lane.py --game <game> --list
python3 tools/validate_game_lane.py --game <game> --lane <lane>
python3 tools/validate_game_lane.py --game <game> --all     # the harness runs once, not per lane
```

Shared formats belong in `mod_editor/games/_formats/`, not in the first module that needed
them. A game imports a format package; it never imports another game. If you find yourself
wanting a sibling module's reader, move the reader and leave a compatibility import behind.

## 7. Output discipline

Tool output is not free: something reads it. The Madden 09 conformance harness prints 544 lines
and 56 KB, and ten validators each printed all of it. Prefer the summary; keep the detail for a
failure.

- Do not paste a tool's whole output into a report. Paste the line that carries the verdict.
- Do not write a JSON dump into the repository that exists only so an agent can read it back.
- When you build a tool that walks a disc, give it a bounded mode: EA's container reader takes
  `max_output`, and a 64-byte window answers "what format is this member" as well as a full
  decode does, at a fraction of the time.

## 8. Commits

- Prose messages: what changed, and **why it was wrong before**. Small steps.
- **No attribution trailer, and no assistant named as author or committer.** The repository
  owner's git identity is configured locally; `AGENTS.md` is the rule and it is not negotiable.
- A contract change (`mod_editor/games/contract.py` and the files pinned beside it) is committed
  **alone**, following the procedure in `AGENTS.md`. Never with feature work.
- Registry/allowlist/pin commits are separate from lane commits, so an integrator can take one
  without the other.

## 9. The report you owe

Short, and in this shape. Everything else is noise.

1. **What you did** — one paragraph.
2. **What you proved, and how** — the gate lines, verbatim, with their PASS tokens; the
   classification each row earned and the evidence behind it.
3. **What you did not prove** — plainly. "Not tested in game" is an acceptable and expected
   answer; a claim above its evidence is not.
4. **Every file you changed**, by path, split into the module's own files and anything upstream.
5. **What the next agent should not have to rediscover** — facts you measured, and where you
   wrote them down.
