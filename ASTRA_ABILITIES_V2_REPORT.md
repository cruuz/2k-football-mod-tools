# Superstar abilities rules v2, 2026-09-08

**EXPERIMENTAL / UNWITNESSED.** Built on `astra/r65-abilities-deeper`, base
`be99b324`. This delivers five bounded live attribute effects, stored
tiers, an owned Rosters Abilities page, reversible rating assignment, and
three independent locks. Six suggested independent abilities are refused
below because no storage or complete native outcome proof is available within
this owner's budget. Protected product integration is the concrete handoff
at the beginning of [WIRING.md](WIRING.md). No push, network, game emulator,
GUI display, audio, or original-input write was used. Qt was offscreen;
Unicorn ran bounded native routines, not a game.

## What changed

`nfl2k5_abilities_runtime` is model 2 with the same owner identity. Its seven
v1 flags and all seven original hook sites remain. One six-byte entry hook
at `0x17B010` wraps the common effective-attribute getter. The five effects
below are attached to existing permissions; they are not extra independent
flags disguised as new toggles. They operate during live phase 14 for tiered
players, after native getter, injury/condition/slider arithmetic and both
clamps, without writing a rating byte or adding persistent runtime state.

Let `v` be the original effective attribute and `t` the tier 1..3. If the
specific stored flag is effective and `0 < v < 1`, return
`min(1, v + .02*t)`. Otherwise preserve the native value. Zero is never
revived. Off-week, untiered, missing-flag, excess-slot and non-live paths get
no new attribute bonus. Changing a lock does not create an effect flag.

| Stored ability / UI effect | Native attribute index | Getter and raw byte | Neutral native replay | X-Factor replay |
| --- | ---: | --- | ---: | ---: |
| Juke / Agility | 1 | `0x1798B0`, record `+0x37` | 0.5 | 0.5600000024 |
| Stiff-Arm / Strength | 2 | `0x179A00`, `+0x3C` | 0.5 | 0.5600000024 |
| Hurdle / Jumping | 3 | `0x179920`, `+0x3D` | 0.5 | 0.5600000024 |
| Truck / Tackle Shed | 12 | `0x179D80`, `+0x41` | 0.5 | 0.5600000024 |
| Spin / Pass Rush | 18 | `0x17A020`, `+0x48` | 0.5 | 0.5600000024 |

Native table indices are **not** on-disc rating byte indices. Each dispatch
pointer and complete 112-byte getter slot is SHA-pinned. Tests run the actual
getters and shared native clamps from the pinned USA executable, with only
peripheral slider/injury-factor fixtures. The effect trace is retained in
`.scratch/abilities-v2/effects-replay.json`. A higher effective Pass Rush or
Break Tackle input is proved; a particular animation, success probability,
or monotonic gameplay outcome is not.

Momentum still owns its two contact calls. It calls the shared getter, so
Tackle Shed is added first, followed by Momentum's existing capped contact
term, with the final native effective value still capped at 1. Its dependency
guard now normalizes the six-byte abilities detour ONLY after validating the
entire abilities owner, seals, settings, hooks and dependencies. An arbitrary
jump, tampered getter, or damaged abilities table refuses before mutation.
Both contact reads are replayed with the real shared getter restored into
the existing Momentum fixture. At native .5, tier 3, 900 cm/s and the fixture's
220 lb masses, the result is `.56 + .06*900/REFERENCE_SPEED`; .99 caps at 1.
The ability .06 and Momentum .08 can total .14; Momentum's .08 limit still
bounds its own contact terms, not the newly separate abilities contribution.

## Tiers and optional locks

The existing two-byte roster footer is now fully assigned:

| Word mask at record `+0x52` | Owner |
| --- | --- |
| `0x001F` | Existing depth locks |
| `0x1EE0` | Existing seven ability flags |
| `0x0100` | Existing cosmetic star |
| `0x2000` | Existing Guardian cap |
| `0xC000` | New two-bit ability tier |

The codec stores the tier in physical `+0x53` bits 6..7, exposed as
`PlayerRecord.ability_tier`, with values Unranked/Star/Superstar/X-Factor
0/1/2/3 and authoring limits 0/2/4/7. Existing raw codec keys and fixed
0x54-byte records remain compatible. CSV adds a named tier column; the
existing sparse JSON and signed-save codec carry these masked footer edits.
Stars are cosmetic and independent. This revision neither changes their
native decal nor claims three visually different decals.

