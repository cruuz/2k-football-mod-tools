# Handoff: the update after Beta 42

**Date:** 2026-08-13
**Branch:** `cursor/ship-beta-38` (name is stale; it carries Beta 42 + WIP)
**Shipped:** `beta-42` = 2K5 `v1.0-RC65` / APF `0.1.0-alpha.74`
**HEAD when written:** `24d4ad0`

**Do not cut a release until every item below is finished.** Noah's explicit
instruction: all of it lands together, however many days it takes. The shipped
Beta 42 is stable enough for users to wait on.

---

## Read this first

Five releases shipped in one day (38 → 42), every one from a user screenshot.
Four of them were the same defect shape: **a mechanism was built and then not
wired to the thing that needed it.**

| Release | The unwired mechanism |
|---|---|
| 39 | `PAYLOAD_SCHEMA` — Fine-tune Plays never reached a project |
| 39 | the membership panel was never reached by a page refresh |
| 40 | `Nfl2k5ProductVisualCatalog` — sessions never reached the extended catalog |
| 41 | `quantize_levels_to_vc_lz_bound` — four importers never used it |

**Before assuming a helper is in use, grep for its own name.** A constant with
one definition and zero references is a feature that does not exist.

Beta 42 added a second lesson. The Beta 41 guard test hard-coded a list I had
typed from a sweep truncated by `head -12`, so the test agreed with the
omission and reported success. **A check that agrees with the mistake is worse
than no check.** Derive sets from the tree; do not trust a list.

---

## Work in progress, committed, NOT released

`24d4ad0` adds `mod_editor/core/nfl2k5_import_preflight.py` and its tests.

**Why it exists.** Beta 41/42 replaced a hard build failure with a palette
ladder that quantizes art down until it fits its fixed VC-LZ span. That is
lossy and it shipped silent. A user's jersey could lose 240 palette entries
with nothing said.

**What it does.** Runs the real quantizer and encoder against the real slot
contract *before* a build, per slot: fits as authored / reduced to N colours /
will not fit. Modelled: `torso`, `sleeve`, `pants` (512×256, 6 mips, 2 palettes
over one shared index chain) and `live_helmet` (256×256, 1 palette). Unmodelled
families are reported as unmodelled, never approximated.

Measured on the reporter's own files, against the pants bound 75,472:

| File | Result |
|---|---|
| Packers gold jersey 2048×1024 | fits as authored, 255 colours |
| Falcons red jersey 2048×1024 | **reduced to 16 colours** |
| Helmet atlas 1024×1024 | reduced to 64 colours |

**Still to do on it:**

1. **No UI.** Needs a "Check my images" action on the 2K5 uniform surface,
   run through `run_task` with progress. This is the whole point of it.
2. **Tests take 4 minutes** because the noise fixtures walk the entire ladder.
   Shrink them to 128×64 before this reaches CI.
3. Resolution is *not* what costs palette — the editor resizes to the slot
   either way. Distinct shade count is. Say that in the UI copy.

---

## Four investigations, all required, all equal priority

Noah wants these finished and fleshed out, not sampled. Each is **reverse
engineering with an unknown answer**, not implementation. Give each its own
workflow, shaped like the scorebug one already written (see below), and give
each an honest verdict: proved / partially proved with a named boundary / not
found. Do not let an unproved one leak into release copy.

### 1. Scorebug — a workflow is already running

**Run ID `wf_f34df8ea-d26`.** Script at
`~/.claude/projects/.../workflows/scripts/scorebug-modernization-wf_f34df8ea-d26.js`.
Read `journal.jsonl` in its transcript dir before assuming any agent returned
something useful.

**The goal, in Noah's words:** *"easy enough a 7 year old could go to it and be
like 'I want NBC or ESPN' and upload it."* A modern horizontal ESPN/MNF-style
bar, placeable on screen, with per-network templates. He is an expert and the
current scorebug panel confuses him — treat that as the bar to clear.

**What is already known — do not rediscover:**

- `reports/assets/scorebug_presentation_audit.json` (schema
  `vc_scorebug_presentation_audit/v1`) has `apf2k8` and `nfl2k5` sections.
