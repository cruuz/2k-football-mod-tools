# r61b screen-pass report, 2026-09-05

**EXPERIMENTAL / UNWITNESSED.** Implemented the fixed-span PLAY timing experiment
and the Create a Play HB/WR/TE screen presets. This is not a gameplay-success
claim. No emulator, game boot, visible GUI, audio or network was used. Qt tests
ran offscreen. No source disc, executable, extracted archive or other worktree
was edited. Protected integration changes are specified in `WIRING.md`.

Starting branch: `astra/r61b-screen-pass`, HEAD
`e6784e70f185567899b4256a4b8ef492dd96c7dd`.
Research authority: the read-only hub's
`SCREEN_PASS_RESEARCH_2026-09-04.md`, tiers 1 and 3. The memo's `.scratch`
artifacts were absent at its linked hub location, so the census and compiler
measurements were independently reproduced from the extracted retail archive.
No tier-2 hook, cave, writable runtime state or section change was introduced.

## What was built and proved

`mod_editor/core/nfl2k5_screen_timing.py` exposes:

```python
status(raw_play, level="D")                     # retail / applied / foreign
inspect(raw_play, level="D")                    # plays, reasons, capacity
replacement, receipt = apply(raw_play, level="D")
inspect_archive(archive, level="D")
apply_to_archive(archive, level="D", progress=None)
inspect_image(image_path, level="D")
apply_to_image(output_copy_path, level="D", progress=None)
```

**PROVED by this run:** all 37 PLAY entries `307..343` are 78,768 bytes each;
129 names contain “screen”, comprising 123 team-book and six other screens.
Sixty-six have an OL release action, but only **64** have the full finite
hold/release/type-3-block grammar. The two direct-release reference plays are
not guessed at. The eligible set contains all 60 team screens with releases,
two reference-book screens and the GEN/WCO screens. The other **65** plays
are listed below and remain byte-identical in their declared assignments.

A qualifying line assignment has Start, optionally Center Snap, a finite
block of type 0 or 1, a mode-0 release, then a type-3 block. Type-0 holds occur
in three native play-action screens (MIA 177, OAK 214, STL 188); their block
kind and QB fakes survive. A only changes a hold that is exactly 0.5 seconds.
Existing one-second holds survive (GB 131, PHI 228, STL 47). B only changes
mode-0 QB moves at nominal -10 yards; existing other drops or absent drop
nodes survive. C changes zero/default pass-delay operands to explicit 0.6.
D combines those changes. Default D is an experimental starting point, not
calibration evidence. A/B/C remain independently selectable.

| Level | Plays changed | Nodes cloned | Pool bytes used | Resource bytes changed |
| --- | ---: | ---: | ---: | ---: |
| A | 61 | 788 | 6,304 | 4,437 |
| B | 61 | 249 | 1,992 | 969 |
| C | 64 | 261 | 2,088 | 1,083 |
| D | 64 | 1,049 | 8,392 | 5,482 |

These totals span separate books; capacity is enforced separately in each.
Retail minimum remaining capacity is 761 nodes (CHI). D leaves at least 710.
ATL 178 independently reproduces the memo: A 13 nodes/74 changed bytes,
B 4/16, C 4/17, D 17/90. The five coordinated donor assignments, including
the HB, cost 19 nodes; a complete authored screen costs 31 nodes/248 bytes.

**PROVED:** pins contain SHA-256 digests only. Each book pins the declared
runtime assignments of every named screen, including skipped ones, for retail
and all four outputs. The signature includes indices, names, play flags,
descriptors and exactly the descriptor low-nibble node count. It excludes
relative pointer encodings, orphan nodes and unrelated plays/categories.
The uncompressed retail resource wrapper is pinned structurally. Unknown book
identities, renamed/replaced named screens, mixed edits, a different installed
level, invalid declared lengths and malformed wrappers refuse. Capacity and
nonzero allocation padding refuse before the writer allocates any chains.
Unrelated category edits are intentionally outside screen ownership.

