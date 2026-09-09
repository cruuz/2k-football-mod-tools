# r65 Deep-zone corner tiers v2

EXPERIMENTAL / UNWITNESSED. No console, emulator session, GUI, audio device or
network was used. The instruction fixtures below are CPU evidence, not Noah's
gameplay witness. Shared product integration is in `WIRING.md`; protected files
were not edited. Nothing was pushed.

This delivery implements sustained deep-zone corner orientation and a separate
press-bail tier. Both are off in every product preset. The earlier
`ASTRA_DEEP_ZONE_TIERS_REPORT.md` and `nfl2k5_zone_facing` audit describe the
historical deferred implementation; this report supersedes those two rows.

## Implementation and decisions

`nfl2k5_deep_zone.py` owns three pinned hooks: native zone initializer tail CALL
at `0x1A66D5` (5 bytes), native steering entry `0x1A4170` (6 bytes), and native
directional-row CALL at `0x2FCADD` (5 bytes). It retains the original initializer,
both zone callbacks, target selector, steering/avoidance, directional bank,
rate/turn integrator, animation sampler and world transform. QB Spy callback
hooks, zone-drop's `0x1A65D1` call and trail's `0x2FC9F0` prologue retain their
owners. The Spy Python validator now recognizes the completely verified new
planner neighbor; Spy runtime bytes are unchanged. Each owner verifies the
other's context without recursive status calls.

The budget table had no named deep-zone row. Decision: use 2048 RX and 256 RW
from existing v3 capacity, with no added pages or borrowed cave. Eleven packed
21-byte records consume 231 RW bytes. Each stores actor, gameplay state,
assignment pointer, snap-time QB cache identity, original native throttle and
one policy byte. All offline RW bytes are zero; immutable constants are in RX.
The committed budget fixture and complete owner union include these requests.
Generated content is 1616 bytes: 1588 instruction bytes and 28 constant/config
bytes, leaving 432 RX padding bytes and 25 RW spare bytes.
The final budget plan remains 12,300,288 bytes with 50,576 RX / 4096 RW / 8104 RO
bytes available to new owners before alignment.

Only an exact native CB (position 18), defensive-team player, ordinary deep
zone `(mode & 12) == 8`, matching native zone registration and live zone task can
enter. CPU owner, player lock, Spy assignment, special action, descriptor, bank,
finite geometry, offense direction and bounded timestep/throttle checks retain
native exceptional behavior. Bail additionally requires exactly three native
bit-8 zone records and actual initial depth from zero through two yards.

The controller keeps a retained facing reference toward the saved QB. Its
Schmitt thresholds are 10 degrees to begin correction and 5 degrees to stop;
reference movement is capped at 180 degrees/second for positive dt <=0.1s.
It uses native bearing and effective quaternion-facing functions. The DB bank
has directional rows at 45-degree intervals: actual body orientation is a
cone, not exact eye tracking, and the reference slew limit is not a bound on
individual synthetic body-heading row transitions. Native blending with real
assets remains a witness item.

Throttle is capped at 0.84 before the native steering routine can set the fast
run latch, and again before row selection. Capping only after planning failed
in a repeated native probe: the fast transition overwrote the desired movement
direction with facing. Moving the cap ahead of that decision preserves native
local aiming and avoidance. The wrapper clears the inherited fast latch in
its eligible scope. It never substitutes the QB for the native receiver target.

A saved-QB native pass ends policy with diagnostic byte 0x12. Other exits use 2:
other passer, handoff/free ball/turnover, changed QB, QB at/past the LOS, phase,
assignment, task, player control, special action or invalid geometry changes.
The retail-selected receiver one yard beyond the corner also ends the policy.
An invalid zone mode/index retires a matching actor record, so briefly leaving
scope cannot resurrect it. Only a native zone initializer re-arms it. Bail alone
ends at seven yards and restores the initial native task throttle; the older
initial-drop owner's cap remains authoritative if installed. Facing selected
alongside bail continues beyond that bail depth limit until a normal exit.

`nfl2k5_deep_zone_bail.py` authors press alignment for an explicit native-personnel
front/coverage pair. It requires two plain Defense Start/Zone corner chains and
three terminal >=18-yard zone assignments, refusing ambiguous additional deep
assignments. This is authoring candidacy; runtime independently certifies three
native deep registrations. It changes Defense Start to LOS-relative mode 1,
zero added depth, and the original formation lane. Native `0x183F60` supplies
the legal player-scaled minimum (133 cm in the fixture). The existing formation
compiler clones just those chains inside the fixed PLAY span. Other users of
the same original chains are isolated; coverage-row formation links remain
shared and are listed in the receipt. Different linked formation lanes refuse.
No automatic whole-playbook conversion is performed.

