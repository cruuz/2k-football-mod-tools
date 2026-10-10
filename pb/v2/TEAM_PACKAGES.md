# How to add a team package (SOFTDRINK offense v2)

Every team book = the shared core (`pb/v2/core.json`) + one team package (`pb/v2/teams/<TEAM>.json`).
The generator (`pb/v2/build.py`) turns both into `data/playbooks/softdrink_<team>_modern.2k5book`
(NYG: `softdrink_giants_modern.2k5book`). Plays come only from the concept engine
`mod_editor/core/nfl2k5_offense_concepts.py`, so anything you can name there is safe to use.
Team codes are the engine's book names: ARZ, SD, OAK and STL are Arizona, the Chargers, the Raiders and the Rams.

## Fields you can edit

| field | what it does |
|---|---|
| `identity`, `staff`, `key_players` | text only (book notes). Keep the source in `sources`. |
| `depth_step` | 0, 1 or 2 yards added to intermediate and deep stems for this team (deeper vertical offenses). |
| `formations.prefer` | optional sets (see `optional_formations` in core.json) this team gets before the tendency score picks the rest. |
| `formations.avoid` | sets this team never gets (core or optional). |
| `boost` | `{concept: n}` moves a concept up `2n` places in every menu that lists it (more menu slots, more CPU calls). |
| `preference_shift` | `{concept: -1 or +1}` changes the play's CPU preference (bits 9-11): -1 = called more, +1 = less. |
| `menu_adds` | `{formation: [concept, ...]}` adds concepts to one formation's menu (after its first two calls). |
| `signature` | team plays: `{"formation", "concept", "name", "overrides"}`; they go third in the menu and never leave it. |
| `formation_ratings` | `{formation: [short, medium, long]}` overrides the core CPU situation ratings (formation flag bits 21-29, 0-7; 1 is best in normal play). Change them only with the call-mix check below: one rating moves the whole personnel group's share. |
| `node_cap` | a lower offense node cap for this team (none today: with p48d's v2 defense every team uses the core cap of 2,300; the old-generator defense needed DAL 1,750, NYJ 1,782, SD 1,810). |
| `keep_in_menu` | `{formation: [concept, ...]}` replaces the core list of gadgets that never leave their menu (core: Flea Flicker in I-Form Pro, End Around in Singleback Doubles, toss Reverse in Singleback Doubles Tight). Keep the Flea Flicker: Noah asked for it in every book. GB, NYJ and TB drop the Reverse to fit their play slots or node cap. |

### Added by p6s (beta 77): whole-book control and CPU personnel design

| field | what it does |
|---|---|
| `formations.exact` | the book's whole formation list in book order, one per ordinary slot (replaces the tendency choice). |
| `menus` | `{formation: [entry, ...]}` authors a formation's whole menu in priority order (first = base call, first three = default audibles). An entry is a concept name or `{"concept", "name", "overrides"}`; named entries are team plays and never leave the menu. Core gadgets in `keep_in_menu` still stay. |
| `personnel_groups` | `{stock group name: {"twin_of": "11", "code": 9, "name": "Kings Long"}}` turns a spare personnel group record (one no retained formation uses: never 5 Wide, which holds the Hail Mary, or Jokers, which holds the Clock) into a twin: the same eleven players as the stock group of `twin_of`, its own CPU lottery code 0..10 and label. Replaces the core default (`personnel_groups_default`: Flush, else Queens, becomes Kings Long at code 9). |
| `formation_groups` | `{formation: {"own": group, "mask": [group, ...]}}`: the group that owns the formation (the CPU draws a formation only from the picked group's owners) and every group it belongs to (the CPU's group weight is the mean rating of all members; a human can pick the formation with any of them). Mask groups must field the same eleven players. Replaces `formation_groups_default`. |

How the CPU uses them (native code, see `pb/v2/selection_model.py`): the down and distance give a target code (third and 8+:
9-10; first and 10: 3-5 at half distance); each group's weight is (distance curve x mean member rating) cubed; then a
formation is drawn from the group's owners by rating; shotgun sets weigh 0.05 beyond the 10 in retail (job a4 makes
that a per-team weight). So: put a twin of 11 personnel at code 9 for third and long, give shotgun sets their own
owner group if early downs should stay under centre, and let under-centre members raise a group's mean.

Fit a team's ratings and groups to its 2025 charting with `pb/v2/fit_cpu.py --image RETAIL --team XX --write`
(data `pb/research/situational_2025.json`, built by `pb/research/situational_2025.py`), then rebuild and check the
call mix natively. TEN (`pb/v2/teams/TEN.json`) is the worked example: three twins (Kings Early 5, Kings Long 9,
Ace Long 8), 21 explicit formations, Daboll menus with team plays, ratings from the fit.

