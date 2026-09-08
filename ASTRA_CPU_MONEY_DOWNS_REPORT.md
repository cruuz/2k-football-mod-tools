# CPU fourth downs and first downs, r65

EXPERIMENTAL / UNWITNESSED. Implemented an opt-in, three-level XBE owner:
Retail, Modern and Aggressive. It adds measured fourth-down attempts and
strengthens third/fourth-down preferences for supported primary routes and
viable targets at the marker. It does not force a throw into coverage or
guarantee a catch or conversion. No gameplay was witnessed and no game, GUI,
audio, network session or disc build was run.

The shared product files were protected by ASTRA_BRIEF.md. The complete
dispatcher, BuildPlan, three-level controls, four status dictionaries,
packaging and capability-registry handoff is in [WIRING.md](WIRING.md).
The core writer, CLI, assembly, replay evidence, budget and safety-gate union
are implemented here. Basic, Advanced and Experimental remain Retail.
**Recommendation:** Advanced with Modern explicitly selected for Noah's
first comparison. Aggressive is a comparison setting, not a default.

## PROVED: retail decision and its inputs

Evidence is the USA `default.xbe`, SHA-256
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`,
the read-only Ghidra corpus and bounded replay of the real instructions.
Numerical results are committed in
[nfl2k5_cpu_money_downs_replays.json](docs/mod_editor/nfl2k5_cpu_money_downs_replays.json).
No retail executable or PLAY resource is redistributed.

`20B180` is the category decision: `20AF80` decides whether to kick a field
goal (category 19), then `209CA0` decides whether to punt (category 17).
Otherwise it considers clock-management actions and calls `209FE0`, which
returns ordinary offensive categories 0 through 10. `20B2E0` calls this path
in ordinary phase 4; `20B670` subsequently commits the formation/play and has
native retry logic. Category selection is distinct from actual play selection.

| Input | Native evidence |
| --- | --- |
| Down and distance | `[E602EC]+4` is the down. `207950` copies LOS and marker vectors at context+10/+20 and calls `E92E0`, returning their signed forward separation in centimetres. One yard is 91.44 cm. |
| Field position | Context+18 is LOS z. `203370` computes distance to the opponent goal as `4572 - LOS_z * direction`. Direction is the sign in `[ [offense+8]+12 ]+4`; both directions are replayed. |
| Score | `205F40` subtracts opponent score from offensive score through each team's +8 statistics pointer. The team's first pointer leads to the opponent. |
| Time and quarter | `205F80` returns remaining half time: current quarter clock `[E6028C]+10`, adding configured quarter length `E602B0` in quarters 1/3, floored at zero. Quarter is `E602C4`. `205FE0` identifies late second-half time. `205F50` reads the team's native timing estimate `BF1240/BF1480`; timeouts also affect punt/FG branches. |
| Kicker/range | `18B120` resolves the kicker via native playbook/roster helpers, uses rating bytes +3A/+4B through `187A60/187AD0` and interpolation `1B0AE0`, and subtracts the native range offset. These are not a universal fixed-yard threshold. |
| Randomness | `20AC70` stores real `48B90` random draws into `BF1244/BF1484`. These cached values are used by `209CA0` and `209FE0`; they are not coach ratings or difficulty settings. |
| Difficulty | The named difficulty index is `E5FF84`; native `E3740` sets the CPU/Human slider pairs to 0/1, .25/.75, .5/.5 and .75/.25 for Rookie/Pro/All-Pro/Legend. There is no direct difficulty-index read in `20B180`, `20AF80` or `209CA0`. All four actual preset writes are replayed with the category cases. With kicker range and supplied state fixed, their punt/FG/go outputs are identical. This is not proof that difficulty cannot affect upstream player state, catchability or full games. |

The retail punt routine is conservative in ordinary conditions: outside its
near-FG exception, own-half positions return the punt choice; beyond midfield,
more than one yard to go commonly returns punt. It also has late trailing,
score, timeouts, mode and FG-range exceptions. The patch leaves those native
decisions intact whenever its additional-go policy declines a case.

The category replay supplies only `18B120`'s roster-derived maximum range
(40 yards in the main comparison). The actual caller, FG and punt decision
instructions, score/time/distance helpers, native category generator and RNG
execute. This is a decision replay, not a full roster or game replay.

| Supplied fourth-down state | Retail category | Modern/Aggressive category |
| --- | --- | --- |
| Own 50, 2 yards, Q2 600 seconds, tied | 17, punt | 5, ordinary offense |
| Opponent 30, 2 yards, same clock/score | 19, FG | 5, ordinary offense |
| Own 30, 7 yards, same clock/score | 17, punt | 17, punt |
| Opponent 20, 2 yards, Q4 100 seconds, down 3 | 19, FG | 19, FG |

These exact category IDs use the recorded seed and supplied context. A live
game can choose a different ordinary offensive category.

## Fourth-down table

Only a CPU offense (`offense+30 == 0`), ordinary phase 4, down 4 and regulation
quarters 1 through 4 can receive an additional-go decision. Own-yard position
is measured from the offense's own goal, independent of field direction.
Limits below are maximum yards to go. Zero means delegate to retail.

| Own-yard interval | Modern | Aggressive |
| --- | ---: | ---: |
| 0 to below 20 | Retail | Retail |
| 20 to below 40 | 1 | 2 |
| 40 to below 60 | 2 | 3 |
| 60 to below 80 | 3 | 5 |
| 80 to below 95 | 2 | 3 |
| 95 through 100 | 2 | 3 |

Apply these exceptions in order:

1. Preserve retail in the final 30 seconds of the first half.
2. Preserve retail in the final 120 seconds of Q4 when the offense is tied,
   leading or behind by at most 3. This preserves late tying/winning FG and
   clock-management decisions, including retail's conservative limitations.
3. Within the final 300 seconds of Q4, leading by at least 9 subtracts one
   yard from the limit. Trailing by at least 4 with at most 120 seconds adds
   four yards; otherwise trailing by at least 9 adds two yards.
4. Own-yard positions below 20 always delegate to retail, including its
   native desperation logic. Invalid position/distance/direction, more than
   20 yards to go, clocks above 10,000 seconds, and overtime delegate to retail.

The policy uses the native half clock, not wall time. A 0.0001-yard comparison
tolerance handles float32 LOS cancellation at whole-yard boundaries. When
accepted, the hook enters native `209FE0`; otherwise it replays the displaced
instruction and resumes `20B185`. No policy random draw or special-teams
result is manufactured. This is an intentionally conservative policy inspired
by more frequent short-yardage attempts, not a fitted expected-points or
win-probability model. Weather, actual conversion rates and kicker quality
are not new inputs to this table; native fallback retains its own range logic.

## PROVED: retail marker logic and passing changes

Retail **already uses distance to the marker**. `209FE0` includes distance,
down, urgency and RNG in category choice. Actual play selector `2096A0`
iterates candidate plays and mirror choices, calls `208820`, normalizes native
run/pass buckets and then calls `203440` with exponent 3 for random choice.
`208820` includes a third/fourth-down branch that reweights native distance
bins from `207950`; history/tendency tables also affect that path. The earlier
`208120`/`207EF0` routines score formations/categories, so they were not used
as the play hook.

The patch intercepts the actual play's native score at `20980D`. On CPU downs
3/4 it multiplies that score by 1.5 (Modern) or 2 (Aggressive) only if the
supported primary route reaches the current marker. Native legality,
formation eligibility, normalization and random choice still execute. Within
the same normalized bucket the later exponent means relative odds can change
by 3.375 or 8, respectively. These are meaningful preferences, not a 50%/100%
claim about final selection probability. It can still call runs or short passes.

The conservative primary classifier reads the loaded native PLAY buffers
`B75A40` and `B88DD0`, each 0x13390 bytes. It bounds/alignment-checks the 270
96-byte plays, 50 180-byte formations and 3500 eight-byte nodes. A terminal
QB Pass node must name explicit first read 1 through 5 (receiver slot 6 through
10). The primary receiver must use exact Start mode 1/role 3/zero offset,
then a straight leg, optionally one terminal lateral break of type 4 or 5.
Its endpoint is the signed formation depth plus the straight distance in
feet converted to whole centimetres, rounding down. Mirrored formation
partners follow the native `17FE60` mapping. Unsupported/ambiguous receiver
scripts, multi-break routes, screens, missing explicit first reads and foreign
buffers keep retail weights. This is planned primary geometry, not a prediction
that the QB will reach that read; intermediate QB commands and coverage can
change the live outcome. The classifier does not rewrite a PLAY resource.

In the ARI book (archive entry 307), the fixed formation-8/category-4 sample
has 12 legal native candidate/mirror rows. Native loader `161E30`, opcode
initialization and validator `1A9A80` execute; the harness supplies zero
tendency/history tables and a fixed formation/category. It runs `2096A0`
through normalization and then real `203440`/RNG for seeds 0 through 255.
Each marker is checked on both downs and in both directions. “Reaches” below
means the supported primary endpoint reaches the line, not that the sampled
play converted.

| Marker | Retail probability / 256 draws | Modern probability / 256 draws | Aggressive probability / 256 draws |
| --- | --- | --- | --- |
| 3 yards | 47.06% / 117 | 75.00% / 189 | 87.67% / 216 |
| 7 yards | 47.06% / 117 | 75.00% / 189 | 87.67% / 216 |
| 12 yards | 23.53% / 63 | 50.94% / 132 | 71.11% / 184 |

The classifier comparison covers all 462 formation/menu links in this book,
both native buffers and both mirror choices: 1,848 comparisons, 20 distinct
supported formation/play links. Most retail routes deliberately retain their
native weights; this is not universal playbook coverage. `50 Inside` has a
supported primary endpoint at 695 cm, while `50 Streaks` reaches 1371 cm;
the latter remains preferred at a 12-yard marker.

A separate host grammar census of entries 307 through 343 finds 616 supported
links among 16,065 distinct formation/play pairs across 37 resources. Per-book
support ranges from 0 to 43; only the resource named Editor has zero. This
quantifies the limited route grammar, not full native replay of every book.
The target preference applies independently of that grammar.

Target selector `1985E0` receives up to five receiver rows at `BE4820`, stride
0xA0, count `BE480C`. It requires the row's native availability and viability
fields (+8/+10), and checks each of four projected scores against the native
threshold before ranking. The projected catch z is at score-pointer minus 12.
With ordinary urgency, its existing down coefficient is
`c = min((down - 1) * .5, 1)`; positive native urgency also selects 1.
Its native marker contribution is
`c * .1 * clamp((projected_forward_gain - distance) / (5 yards), -1, 5)`.
Native receiver attribute `17AE80` and trajectory penalty remain in the score.

At `1987B5`, after those eligibility and threshold checks, the patch adds
0.15 (Modern) or 0.30 (Aggressive) if the projected catch is at/beyond the
marker. A live CPU passer is required as well as the CPU team: the controller
record at passer+0xC must contain -1. The score is stored/reloaded exactly as
the displaced native instructions require. Native QB callback `19BB60`
calls this selector at `19BD8C`; the existing initializer/callback hooks owned
by screen/read-option are untouched.

The target replay executes full `1985E0` and its actual attribute helper,
with supplied viability and projected trajectories/scores. A short target
one yard before the line with raw .8 beats the at-line .7 target in Retail;
Modern and Aggressive select the viable at-line target. This is checked at
3, 7 and 12 yards, on downs 3/4, in both directions. Unavailable, nonviable
and below-threshold targets cannot gain eligibility; human teams, human
passers and downs 1/2 retain retail choice. Empty/no-viable lists still return
no target, and a substantially better short target can still win. Projection
generation, receiver reactions, throws, catches, collisions and animations
were not replayed.

## Owner safety and scope

The owner requests `(("nfl2k5_cpu_money_downs", "code", 2048, 16),)` and
uses 1,248 generated bytes with immutable constants inside RX and 800 bytes
of sealed padding. There is no RW/RO child and no persistent runtime state.
Live edits are exactly 5 bytes at `20B180`, 6 at `20980D`, and 6 at `1987B5`.
All added scratch writes use the native stack; only the displaced native
score stores write their original frame slots. GPRs/EFLAGS are preserved
except displaced outputs; XMM is untouched; additional x87 pushes/pops are
balanced. x87 diagnostic condition/status bits are not an API guarantee.

The core seals exact relocated code and pins complete dependent decision,
selector, half-clock and formation-depth routines. Recognition restores only
this owner's hooks for guard hashing, then checks each hook independently.
Mixed hooks, foreign dependencies, modified code even after resealing, an
absent allocation and changing an installed level refuse before mutation.
Repeated application is byte-identical with zero changed bytes. CLI reads
are bounded at 16 MiB; output must be a new file, and handles are closed on
every path. No raw `os.open` or replacement operation was added.

The allocator budget fixture was planned before implementation and now includes
the real 2048-byte request. The shared test union composes the owner forward,
reverse and under explicit v3 allocation; both XBE gates enumerate it.
The pair matrix adds every existing matrix partner, including read-option,
screen hooks, MyCareer and coverage trail, without editing their modules.
The cave-manifest builder observes the owner and includes it in its request,
wrapper, installation, status and metadata lists.

In the complete test union the code begins at `0x14DAB00`; this is a measured
test address, not a runtime constant. The union retains 52,624 allocatable RX
bytes and 4,096 allocatable RW bytes. A standalone Modern build explicitly
uses v3, is 12,300,288 bytes, grows the XBE by 352,256 bytes and changes
353,293 bytes including growth/allocator metadata. Its SHA-256 is
`970f189e5b443ac873653b1e528e4490f3e9068ff942d1397fb8eb5e609e33c3`.
Those figures include the shared allocator, not just the 1,248-byte feature.

## HYPOTHESIS and remaining integration limits

More attempts and deeper planned routes/targets should improve the player's
reported behavior. Conversion rates, sack/interception effects, late-game
judgment across full drives and QB willingness to wait for the deeper read
remain unproved. This patch cannot guarantee throws past the sticks on every
third/fourth down. Broad route support and team-specific analytics need more
evidence; unsupported cases intentionally retain retail.

The production cave manifest on the supplied branch has seven stale source
fingerprints: mod_build, throw_tuning, ESPN rosters, MyCareer mode/code and
read-option runtime/code. Local tests use a labeled `.scratch/cave-base.json`
with refreshed source identities and inherited reservations via
`NFL2K5_CAVE_MANIFEST`; no protected manifest was edited. The dedicated owner
projection observes this owner's actual XBE writes and allocator union,
rejects new unobserved drift and records the inherited provenance limitation.
Refreshing historical source identities is not proof of the other owners'
new disc-build behavior. Claude must regenerate production evidence after
the protected integration. The shared GUI and build dispatcher are not wired
by this commit; WIRING.md supplies the required concrete changes.

An additional independent observation of the complete current XBE writer
composition passed: 108 observed steps, 10,628 reservation spans, including
this owner's installation/replay steps. Its composed XBE SHA-256 is
`d446749b73452818ea4a1273789254ef23989f96514455ec26d055074f01080b`.
The resulting `.scratch/observed-xbe-manifest.json` validates every current
source fingerprint without refreshing a historical digest; it has no disc
or resource-build claim. Its SHA-256 is
`2b368ae6988c511fae8edda25490f199d6b2a1df6348826a96fdabd8b96e1726`.
This stronger XBE-only evidence still does not replace production disc
manifest regeneration or Noah's gameplay witness.

## Noah's witness list

1. Compare verified Retail, Modern and Aggressive builds on the same matchup,
   playbooks, sliders and clock. Capture the build receipt/installed level,
   difficulty, offense, down/distance, score, quarter and clock.
2. Test own 19/20, 39/40, midfield, opponent 40/20/5, with distances just below,
   at and above each table limit. Repeat in the opposite field direction.
   Record actual punt, FG or offensive play calls, including retry/audible cases.
3. Test Q2 30 seconds, Q4 300/120 seconds, tied, down 3/4/9 and up 9, plus
   overtime. Confirm late tying/winning FG and human play-call controls.
4. On CPU third/fourth and 3/7/12, include the ARI formation-8 candidate set,
   then several other playbooks. Record the selected play and primary route;
   repeat enough calls to distinguish a preference from one random draw.
5. Present an open receiver at/beyond the marker and a slightly better short
   option. Then cover the deep option, leave only a short option, and remove
   every viable target. Record throw location, hesitation, sacks and catches.
   Include backs, tight ends, goal-to-go, mirrored routes and unsupported screens.
6. Repeat on Rookie/Pro/All-Pro/Legend, both human and CPU offenses, and downs
   1/2. Include the other optional CPU/QB/screen features in the composed build.
   Nothing here is witnessed until Noah plays and reports those outcomes.

## Validation record

All commands ran from this worktree with Python 3, without pytest or a display.
The new suites use precise skips if the pinned executable, indexed PLAY
resources, Unicorn or the ELF32 GNU assembler are absent. No test reads a
whole archive/disc into memory. The final native suite used 305,992 KiB peak
RSS; the owner suite used 149,052 KiB. The full-stack observation used
236,636 KiB, the complete memory gate used 340,828 KiB and the cave-reference
gate used 526,928 KiB. Each stays below the 2 GiB process limit. No temporary
executable, archive or disc copy is retained; scratch evidence remains below
the 200 MiB limit.

| Command | Result |
| --- | --- |
| `python3 tools/nfl2k5_xbe_space.py plan --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json` | Passed, v3 budget fits; initial scratch plan also passed before implementation. |
| `python3 tools/nfl2k5_cpu_money_downs_assemble.py --check` | Generated code reproduces exactly. |
| `python3 tests/mod_editor/test_nfl2k5_cpu_money_downs.py` | 12 passed, 34.316 s. Final platform-skip adjustment also checked with `PolicyTests`: 7 passed. |
| `python3 tests/mod_editor/test_nfl2k5_cpu_money_downs_unicorn.py --write-evidence docs/mod_editor/nfl2k5_cpu_money_downs_replays.json` | 8 passed, 83.776 s; final numerical evidence and 37-book census generated. |
| `python3 tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py -k cpu_money_downs` | 15 passed, 131.530 s; each new-owner pair in both orders, exact replay and byte equality. The unrelated preexisting pairs were not rerun. |
| `NFL2K5_CAVE_MANIFEST=.scratch/cave-base.json python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` | 28 passed, 433.532 s. |
| `NFL2K5_CAVE_MANIFEST=.scratch/cave-base.json python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 99 passed, 1686.821 s; full forward/reverse and explicit v3 classes. |
| `NFL2K5_CAVE_MANIFEST=.scratch/cave-base.json python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 111 passed, 1889.542 s; full forward/reverse and explicit v3 classes, no retail references into this owner's detour interiors or new allocation. |
| `NFL2K5_CAVE_MANIFEST=.scratch/cave-base.json python3 tests/mod_editor/test_nfl2k5_cpu_money_downs_manifest.py` | 3 passed, 8.365 s, and `--write-projection .scratch/cpu-money-downs-manifest.json` succeeded. |
| `NFL2K5_CAVE_MANIFEST=.scratch/observed-xbe-manifest.json python3 tests/mod_editor/test_nfl2k5_cpu_money_downs_manifest.py` | Final 3 passed, 7.849 s; projection emitted with current layout and observed-XBE hash. |
| `NFL2K5_CAVE_MANIFEST=.scratch/cave-base.json python3 tests/mod_editor/test_nfl2k5_screen_hooks_manifest.py` | 3 passed, 8.738 s. |
| `NFL2K5_CAVE_MANIFEST=.scratch/cave-base.json python3 tests/mod_editor/test_nfl2k5_my_career_manifest.py` | 3 passed, 12.861 s. |
| `NFL2K5_CAVE_MANIFEST=.scratch/cave-base.json python3 tests/mod_editor/test_nfl2k5_music_playlist_manifest.py` | 2 passed, 7.310 s. |
| `NFL2K5_CAVE_MANIFEST=.scratch/cave-base.json python3 tests/mod_editor/test_nfl2k5_defensive_try_manifest.py` | 3 passed, 8.085 s. |
| Scoped read-option manifest runner below | 1 passed, 29.050 s. |
| Scoped complete-XBE observation runner below | 1 passed, 379.124 s; all final changed bytes attributed. |
| `git diff --check` and protected-path comparison against HEAD | Passed; protected sources and excluded gameplay modules unchanged. |

The two existing-suite observation issues were recorded rather than hidden:

- The unmodified read-option diagnostic manifest suite ignores
  `NFL2K5_CAVE_MANIFEST`, so its plain-file invocation failed on the seven
  known stale historical sources. A direct production-manifest load with
  `source_root=Path.cwd()` likewise refused stale `mod_build.py`, as expected.
  The scoped run below changes only that suite's manifest input.
- The unmodified guardian manifest suite failed at raw offset `0xB2319`
  because the existing ESPN adapter's static method had captured `apply_xbe`
  before the recorder wrapped the module function. The second run delegates
  through the same actual writer so its real bytes are observed. It changes
  no source, output bytes or assertions and then passes full attribution.

```python
# Run from the worktree: python3 - <<'PY' ... PY
import os
import unittest
from pathlib import Path
from unittest.mock import patch
from tests.mod_editor import test_nfl2k5_read_option_diagnostic_manifest as read_suite
read_suite.DEFAULT_MANIFEST = Path(".scratch/cave-base.json").resolve()
result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(read_suite))
assert result.wasSuccessful()