- APF's scorebug is **seven SCNE components** in outer 1310 `global.iff`,
  already exported to glTF:

  | inner | name | meshes | tris | verts |
  |---:|---|---:|---:|---:|
  | 106 | `scorebug_bottombar` | 46 | 221 | 361 |
  | 131 | `scorebug_titlebar` | 5 | 31 | 35 |
  | 156 | `scorebug_team_logos` | 4 | 8 | 16 |
  | 235 | `scorebug_infobar` | 4 | 149 | 171 |
  | 250 | `scorebug_messages` | 2 | 14 | 16 |
  | 262 | `scorebug_blackbar` | 1 | 5 | 7 |
  | 360 | `scorebug_statbar` | 8 | 181 | 208 |

- Compiled descriptors `0x84EAD3F8..0x84EAD51B`, stride 44, factory
  `0x18FD4C05`. All seven rows share `0x84ABE4C8`. `scorebug_bottombar` carries
  `0x42C80000` = 100.0f.
- `composition_boundary`: no scorebug-named LAYT or MRKS peer exists; compiled
  behaviour composes these SCNE components.
- `runtime_replacement_visibility_proved` is **False**.
- 2K5 has three proved texture writers only: `score_buga` (346/53, 64×64),
  `shield_espn` (346/26, 128×64), `digital_font` (3/46, 128×128 — **global**,
  affects UI outside the scorebug).

**The single highest-value question:** this repo already round-trips
same-topology vertex POSITION edits into a verified copied volume for 77
stadium surfaces. If that machinery generalises to these SCNE components, then
moving and resizing the scorebug is reachable **without new format work**.
Settle that before designing anything.

### 2. Camera angles

Unlock the camera and add Madden-style presets; a default camera options
editor. Nothing in this repo has located camera data yet — start from zero.
Suggested first cuts: the presentation/broadcast camera enum in the frontend,
any float triples near the playcall/situation objects, and whether camera
choice is a save-file field or executable-resident.

### 3. Catching slider above 100

Find where the slider is clamped and whether raising it is meaningful or just
saturates downstream. **A slider that stores 120 and behaves like 100 is a
worse outcome than refusing** — prove the consumer actually reads past 100
before offering it. Slider inspection already exists (`gameplay_inspection.py`,
the APF gameplay bug map) — start there.

### 4. Franchise CPU draft bug

CPU teams cannot take any position in round 1. Find the position filter or
weighting in the draft logic. Likely the same class of problem as G12: a
consumer that gates on a table nobody has mapped. `APF_GAMEPLAY_BUG_MAP.md` is
where findings belong.

---

## Non-negotiables

- **Three OS.** Everything must hold on Linux, macOS (the reporter is on
  Tahoe), and Windows. CI covers all three but only runs on `main` and PRs —
  **a branch push runs nothing.** Verify locally and say so.
- **`python3 packaging/repin.py`** after touching `studio/session.py`,
  `studio/facade.py`, `core/providers.py`, or any `tools/` writer. Both runtime
  gates pin module hashes and refuse until re-synced. Preview, then `--apply`.
- **Both release gates** must pass on a staged tree, both products, before any
  release. `stage_release.py` then `check_*_release.py` then the staged
  `check_*_runtime.py`.
- **Never claim runtime behaviour without a witness.** Urianus's alpha.70
  report is the first runtime witness G12 ever had, and it *contradicted* a
  static reading the product had shipped as if it were safety. Static facts are
  not safety proofs.
- CI hydrates from the previous release's assets; repin `ci.yml` after the new
  assets exist.

## Community reporters

- **Urianus Magnus Ursulinus** — G12, the Save Project gap, the
  empty-formation runtime witness. Tests on Xbox and PS3.
- **davidhbui** — mask previews, the shoulder allocation budget study, endzone
  identification. His reports arrive as reproducible measurements; when he says
  he measured something, he did.
- The uniform importer on macOS Tahoe — modern NFL texture packs, 2026+ teams,
  fantasy and classic uniforms. His last build succeeded; his open issue is
  that 2K5 draws jersey numbers from **separate 64×64 digit textures**
  (`Jersey Digit 0–9`, `Arm / Shoulder Digit 0–9`, `Helmet Digit 0–9`,
  Nameplate Atlas — 31 components per uniform set, per set, editable), so art
  with numbers baked in doubles up. **The torso/pants slot copy still does not
  say this.** Add it.