**Compatibility decision:** merely loading a legacy tier0 player never changes
its flags. Runtime tier0 retains the full v1 permission contract, with no new
rating effects. Explicitly selecting Unranked in the new editor clears flags;
selecting a lower tier retains abilities in the displayed order up to its
capacity, with a reversible receipt. A tiered player with excess flags gets
zero effective stored abilities at runtime, so raw CSV/import edits cannot
bypass the tier limit. An unlocked move still works without a stored flag.

All three settings are Boolean, default True when the existing `abilities`
opt-in is enabled:

* `lock_right_stick`: stick directions/gestures and stick-click hurdle require
  Right-Stick Moves. A directional juke also needs Juke when special locks are on.
* `lock_special_moves`: each mapped special move requires its v1 permission.
* `lock_speedster`: movement Speed above 99 requires Speedster. When off,
  unflagged raw Speed 100..127 uses the same bounded extension as Speedster.

With both move locks off, native charge generation/readiness/consumption is
restored, including noncarriers and callers outside the v1 move map. With
either move lock on, the v1 conservative live-carrier/known-consumer policy
remains. The GUI and runtime help spell out this material consequence. The
existing exact `(franchise mode 2, regular stage 8, configured row 0..17)`
off-week still disables stored abilities. Disabled locks remain disabled in
that week; turning a lock off cannot grant a rating bonus. There is no new
week or simulated-game effect. Omitted API settings preserve installed values;
changing any installed setting requires a rebuild.

## Assignment and editor

`nfl2k5_abilities_editor.py` supplies preview plans, exact receipts, strict
capacity/identity validation, idempotent replay and masked undo. Every row is
validated before any record changes. Foreign masks, duplicate/replaced
identities, mixed source/destination state, invalid signed ratings and stale
preview hashes refuse atomically. Undo preserves unrelated rating, depth,
star and Guardian edits. Reusing a document/source invalidates the old GUI
callbacks; WIRING explains receipt replay through the parent shared undo
stack when other roster pages replace the composed document.

The optional assignment replaces tiers/flags only for primary NFL records
with at least one club membership 0..31. It ranks each native position code
by the mean of that position's four existing key ratings, with pool index
breaking ties. Rank 1 gets X-Factor; ranks 2..ceil(N/3) get Superstar; the
remaining top N get Star; other eligible players clear. Rating range is
0..127. Free agents, historic-only records, draft prospects and templates are
excluded. The rules are deterministic and heuristic, not player scouting.

Candidate abilities fit broad roles: skill offense gets carrier moves,
offensive linemen Strength, defensive backs Jumping/Strength, and front-seven
players Pass Rush/Strength/Jumping. Speedster is considered only for raw
Speed 100..127; no rating is raised. Stick permission is added only with Juke
and spare capacity. Specialists may receive a tier without an ability,
because a proved kicking ability is not available. Users can override these
choices within capacity.

The retail pass with N=10 reviewed **1,696** eligible club records and changed
**170**: **17 X-Factor, 51 Superstar, 102 Star**. It changed exactly **217
footer bytes**, preserved the resource size, replayed through the existing
roster JSON writer, and undid to byte identity across the full body. All
2,547 retail records had zero footer bytes before assignment. Full private
receipt: `.scratch/abilities-v2/retail-assignment.json`.

* Retail ROST body SHA-256:
  `b1164eeed262988dc97d840ba59f6274c1f5d4505249474e4cafd4e322d9f7ae`.
* Assigned body SHA-256:
  `054422977d2d80853216f161016ef7ff8e998b217880aebc1d743c3754fb9f38`.

`abilities_panel_qt.py` is the new owned Rosters page: per-player checkboxes,
tier chooser, three lock switches, whole-league assignment preview table and
one transaction per application. Offscreen tests cover capacity refusal,
stale previews, no mutation on selection, shared undo/redo callbacks, masked
neighbor preservation, receipt export and Build-setting signals. The protected
Rosters shell currently still hosts its v1 controls until Claude applies
WIRING. The default runtime path already selects the upgraded owner with all
locks on; custom locks and the new page require that protected connection.