Both modules provide bounded, create-new-file CLI writers. XBE apply/status
validate allocator geometry, seals, code/constants/padding, hooks and native
prerequisites before mutation. Replay preserves omitted installed settings;
changing tiers or disabling requires rebuilding from base. Foreign code,
mixed hooks and nonzero offline RW refuse even after section digest repair.

## Native evidence and limits

PROVED in the bounded supplied-state fixtures:

- Real packed-opcode decoders, complete zone initializer/task allocation and
  both native callback identities feed ordinary native locomotion. Straight
  deep drops move backward while facing the QB in both field directions.
- `0x35AF40 -> 0x35AD60 -> 0x1CB950 -> 0xA0B90 -> 0xB7430` executes the native
  pass animation callback, trajectory calculation, ball release and event
  store. `B7430` stores the actual actor at `[E602EC]+0x1C8`; the ball becomes
  unowned. The native callback's only substituted leaf is the existing fixture's
  roster attribute lookup `0x17B010`. Event identity is not inferred from losing
  possession. The distinct +0x1C4 and +0x1D0 fields never count as this pass.
- The existing fixed-span compiler changes the selected ATL pair and replays
  exactly. Its authored start node executes through `0x2D6550 -> 0x2D5860` to
  the legal press target; the subsequent native zone drop and row turn execute.
- Full before/after dispatcher trials retain all 22 synthetic actors and all
  27 `0x11A7C0` phases, including task scheduling, steering filtering, root
  sampling and world transforms. The fixture supplies neutral directional
  clips, not retail motion assets. It observes a native filter startup transient
  before sustained backward travel. That transient is retained in the replay.

The fixture seeds native zone registrations, task/roster objects, opponent
coordinates and compressed neutral clip data. The native start target is used
for the final presnap placement in the fixture; a complete real presnap walkout
and all adjustments are not witnessed. After snap, Python does not move the
corner. No native zone planner, target selector, row selection, sampler,
transform or dispatcher phase is substituted. Full-frame hardware/audio and
roster-rating leaves are enumerated in the replay JSON. Supplied object callbacks
also include constant height (`FLD1; RET`) and empty task handlers inherited
from the fixture. These supplied callbacks are distinct from the enumerated
retail-address leaf replacements; they do not constitute retail asset evidence.

The committed `docs/mod_editor/nfl2k5_deep_zone_native_frames.json` contains
four complete 90-frame numeric replays, exact input/source hashes and fixture
limits. Both press replays use the same authored press start, isolating the
runtime bail change; the separate compiler/native-start test proves the
authoring change. They do not compare full retail presnap walkouts.

| Full-frame scenario | First / minimum / last depth (yd) | Final QB-facing error |
| --- | --- | --- |
| Initial-drop + trail + Spy, facing off | 6.00 / 5.75 / 14.34 | 35.09 degrees |
| Same owners, facing on | 5.98 / 5.74 / 14.37 | 21.17 degrees |
| Authored press, bail off | 1.45 / 1.21 / 10.26 | 53.00 degrees |
| Same authored press, bail on | 1.44 / 1.19 / 10.20 | 53.09 degrees, policy released |

The roughly quarter-yard startup advance is native filter behavior in both
variants. Bail's final facing is measured after its seven-yard release, so it
is not an active-controller cone result. The separate 100-frame straight-drop
tests cover both field directions with over eight yards of backward travel
and less than one degree of facing error. A 12-yard lateral QB displacement
settles inside 25 degrees while the retained reference meets its slew bound.

HYPOTHESIS / needs Noah: retail clip blending and visual quality, realistic
receiver selection and simultaneous threats, early human takeover, press
walkout after shifts and motion, collision/contact transitions, late
man-to-zone conversions, catch/pass-reaction results, useful football balance,
and production UI/build behavior after protected integration. The one-yard
receiver release uses the selected receiver only. This is neither match
quarters nor a new interception/reaction modifier.

## Validation

All commands ran from this worktree with plain Python/unittest. The oracle and
two gate commands used
`NFL2K5_CAVE_MANIFEST="$PWD/.scratch/deep-zone-oracle-manifest.json"`.

| Command | Result |
| --- | --- |
| `python3 tests/mod_editor/test_nfl2k5_deep_zone.py -v` | 10 passed, 160.823s |
| `python3 tests/mod_editor/test_nfl2k5_deep_zone_frames.py -v --record` | 11 passed, 250.850s; four complete 90-frame replays |
| `python3 tests/mod_editor/test_nfl2k5_deep_zone_frames.py FrameTests.test_bail_without_initial_cap_resumes_native_run_and_both_tiers_continue -v` | Added twelfth native case passed, 14.655s |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 99 passed, 860.701s |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 111 passed, 991.704s |
| `python3 tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py` | 146 passed, 848.897s |
| `python3 tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py -k deep_zone -v` | All 16 deep-zone pairs passed after final Python guard changes, 96.024s |
| `python3 tests/mod_editor/test_nfl2k5_allocator_scaleout.py` | 23 passed, 450.649s |
| `python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` | 28 passed, 215.402s |
| `python3 tests/mod_editor/test_nfl2k5_qb_spy_runtime.py` | 13 passed, 259.153s |
| `python3 tools/nfl2k5_deep_zone_assemble.py --check` | Generated bytes match assembly |
| `python3 tools/nfl2k5_xbe_space.py plan --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json` | 47 requests fit existing v3 geometry |
| Python compilation and `git diff --check` | Passed |