os.environ["NFL2K5_CAVE_MANIFEST"] = ".scratch/cave-base.json"
os.environ["NFL2K5_GUARDIAN_MANIFEST_OUTPUT"] = ".scratch/observed-xbe-manifest.json"
from mod_editor.core import nfl2k5_espn25_rosters as espn
from tests.mod_editor import test_nfl2k5_guardian_manifest as observed_suite
with patch.object(espn.XbePatch, "apply", staticmethod(lambda payload: espn.apply_xbe(payload))):
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(observed_suite))
assert result.wasSuccessful()
```

Scratch-base preparation is intentionally explicit and is not a release
manifest command. Preserve the production document's spans/layout, replace
only its existing `source_sha256` entries with `builder.source_fingerprints()`
values, and label the result scratch-only with `real_disc_build=False` and
`production_regeneration_required=True`. The seven old/new digest pairs are
in `.scratch/manifest-stale-sources.json`. The complete current-XBE observation
above separately records actual writer effects. The protected production
document was never written.

## Delivery

Explicit-path `git add -- <18 reviewed paths>` failed because the shared
worktree Git metadata cannot create `index.lock` on its read-only filesystem.
The authorized fallback is `.scratch/cpu-money-downs.bundle`: one local commit
on `astra/r65-cpu-fourth-down` over
`be99b324f34d536c625efcba7e7ea5d4f104fd2b`, made in an isolated temporary Git
directory with a read-only alternate base object store. Only the 18 reviewed
paths are staged/committed. Bundle verification, parent identity and exact
worktree-file/blob comparisons are required before delivery; the temporary
Git directory is deleted. The original files stay in this worktree.
`ASTRA_BRIEF.md` and `.scratch/` contents are excluded from the commit.
No push is performed. The final commit ID and bundle hash are recorded in
`.scratch/delivery.json` with per-file hashes.