`Nfl2k5Playbook.assignment_chain` and `PlaybookAssignment.declared_length`
provide the runtime span used by reader `0x1A8C00`. The existing `chain()`
extent API remains available for inspection. Parsing now rejects zero lengths
and lengths exceeding the used pool. The old synthetic inspector fixture's
arbitrary low nibbles were corrected to its actual two-node lengths.

The writer now exposes `authored_node_cost` and preflights the complete batch's
node cost/zero tail. All timing replacements use the existing
`compile_formation_play_creations` writer with the same donor/replacement play
index and `None` for untouched slots. Shared original chains and formation
links remain intact; only the edited assignment references move to fresh
nodes. Multiple links to ATL 178 still reach the same edited play. Orphan QB
nodes enlarge play 177's inferred extent in B/C/D, but its declared assignment
is identical. Every play in each of the 148 compiled resource outputs passes
the ported game validator. Reapplying every level produces identical bytes
and zero additional node/byte cost.

Receipts identify book, outer entry, play name/index and assignment slots;
list exact resource-relative offsets with before/after hex; separate the
shared node-count word changes; record source/output hashes, node costs and
changed-byte counts. Per-play counts plus shared-word counts equal the complete
byte difference. Full receipts remain local in `.scratch/screen_pass/receipts_D.json`.
The committed report includes byte counts, not redistributed PLAY bodies.

The archive adapter checks all 37 resources before its first write and checks
book identity against outer index. It rejects an archive with only some
applicable books patched. It rechecks preimages, writes exact changed runs,
verifies read-back and rolls back every attempted write if one fails. Tests
exercise late preflight refusal, wrong/missing books, mixed states, concurrent
preimage changes, short writes, bad read-backs and rollback failure. Actual
retail resource transport/idempotence was tested in an in-memory archive;
no full disc was written or booted in this session.

## Create a Play and exact GUI edit boundary

**PROVED:** selecting the HB Screen preset produces the stock QB look-first
sequence, three finite line holds/releases/type-3 blocks, preserved center
snap, two remaining protectors and the HB's type-9 route. Selecting Retail
on the timing control reproduces ATL 178's five coordinated chains byte for
byte. D is the default; Retail/A/B/C/D starting points plus finite line hold,
nominal QB drop and pass delay controls are exposed. A zero pass delay is
labeled “Retail default timer”, never immediate. Zero line holds are not
permitted for releasing blockers; the other two linemen retain terminal
zero-delay protection.

HB, WR and TE variants expose only actual eligible assignment slots `6..10`
for the chosen position. The QB first-read operand is `slot - 5`; the other
three reads stay zero. Screen-only finalization preserves those zeros and
explains first-zero/default slot 7 and later-zero/skip semantics. Existing
non-screen read editing is unchanged. Missing personnel or selecting the
screen with Play-action prevents advancement; the authored preset is a Pass.
Native retail play-action screens remain eligible for the separate data pass.

**HYPOTHESIS:** WR/TE variants adapt the HB donor grammar. They are not claimed
to reproduce every native WR/TE screen family. Both sides and all eligible
receiver choices compile and validate, but their timing, geometry and usefulness
need independent gameplay witness. Non-target WRs clear out; other backs/TEs
protect. Choosing a slot does not force the runtime QB selector's final target.

The screen preview replaces the misleading generic type-9 block glyph with a
dashed behind-line endpoint guide. The underlying `screen_endpoint` helper
expresses the memo's proved type-9/type-10 endpoint adjustment: type 9 is
1.5 yards behind the line, type 10 one yard behind; type 9 bounds the incoming
lateral endpoint to ±19 2/3 yards unless the actor is already outside that
bound. Both directions and boundary cases are tested. The preview explicitly
does **not** predict lateral travel, arrival time or catches. The encoded
negative distance is not displayed as an ordinary eleven-yard downfield route.
The helper does not simulate the preceding movement solver.