The final native file has twelve cases: the passing eleven-case run plus the
subsequently added, independently passing bail-release regression above.
The owner suite also exercises all 24 installation orders of deep-zone,
initial-drop, trail and Spy, with byte-identical final output and replay.
Both gates use the complete owner union in both installation orders. The
pairwise suite has 17 owners, including deep-zone and the initial-drop owner.

The source-pin refresh is the brief's explicit stale-manifest procedure. It
retains canonical reservations and replaces `source_sha256` with current
`nfl2k5_cave_manifest.source_fingerprints()`. Gate projection verifies the
actual sealed allocation union and exact native hook pins before publishing
test-only spans. Source checks remain enabled. Scratch manifest SHA-256:
`48032d0eef1a274db29aca27d611599e7e97e7804387413f87181f54cf6224e4`.
This is not a regenerated production disc manifest. The protected canonical
manifest still has eight mismatched source pins on this worktree; its release
regeneration remains assigned to Claude in `WIRING.md`.

Early failing probes were resolved before the final results above. The complete
stack exposed kickoff's owned `0x183F60` prologue inside the new presnap guard;
normalization now requires kickoff's complete validated owner. The ABI fixture
needed an explicit stop hook at the restored native boundary because Unicorn
reused a cached translation block. Test expectations now respect the older
initial-drop cap after bail release, exercise a lateral displacement large
enough to select another native row, and sort the merged capability ids.
No failing assertion was disabled or runtime prerequisite left unpinned.

Largest measured process RSS was 527,492 KiB (about 516 MiB), in the final cave
gate; the native suite peaked at 213,164 KiB. Inputs were one bounded
11,948,032-byte retail XBE and a bounded 78,768-byte ATL PLAY resource read from
the archive through its existing reader. No whole disc/archive load or
disposable disc build occurred. Scratch remains under 200 MB; disposable
decompiler excerpts and probes were removed. No generated XBE, disc, pack or
retail animation assets are retained or committed.

## Delivery and integration

The 27-file protected/scope audit matches base
`be99b324f34d536c625efcba7e7ea5d4f104fd2b` byte for byte, including the read-option,
MyCareer, ESPN and coverage-trail modules. The only existing gameplay owner
changed is Spy's necessary Python neighbor validator. Protected dispatcher,
BuildPlan, GUI, allowlist, runtime closure and production manifest work is
specified concretely in `WIRING.md`.

The explicit 20-path `git add` failed because the branch's external Git metadata
is read-only (`index.lock`: read-only file system). The authorized fallback
uses an isolated scratch Git repository, the same base and branch name, and an
explicit-path source commit. Its deliverable is
`.scratch/deep-zone-tiers.bundle`; `git bundle verify` and the commit/path audit
are recorded in `.scratch/deep-zone-commit-result.json`. The source files stay
in place. `ASTRA_BRIEF.md` and `.scratch/` are excluded from the commit. No push
was attempted.

## Noah's witness list

1. A/B the same deep-zone calls and ratings with facing off/on: QB holds,
   drifts each direction, pump fakes, releases, scrambles across the LOS,
   hands off, fumbles and recovers. Record effective facing, native callback,
   selected receiver, ball owner, +0x1C8 actor and policy byte each frame.
2. Outside go, seam, crossing and comeback routes; two simultaneous threats;
   receiver one yard beyond the CB. Confirm permanent release for that
   assignment, native turn/run/ball response and clean next-snap re-arm.
3. ATL formation 22, front 1 / coverage 13 authored press pair, both corners
   and field directions. Check actual presnap depth after shifts/motion,
   backpedal turn and seven-yard bail-only release. Also test existing press
   three-deep calls, off corners, four-deep calls, flats, safeties and man calls.
4. Toggle player control, defensive lock, special actions and Spy assignments
   during the play. Check stops, contact, bump/jam, stumble, recovery and late
   zone transitions. A longer slow turn or startup step toward the LOS needs
   attention before promoting the feature.
5. Repeat with initial-drop, coverage-trail, Coverage and catch options
   separately and together. Confirm the two tiers remain explicit opt-ins in
   all presets after Claude wires the protected product files.