## Allocation, references, source evidence and limits

Actual request: **1,344 RX bytes**, including 1,061 instruction bytes, 277
bytes of immutable tables/alignment, and 6 bytes of final padding. **Zero RW,
zero additional RO**. The 1,536-byte budget leaves **192 bytes**. GNU assembly
reproduces the checked-in template. The complete budget plan was run first
with 1,536 reserved in a scratch fixture and then with the real request. No
allocator page count, retail cave, unknown address or protected reservation
file was changed.

The new hook replaces `83 ec 08 8b 41 30` at `0x17B010`, replays the displaced
`sub esp,8; mov eax,[ecx+0x30]` and resumes at `0x17B016`. It forwards exactly
one stack modifier and returns with `ret 4`. Registers/flags around the added
work and the lower x87 stack are preserved; effect writes are stack scratch.
Existing wrappers still own their native charge fields. Integrity tests cover
each hook, code/table/configuration/padding seals, corrupted dependencies and
all lock combinations. Old v1 allocation geometry is rejected, not migrated.

The authority includes the brief, RC86 changelog, all 102 prior ASTRA report
inventory entries, and the relevant full abilities, roster, Guardian,
Momentum and allocator reports. The read-only hub abilities memo and local
Ghidra corpus guided byte checks. Retail XBE SHA-256 remains
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
The inventory and hashes are retained under `.scratch/abilities-v2` for a
continuation; none of the other worktrees was modified.

**PROVED:** product footer ownership, zero retail census, exact host
round trips, bounded native arithmetic/ABI, complete owner composition and
the tests below. **HYPOTHESIS:** universal freedom from retail aliases, native
clone/reuse persistence, complete save lifecycle, loader acceptance, gameplay
balance and visible outcomes. The two tier bits use the existing footer
channel; a zero census is not advertised as a whole-program alias proof.
The native clone omits these footer fields; Guardian's clone hook copies only
its own flag. No unproved clone/save migration hook was installed here.

The six suggested independent effects **Sure Hands, Ball Hawk, Big Hitter,
Cannon, Deep Threat and Shutdown are not implemented**. All 16 footer bits
are now owned. Even one extra byte per retail player would need 2,547 bytes
before identity/migration metadata, beyond the remaining 192-byte RX-only
budget with no additional state/table allowance. Stealing a rating/style or
Guardian/depth/star bit would violate existing owners. An independent
catch-in-traffic, interception-window, fumble-on-hit, arm-cap, deep tracking or
reaction hook also needs its own full native consumer and lifecycle replay.
This task does not give those names to unrelated attribute edits or claim
that a pass-rush input guarantees a successful rush. A later design needs
explicit expanded storage and save ownership before exposing those toggles.

## Verification and disk decision

Free root space was **99,629,555,712 bytes**, already below the brief's 100 GB
floor. No real-disc build was started. No disc/pack copy exists in this
delivery. The bounded manifest uses the established Recorder around every
current XBE gate writer plus an alternate retail season-rules probe; it
inherits no stale reservations or source fingerprints. It validates complete
changed-byte attribution, live owners, section seals and source drift, and
explicitly says `real_disc_build=False` and
`production_regeneration_required=True`. The oracle's historical image-step
names are labeled as XBE-only probes. This proves executable ownership, not
resource transport or a production disc build.

The final scratch manifest pins **276 source files**, attributes **10,628
reservation spans** including the complete abilities owner, and validates the
resulting XBE SHA-256
`caf9c08a1a3e44742ef79b393a096f443b5df69ca43cecf3c37d1ec81c9e56ce`.
Manifest SHA-256:
`a881afff6e698b2827f849a68d266d9cccdb88cadb121f759cc05171d834af2d`.
The final ABI review additionally preserved the native volatile ECX/EDX
outputs; all five effect replays compare complete general-register results
against the original getter. All final composition results below use that
1,344-byte revision and this fresh manifest where required.