The wizard shows full authored node cost and remaining space after other
plays in this wizard; the writer is the final authority across all project
requests. Restoring a drawn job preserves the selected screen receiver/side.
Offscreen tests verify controls, missing personnel, capacity gating, preview
text, default D, Retail values and final staged zero reads.

Only these existing functions in `mod_editor/gui/create_play_wizard_qt.py`
were changed, with changes scoped to screen paths:

- `with_read_order`: optional `allow_zero`, used only by screen finalization.
- `PlayTypePage.__init__`, `_refresh_options`, `build_spec`: screen controls and
  screen-specific concept text/selection.
- `AssignPage._refresh`, `_describe`, `_default_for`: screen guide, node budget,
  job text and restoration.
- `FinalizePage._add_read_order`, `_apply`: screen-only zero ranges and retention.

New functions: `PlayTypePage._make_screen_options`, `_screen_timing`,
`_screen_options`, `isComplete`. No Defense-family code, formation-page code,
other GUI panel or protected file was changed.

## Tests actually run

All commands ran from this worktree, using plain standalone unittest scripts.
`PYTHONPATH=.` is needed by older scripts which do not add the repository root;
the new tests and updated inspector test bootstrap it themselves. Qt used
`QT_QPA_PLATFORM=offscreen` throughout. Evidence-dependent tests have precise
unittest skips when retail extraction or Qt is absent; no skip was needed here.