`overrides` (all optional): `routes` `{label: spec}` replaces one player's job, `reads` `[labels]` sets the read
order, `depth_step`, `direction: "weak"` flips a run, `name`, `preference`.
Labels are counted from the outside on each side: `S1 S2 S3` strong side (more receivers, tie: the tight end's
side), `W1 W2` weak side, `B` the back, `B2` the fullback, `Y` the attached tight end.
Specs: `["route", "Dig", 12]`, `["check", "Back Flat"]` (block, then release), `["block"]`, `["stalk"]`,
`["leak", "Drag", 1.2, 2]` (block 1.2 s, then a 2-yard drag), `["fake", hole, ["route", "Back Flat"]]`.
Route names: `nfl2k5_offense_concepts.ROUTES` (39, each copied from a retail chain).

## Rules the generator enforces (do not fight them)

1. A signature must change at least one assignment against the core design, or it merges into the core play.
2. Every target finishes at least 1.25 yards in front of the QB's release (the engine lengthens the stem if not);
   back screens start 2 yards in front of a 9-yard drop; an end around needs the QB under centre and a slot
   within 9.6 yards (retail exchange envelope). A concept that cannot run in a formation is skipped, not faked.
3. The book keeps its exact ordinary formation and play counts; menus stay 8-12 plays.
4. The compiled offense stays at or under `offense_total_node_cap` (2,300 since p6s; the v2 defense needs about 400-570 nodes and kickoff returns 78 of the 3,500).
5. No pre-snap motion exists in this engine: do not describe jet motion; use the End Around.
6. CPU personnel choice is native: a personnel group's weight is the mean rating of every formation whose
   category mask carries it, cubed, and every shotgun or pistol set scores 0.05 outside the 10 (`0x207EF0`,
   byte `0x207F85` left as retail). So under-centre 10/00 sets are not in the core (they would take every
   3rd-and-long call from the shotgun sets), and tendency-filled extras stop at `max_gun_sets` (five shotgun or
   pistol 11-personnel sets) before the leftover slots are filled.

## Workflow

CPU receiver targeting is applied automatically by `pb/v2/targeting.py` after
the concept and package overrides. Its source is `pb/research/targets_2026.json`:
2026 regular-season named targets, joined to the v0.5 build's main-roster depth
fields. `pb/research/targets_2026.py` records exact nflverse URLs, dates and
hashes. No 2025 fallback is used. The native read setup and evaluation scheduler
consume the order; live catchability and target scoring can override it.

Only existing direct reads in the same shallow (<8 yd), intermediate (8 to
<16 yd), or deep (16+ yd) band can trade places. Compatible reads descend by
observed role share; equal shares retain their authored relative order.
Compatible zero-share reads move behind
positive-share reads and keep their relative order. Delayed releases, screens,
gadgets, nonstandard pass modes and moving pockets retain their jobs and order.
Missing or exhausted roster position pools have zero weight. Their native
substitute identity is unresolved and is labeled explicitly in measurements.
The four encoded reads keep their membership; any fifth metadata read stays
outside that permutation. Routes, blocking, drop, timing and concept depth
progression are preserved. Per-team catalogs pin the source data hash.
Named signatures keep separate play identities when retargeting makes their
chains equal to the core. Compiled node sharing remains intact. Their old
reads are not restored. The native measurement checks all baseline named plays.

Run `tools/b77/tgt_target_probe.py` for native mechanism controls or with
`--before DIR --after DIR` for paired component distributions. Those distributions
use supplied openness and release opportunities, not a live game prediction.

```
export PYTHONDONTWRITEBYTECODE=1 RETAIL='/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso'
python3 pb/v2/build.py --image "$RETAIL" --team KC          # dry run, prints formations / plays / links
python3 pb/v2/build.py --image "$RETAIL" --write             # all 32 packs, catalogs, manifests
python3 pb/defense/build.py --workers 2                      # defense packs pin the offense compile: always rerun
python3 pb/v2/pins.py --image "$RETAIL" --xbe "$XBE" --write # screen pins for screen timing D
python3 pb/v2/verify.py --image "$RETAIL" --v05 "$V05" --xbe "$XBE" --books /tmp/v2books
python3 pb/v2/selection_model.py /tmp/v2books/*.play       # the call-mix check: CPU personnel per situation
python3 tests/mod_editor/test_nfl2k5_offense_concepts.py && python3 tests/mod_editor/test_nfl2k5_modern_league.py
```

Check the result in `pb/v2/catalogs/<TEAM>.json` (formations, donors, menus, headers, node budget) and render
diagrams with `python3 pb/v2/diagrams.py --out sheet.png`. Real-world facts (staff, players, tendencies) need a
source in `sources`; football choices are DESIGN. Nothing here is a gameplay witness: Noah checks plays in game.