The first manifest run correctly refused an unobserved 12-byte ESPN importer
edit: its static `XbePatch.apply` alias bypassed the module observer. The
test-only alias now calls the same observed real writer; its actual bytes
are recorded. No ESPN source was edited and no unattributed-byte guard was
relaxed. The second manifest run passed. The first effect test also caught
the fixture's own x87 measurement store outside stack scratch; its exact
destination is now identified separately from runtime writes.

All suites run standalone with `python3 tests/mod_editor/<filename>.py`.
Qt suites use `QT_QPA_PLATFORM=offscreen`; no visible application was launched.
The final v2 replay also writes these private receipts:

```sh
NFL2K5_ABILITIES_PROOF=.scratch/abilities-v2/effects-replay.json \
NFL2K5_ABILITIES_ASSIGNMENT_PROOF=.scratch/abilities-v2/retail-assignment.json \
python3 tests/mod_editor/test_nfl2k5_abilities_v2.py
```

The bounded manifest is generated before its dependent suites:

```sh
NFL2K5_ABILITIES_MANIFEST_OUTPUT=.scratch/abilities-v2/final-manifest.json \
python3 tests/mod_editor/test_nfl2k5_abilities_v2_manifest.py
```

For the cave-reference gate, cave oracle and existing owner-manifest suites,
set `NFL2K5_CAVE_MANIFEST=.scratch/abilities-v2/final-manifest.json`. The memory
write gate and pairwise matrix use their full current owner union directly.
The pair matrix has 17 named variants, 135 applicable distinct-owner pairs
(the two MyCareer formats are mutually exclusive), both installation orders,
and 11 additional strict partner-guard cases.

**600 test cases across 18 standalone suites: 599 pass, 1 existing evidence skip, zero failures.**

| Standalone suite (`tests/mod_editor/`) | Tests | Result | Seconds | Peak RSS KiB |
| --- | ---: | --- | ---: | ---: |
| `test_nfl2k5_abilities_runtime.py` | 12 | 12 pass | 55.124 | 150,964 |
| `test_nfl2k5_abilities_unicorn.py` | 12 | 12 pass | 20.463 | 308,460 |
| `test_nfl2k5_abilities_v2.py` | 15 | 15 pass | 83.600 | 396,220 |
| `test_nfl2k5_abilities_v2_qt.py` | 5 | 5 pass | 1.275 | not recorded |
| `test_rosters_reserves_abilities.py` | 13 | 13 pass | 24.234 | not recorded |
| `test_rosters_reserves_abilities_qt.py` | 7 | 7 pass | 7.056 | not recorded |
| `test_nfl2k5_roster_records.py` | 108 | 107 pass, 1 skip | 24.713 | not recorded |
| `test_nfl2k5_momentum.py` | 23 | 23 pass | 64.700 | 276,672 |
| `test_nfl2k5_momentum_collisions.py` | 16 | 16 pass | 86.873 | 440,148 |
| `test_nfl2k5_abilities_v2_manifest.py` | 2 | 2 pass | 369.891 | 247,900 |
| `test_xbe_patch_memory_writes.py` | 95 | 95 pass | 1287.510 | 340,740 |
| `test_xbe_patch_cave_references.py` | 107 | 107 pass | 1218.544 | 525,088 |
| `test_nfl2k5_owner_pairwise_composition.py` | 146 | 146 pass | 1270.957 | 192,156 |
| `test_nfl2k5_cave_oracle.py` | 28 | 28 pass | 376.225 | 920,200 |
| `test_nfl2k5_screen_hooks_manifest.py` | 3 | 3 pass | 7.959 | 128,252 |
| `test_nfl2k5_defensive_try_manifest.py` | 3 | 3 pass | 9.119 | 154,128 |
| `test_nfl2k5_music_playlist_manifest.py` | 2 | 2 pass | 7.557 | 131,464 |
| `test_nfl2k5_my_career_manifest.py` | 3 | 3 pass | 12.262 | 136,020 |

The measured runs use `/usr/bin/time -v`; the largest recorded process is 920,200 KiB (under 2 GiB). Times are unittest elapsed seconds. The table counts each final suite once; superseded native-byte runs are excluded. No final v2, manifest, oracle or owner-composition case was skipped. Private logs and exact JSON results remain in `.scratch/abilities-v2`, about 7.5 MB total.