| Command | Result |
| --- | --- |
| `python3 tests/mod_editor/test_nfl2k5_screen_timing.py` | 13 passed, 88.967 s; 37 books × four levels plus real-resource archive round trip |
| `python3 tests/mod_editor/test_nfl2k5_screen_archive.py` | 7 passed; synthetic transaction fault injection |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_screen_preset_qt.py` | 4 passed; final run 0.193 s |
| `python3 tests/mod_editor/test_nfl2k5_playbook_inspector.py` | 6 passed |
| `PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_formation_play_writer.py` | 8 passed |
| `PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_play_author.py` | 13 passed |
| `PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_playbook_route_writer.py` | 4 passed |
| `PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_depth_roles.py` | 22 passed |
| `python3 tests/mod_editor/test_nfl2k5_screen_timing.py RetailScreenTests.test_foreign_mixed_other_level_and_skipped_screen_refuse ScreenAuthorUnitTests.test_unknown_payload_and_level_refuse` | 2 passed after adding strict wrapper refusal |

That is **77 unique passing tests** across eight standalone suites, plus two
focused reruns. Older authoring tests emit an existing unclosed-cache-reader
`ResourceWarning`; their assertions pass. New screen APIs do not open those
cache readers. Logs are in `.scratch/screen_pass/tests_*.log`.

The mandatory existing XBE gates were run and are **not green on the starting
branch**:

- `python3 tests/mod_editor/test_xbe_patch_memory_writes.py`: four tests pass;
  `PatchWriteTests.setUpClass` errors at `nfl2k5_depth_locks.apply`.
- `python3 tests/mod_editor/test_xbe_patch_cave_references.py`:
  `CaveReferenceTests.setUpClass` errors before its tests run.
- Both errors are `DepthLockError: ... unknown bench promotion call sites`.
- Repeated both commands against `.scratch/screen_pass/baseline/`, populated
  with `git archive HEAD mod_editor tools data tests`: identical failures
  without any screen code. Baseline memory: four tests/one setup error;
  baseline cave: zero tests/one setup error.

No gate was weakened and no out-of-scope XBE patch was edited. This task adds
no executable owner to their composition chains; passing this resource API
an XBE is itself tested to refuse. The existing depth-lock/practice-squad
integration failure must be repaired by its owner before a combined release.
`WIRING.md` records this separately from the screen feature.

## Noah's paired-snap witness protocol

**HYPOTHESIS until Noah plays it.** Keep five separately identified baseline/A/
B/C/D output copies and their recipes/receipts. Build each candidate from the
same unmodified baseline with all other options identical. Do not apply D over
an A/B/C copy; the pins deliberately refuse that. For the first timing test,
use ATL 178 from I Twins, then repeat the other two linked formations.

1. Fix teams, roster, QB/HB identities, difficulty, sliders, weather, fatigue,
   field spot/hash, ball direction and defensive calls. Record them with the
   output hash/level. Keep the same unrelated gameplay patches in each copy.
2. For **each level A, B, C and D**, run **ten paired snaps versus baseline**
   against each of a four-man rush, a man blitz and a zone call. Separate human
   QB and CPU QB trials. Thus each candidate has six cells × ten pairs = 60
   pairs; the four candidates require 240 pairs/480 snaps including their
   matched baseline snaps. A pair means one baseline snap and one candidate
   snap under matching conditions, not five snaps of each in a ten-snap total.
3. Alternate which copy goes first in successive pairs. Reload/reset conditions
   as closely as possible. Record substitutions, fatigue changes, audibles or
   other mismatches; flag those pairs rather than treating them as controlled.
   Uncontrolled game RNG is not assumed equal. For human trials, choose one
   consistent throw rule before starting and write it down. CPU trials must
   allow the CPU to choose the target and release time.
4. Record per snap: level, pair number, defense, control mode, formation/link,
   intended receiver name and assignment slot; actual target; snap-to-OL-release
   time; snap-to-QB-release time; nominal versus observed QB depth; first useful
   OL contact after release (which lineman/defender and when); throw location;
   catch location relative to the line and hash; sack/throwaway/incompletion/
   completion; net yards; immediate contact; any control/animation anomaly.
   Video frame counts are useful if Noah captures them, but do not replace the
   snap log with an impression. A sack has no QB-release time; mark it absent.
5. Compare each pair and summarize medians/ranges of timing, completions, sacks,
   useful escort engagements and net yards. Inspect A/B/C individually before
   interpreting D. A longer hold may delay escorts, a shallower drop may expose
   the QB sooner, and explicit 0.6 may hurt some QBs; report those regressions.
6. Repeat any promising setting mirrored, in each ATL-linked formation, with
   at least one additional team/QB and with an ordinary pass control. Inspect
   a skipped named WR screen as an unchanged control. Give one-second holds,
   a native PA screen and a middle screen their own trials before broad claims.
7. Separately author HB, WR and TE screens. Confirm menu placement, intended
   assignment slot and icons, both release sides, center snap, the two remaining
   protectors, receiver endpoint and actual QB target. Use Retail versus D,
   ten paired snaps per variant/side/control mode against the same defenses;
   expand A/B/C if a variant needs diagnosis. Save/reload the project, rebuild,
   then check the same assignments. The WR/TE adaptation is a separate witness.

Success requires escorts visibly engaging useful defenders and a catch before
the rush wins, without new sacks, stalled blockers, broken snaps, ordinary-pass
regressions or lost control. A valid diagram or higher mean yardage alone does
not establish that. Do not label the feature “fixed” based on these offline
checks. Only Noah's recorded play can establish the bounded witnessed result.

## Remaining limits and integration decisions

The protected BuildPlan, Build/Gameplay Patches controls, release allowlist,
runtime closure and capability registry are **handoffs**, not silently wired
here. `WIRING.md` gives exact field/preset/dispatcher/status-dictionary changes.
Tier 2 waits for the allocator and Noah's evidence. No current code claims a
root cause for retail screen failures, a guaranteed pass time, a forced target,
a full movement/contact simulation or a defensive-recognition correction.

WR/TE variants reuse the proved HB grammar and need their own witnesses.
Generic manual “Screen” route selection and the codec's legacy type labels
remain unchanged outside the dedicated preset path. Custom screen replacements
conflict with the retail timing pass; build such authored trials with the
retail timing toggle off. Capacity estimates in the wizard exclude other
preexisting project requests; the common writer enforces the combined budget.

Pin reproduction: read each fixed wrapped resource from outer entries 307..343,
parse it, compute `_signature(book)`, compile `_requests(book, level)` through
the existing writer for each A/B/C/D, and compute each parsed output signature.
The key is SHA-256 of the UTF-8 book identity. The all-corpus test independently
requires those compiled outputs to match the embedded pins. Local reproduction
scripts, private resources, compiler receipts and baseline logs are in
`.scratch/screen_pass/`; they are excluded from the commit and release.

## Per-book resource measurements

All four outputs retain 78,768 bytes. Each level cell below is
`changed plays / cloned nodes / changed resource bytes`.

| Outer | Book | A | B | C | D |
| ---: | --- | --- | --- | --- | --- |
| 307 | ARZ | 2 / 26 / 145 | 2 / 8 / 31 | 2 / 8 / 33 | 2 / 34 / 177 |
| 308 | ATL | 1 / 13 / 74 | 1 / 4 / 16 | 1 / 4 / 17 | 1 / 17 / 90 |
| 309 | BAL | 1 / 13 / 74 | 1 / 4 / 16 | 1 / 4 / 17 | 1 / 17 / 88 |
| 310 | BUF | 1 / 13 / 74 | 1 / 4 / 16 | 1 / 4 / 17 | 1 / 17 / 90 |
| 311 | CAR | 1 / 13 / 74 | 1 / 4 / 16 | 1 / 4 / 17 | 1 / 17 / 90 |
| 312 | CHI | 3 / 39 / 216 | 2 / 8 / 31 | 3 / 12 / 51 | 3 / 51 / 264 |
| 313 | CIN | 1 / 13 / 74 | 1 / 4 / 16 | 1 / 4 / 17 | 1 / 17 / 90 |
| 314 | CLE | 1 / 13 / 74 | 1 / 4 / 16 | 1 / 4 / 17 | 1 / 17 / 90 |
| 315 | DAL | 1 / 13 / 74 | 1 / 4 / 16 | 1 / 4 / 17 | 1 / 17 / 90 |
| 316 | DEN | 3 / 39 / 220 | 3 / 12 / 46 | 3 / 12 / 49 | 3 / 51 / 268 |
| 317 | DET | 2 / 26 / 144 | 2 / 8 / 31 | 2 / 8 / 33 | 2 / 34 / 177 |
| 318 | Editor | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| 319 | GB | 2 / 26 / 145 | 3 / 12 / 46 | 3 / 12 / 49 | 3 / 38 / 193 |
| 320 | GEN | 1 / 13 / 74 | 1 / 4 / 16 | 1 / 4 / 17 | 1 / 17 / 88 |
| 321 | HOU | 3 / 39 / 218 | 3 / 12 / 46 | 3 / 12 / 49 | 3 / 51 / 268 |
| 322 | IND | 1 / 13 / 72 | 1 / 4 / 16 | 1 / 4 / 17 | 1 / 17 / 90 |
| 323 | JAX | 2 / 26 / 145 | 2 / 8 / 31 | 2 / 8 / 33 | 2 / 34 / 177 |
| 324 | KC | 3 / 39 / 216 | 2 / 8 / 31 | 3 / 12 / 51 | 3 / 51 / 266 |
| 325 | MIA | 2 / 26 / 147 | 2 / 9 / 35 | 2 / 9 / 37 | 2 / 35 / 183 |
| 326 | MIN | 2 / 26 / 143 | 2 / 8 / 31 | 2 / 8 / 33 | 2 / 34 / 177 |
| 327 | NE | 1 / 13 / 74 | 1 / 4 / 16 | 1 / 4 / 17 | 1 / 17 / 90 |
| 328 | NO | 2 / 26 / 147 | 2 / 9 / 34 | 2 / 9 / 36 | 2 / 35 / 181 |
| 329 | NYG | 4 / 52 / 293 | 4 / 17 / 65 | 4 / 17 / 69 | 4 / 69 / 360 |
| 330 | NYJ | 3 / 34 / 195 | 3 / 12 / 46 | 3 / 12 / 49 | 3 / 46 / 243 |
| 331 | OAK | 2 / 26 / 147 | 2 / 9 / 35 | 2 / 9 / 37 | 2 / 35 / 183 |
| 332 | PHI | 1 / 13 / 75 | 1 / 4 / 16 | 2 / 8 / 34 | 2 / 21 / 106 |
| 333 | PIT | 1 / 13 / 74 | 1 / 4 / 16 | 1 / 4 / 17 | 1 / 17 / 90 |
| 334 | PRACTICE | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| 335 | reference | 2 / 26 / 147 | 2 / 8 / 31 | 2 / 8 / 33 | 2 / 34 / 179 |
| 336 | SD | 3 / 39 / 218 | 3 / 12 / 46 | 3 / 12 / 49 | 3 / 51 / 266 |
| 337 | SEA | 1 / 13 / 74 | 1 / 4 / 16 | 1 / 4 / 17 | 1 / 17 / 90 |
| 338 | SF | 1 / 13 / 74 | 1 / 4 / 16 | 1 / 4 / 17 | 1 / 17 / 90 |
| 339 | STL | 2 / 26 / 147 | 3 / 13 / 50 | 3 / 13 / 53 | 3 / 39 / 199 |
| 340 | TB | 2 / 26 / 147 | 2 / 8 / 31 | 2 / 8 / 33 | 2 / 34 / 179 |
| 341 | TEN | 1 / 13 / 74 | 1 / 4 / 16 | 1 / 4 / 17 | 1 / 17 / 90 |
| 342 | WAS | 1 / 13 / 74 | 1 / 4 / 16 | 1 / 4 / 17 | 1 / 17 / 90 |
| 343 | WCO | 1 / 13 / 74 | 1 / 4 / 16 | 1 / 4 / 17 | 1 / 17 / 90 |

## Eligible plays: exact D receipt counts

Changed bytes here exclude the shared book node-count word, which has its own receipt entry.

| Outer / book | Play index | Play | D nodes | D changed bytes |
| --- | ---: | --- | ---: | ---: |
| 307 / ARZ | 91 | 50 H Screen Weak | 17 | 87 |
| 307 / ARZ | 202 | 50 H Screen Strong | 17 | 89 |
| 308 / ATL | 178 | 50 H Screen Strong | 17 | 89 |
| 309 / BAL | 158 | 50 H Screen Strong | 17 | 87 |
| 310 / BUF | 176 | 50 H Screen Strong | 17 | 89 |
| 311 / CAR | 211 | 50 H Screen Strong | 17 | 89 |
| 312 / CHI | 93 | 50 H Screen Weak | 17 | 85 |
| 312 / CHI | 155 | 50 H Screen Strong | 17 | 89 |
| 312 / CHI | 227 | PA Reverse H Screen | 17 | 89 |
| 313 / CIN | 200 | 50 H Screen Strong | 17 | 89 |
| 314 / CLE | 163 | 50 H Screen Strong | 17 | 89 |
| 315 / DAL | 127 | 50 H Screen Strong | 17 | 89 |
| 316 / DEN | 62 | 50 H Weak Screen | 17 | 89 |
| 316 / DEN | 191 | 50 H Screen Strong | 17 | 89 |
| 316 / DEN | 192 | 50 F Screen Weak | 17 | 89 |
| 317 / DET | 110 | 50 H Screen Weak | 17 | 87 |
| 317 / DET | 167 | 50 H Screen Strong | 17 | 89 |
| 319 / GB | 79 | 50 H Screen Weak | 17 | 87 |
| 319 / GB | 131 | 50 Y Middle Screen | 4 | 16 |
| 319 / GB | 163 | 50 H Screen Strong | 17 | 89 |
| 320 / GEN | 99 | 50 H Screen Strong | 17 | 87 |
| 321 / HOU | 93 | 50 F Screen Strong | 17 | 89 |
| 321 / HOU | 178 | 50 TE Screen | 17 | 89 |
| 321 / HOU | 200 | 50 H Screen Strong | 17 | 89 |
| 322 / IND | 203 | 50 H Screen Strong | 17 | 89 |
| 323 / JAX | 129 | 50 H Screen Weak | 17 | 87 |
| 323 / JAX | 207 | 50 H Screen Strong | 17 | 89 |
| 324 / KC | 92 | 50 H Screen Weak | 17 | 87 |
| 324 / KC | 156 | 50 H Screen Strong | 17 | 89 |
| 324 / KC | 221 | PA Reverse H Screen | 17 | 89 |
| 325 / MIA | 69 | 50 H Screen Strong | 17 | 89 |
| 325 / MIA | 177 | PA H Screen Strong | 18 | 93 |
| 326 / MIN | 26 | 50 H Screen Weak | 17 | 87 |
| 326 / MIN | 136 | 50 H Screen Strong | 17 | 89 |
| 327 / NE | 183 | 50 H Screen Strong | 17 | 89 |
| 328 / NO | 107 | PA H Weak Screen | 18 | 91 |
| 328 / NO | 174 | 50 H Screen Strong | 17 | 89 |
| 329 / NYG | 72 | PA H Strong Screen | 18 | 93 |
| 329 / NYG | 88 | 50 F Screen Strong | 17 | 89 |
| 329 / NYG | 203 | 50 H Screen Strong | 17 | 89 |
| 329 / NYG | 207 | 50 TE Screen Strong | 17 | 88 |
| 330 / NYJ | 95 | 50 F Screen Weak | 17 | 89 |
| 330 / NYJ | 165 | 50 H Screen Strong | 17 | 89 |
| 330 / NYJ | 195 | 50 H Load Screen | 12 | 64 |
| 331 / OAK | 184 | 50 H Screen Strong | 17 | 89 |
| 331 / OAK | 214 | PA H Screen Strong | 18 | 93 |
| 332 / PHI | 57 | 50 H Screen Strong | 17 | 89 |
| 332 / PHI | 228 | Philly Option Screen | 4 | 15 |
| 333 / PIT | 173 | 50 H Screen Strong | 17 | 89 |
| 335 / reference | 108 | 50 F Screen Strong | 17 | 89 |
| 335 / reference | 180 | 50 H Screen Strong | 17 | 89 |
| 336 / SD | 124 | 50 TE Screen | 17 | 89 |
| 336 / SD | 139 | 50 H Screen Weak | 17 | 87 |
| 336 / SD | 144 | 50 H Screen Strong | 17 | 89 |
| 337 / SEA | 147 | 50 H Screen Strong | 17 | 89 |
| 338 / SF | 179 | 50 H Screen Strong | 17 | 89 |
| 339 / STL | 20 | 50 H Screen Strong | 17 | 89 |
| 339 / STL | 47 | Middle H Screen | 4 | 16 |
| 339 / STL | 188 | PA H Screen Strong | 18 | 93 |
| 340 / TB | 182 | 50 H Screen Strong | 17 | 89 |
| 340 / TB | 183 | 50 F Screen Weak | 17 | 89 |
| 341 / TEN | 129 | 50 H Screen Strong | 17 | 89 |
| 342 / WAS | 174 | 50 H Screen Strong | 17 | 89 |
| 343 / WCO | 99 | 50 H Screen Strong | 17 | 89 |

## All 65 skipped named screens

No full finite hold/release/type-3-block grammar; no timing values or chains guessed.

| Outer / book | Play index | Play |
| --- | ---: | --- |
| 307 / ARZ | 113 | 50 Z Slip Screen |
| 308 / ATL | 170 | 50 Z Slip Screen |
| 309 / BAL | 83 | 90 X Slip Screen |
| 310 / BUF | 120 | Z Slip Screen |
| 310 / BUF | 166 | 90 Y Screen Weak |
| 310 / BUF | 188 | 90 Z Quick Screen |
| 311 / CAR | 113 | 50 Z Slip Screen |
| 311 / CAR | 178 | 90 Y Screen Weak |
| 312 / CHI | 79 | 90 X Slip Screen |
| 312 / CHI | 159 | 50 Z Slip Screen |
| 312 / CHI | 178 | 90 Z Quick Screen |
| 313 / CIN | 96 | 90 X Slip Screen |
| 313 / CIN | 100 | 50 Z Slip Screen |
| 313 / CIN | 174 | Y Slip Screen |
| 314 / CLE | 134 | Y Slip Screen |
| 314 / CLE | 168 | 90 Z Sprint Screen |
| 316 / DEN | 93 | 90 X Slip Screen |
| 316 / DEN | 164 | 90 H Quick Screen |
| 317 / DET | 83 | 90 X Slip Screen |
| 317 / DET | 103 | 50 Z Slip Screen |
| 317 / DET | 158 | Z Slip Screen |
| 319 / GB | 143 | 50 Z Slip Screen |
| 321 / HOU | 100 | 90 X Slip Screen |
| 321 / HOU | 114 | 50 Z Slip Screen |
| 321 / HOU | 159 | 50 Y Screen Seam |
| 322 / IND | 104 | 50 Z Slip Screen |
| 323 / JAX | 141 | 50 Y Screen Seam |
| 323 / JAX | 152 | 90 Y Screen Weak |
| 323 / JAX | 184 | 90 B Speed Screen |
| 324 / KC | 78 | 90 X Slip Screen |
| 324 / KC | 160 | 50 Z Slip Screen |
| 324 / KC | 179 | 90 Z Quick Screen |
| 326 / MIN | 101 | 90 Bubble Screen |
| 326 / MIN | 177 | 50 Z Slip Screen |
| 327 / NE | 67 | 50 Double Screen |
| 327 / NE | 81 | 90 Y Screen Weak |
| 327 / NE | 82 | RO Y Sprint Screen |
| 327 / NE | 83 | 50 H Slip Screen |
| 327 / NE | 151 | 50 Z Slip Screen |
| 328 / NO | 96 | 90 Z Sprint Screen |
| 328 / NO | 143 | 90 Z Quick Screen |
| 328 / NO | 168 | 50 Z Slip Screen |
| 329 / NYG | 103 | 90 F Screen Out |
| 329 / NYG | 153 | 50 Z Slip Screen |
| 329 / NYG | 156 | 50 Y Screen Seam |
| 329 / NYG | 208 | 50 TE Zip Screen |
| 330 / NYJ | 110 | 90 F Quick Screen |
| 330 / NYJ | 145 | 50 Z Slip Screen |
| 330 / NYJ | 156 | 90 H Quick Screen |
| 333 / PIT | 86 | 90 Z Sprint Screen |
| 333 / PIT | 100 | 90 X Slip Screen |
| 333 / PIT | 103 | 50 Z Slip Screen |
| 335 / reference | 196 | Screen |
| 335 / reference | 197 | Middle Screen |
| 336 / SD | 71 | 50 Z Slip Screen |
| 336 / SD | 119 | 90 Y Screen Weak |
| 337 / SEA | 98 | 90 X Slip Screen |
| 337 / SEA | 102 | 90 F Screen Out |
| 337 / SEA | 153 | 50 Y Screen Seam |
| 337 / SEA | 178 | 50 Z Slip Screen |
| 337 / SEA | 184 | 90 H Screen Out |
| 338 / SF | 171 | 50 Z Slip Screen |
| 339 / STL | 119 | Z Slip Screen |
| 341 / TEN | 130 | Z Slip Screen |
| 342 / WAS | 94 | 90 Z Sprint Screen |