The roster suite skips its existing portrait-catalogue test because
`reports/assets/nfl2k5_player_portrait_compatibility.json` is absent in this
checkout. That is unrelated to footer authoring. Its other 107 cases pass;
the new ability/tier/save/retail assignment and offscreen page cases all run.


Additional checks passed: `python3 tools/nfl2k5_abilities_runtime_assemble.py
--check`; `python3 tools/nfl2k5_xbe_space.py plan --requests
tests/fixtures/nfl2k5_allocator_beta62_requests.json`; compilation of changed
Python modules/new suites; staged diff whitespace and protected-path checks.
The actual request plan has 45 rows and a 12,300,288-byte XBE, without building
a disc. Read-only runtime CLI inspection reports retail/model2/all locks true.
The authoring CLI used the loose retail extraction with `--top-n 10` and
`--output .scratch/abilities-v2/authoring-cli.json`, producing the same
170-player receipt and compatible `roster_edits` envelope.

Both capability handoffs pass merged registry schema/semantic validation
(118 rows) and strict file/dotted-command checks for their own paths. The full
existing-registry file check refuses the **pre-existing missing
`docs/research/apf_audio.md`**. No validator or absent evidence was fabricated
to suppress that refusal. The production registry itself is a WIRING handoff.


## Noah's witness list

1. After protected wiring and production manifest regeneration, build from a
   supported base with a known roster/save, record XBE hash, v2 settings, tier
   flags and assignment receipt. Boot, enter practice/exhibition/franchise,
   save/reload and verify selected players. Rebuilding a disc does not migrate
   an existing franchise roster.
2. Compare each effect at identical ratings and conditions, tier0/1/2/3,
   missing/present flag, healthy/injured/fatigued, human/CPU and both teams.
   Measure ordinary cuts for Juke, physical contests for Stiff-Arm, jump
   behavior for Hurdle, contact outcomes for Truck and rush outcomes for Spin.
   Record unsuccessful outcomes too; none is guaranteed by this patch.
3. Compare Truck with Momentum movement/contact/collisions independently on
   and off, stationary/moving carriers and defenders, low and near-cap ratings,
   both contact reads and repeated tackles. Watch balance and animations at the
   combined maximum bonus.
4. Try all eight lock combinations with zero-flag and tiered players, every
   direction/gesture/click and button move, all three controller layouts,
   multiple controllers, CPU carriers, scrambles and kick/punt returns.
   Verify ordinary steering and passing/kicking/QB-evade inputs.
5. With either move lock on, compare noncarrier powered tackles, catches,
   blocks and every unclassified consumer. With both off, confirm retail
   charge behavior returns. Test ready meters, possession/controller changes,
   turnovers, direct initializer transitions and powered moves with missing
   base versus stick permission.
6. Compare Speed 99/100/127 with flag and lock independently on/off, Momentum
   and ramp settings, starts/cuts/stops and real distance. Do not interpret
   127 as a guaranteed 28% displacement increase.
7. Enter and load directly into the off-week, then advance past it. Compare
   identical week numbers outside regular-season franchise. Stored effects
   return; disabled locks stay disabled; cosmetic stars remain independent.
8. Preview N=10, inspect names/tiers/flags, apply, undo and redo, export CSV,
   roster JSON and a signed save copy. Check an untouched player, free agent,
   rookie template, specialist, shared all-star identity, Guardian cap and
   depth locks. Test tier downgrade, deliberate overfill, trade/release,
   created/cloned/reused identity and season rollover. Report lost/footer
   inheritance separately; no native migration is claimed.

No entry on this list is witnessed in this session.

## Commit delivery

This report is included in the explicit-path commit
`Add abilities v2 effects, tiers, and editor locks` on
`astra/r65-abilities-deeper`, with parent
`be99b324f34d536c625efcba7e7ea5d4f104fd2b`. All 19 intended paths are supplied
to both `git add -- <paths>` and `git commit ... -- <paths>`. The worktree
metadata accepted staging, so the bundle fallback was not needed. The commit
ID is recorded in the final delivery and private commit receipt rather than
creating a self-referential report hash. No push is performed. `ASTRA_BRIEF.md`,
`.scratch/`, original game bytes and every protected source are excluded.
