# 7-on-7 practice v2

2026-09-08. Branch `astra/r65-seven-on-seven-v2`, base `be99b324`.
**EXPERIMENTAL / UNWITNESSED.** The owner port, book repair, exact replay,
composition tests and protected integration handoff are delivered. Noah has not
played this revision. Protected product integration is specified in the final
r65 section of `WIRING.md`; those implementation files remain unchanged.

## What was built and decided

Ported the feature-specific changes from local branch
`local/seven-on-seven-v2`, commit
`f3428647a3b6c6ab6244b2777ddc283acf313f40`, using read-only Git objects. This
avoids importing that old branch's unrelated beta-58 changes. The beta-63
compiler's `_seven_on_seven_source` pin and exact-request check are retained.
The main repository working files and other worktrees were not changed.

The practice book now puts offensive tackles and guards at the retail I Pro
line positions and gives them the retail `50 All Go` pass sets. The centre
retains the retail snap and pass set. Defensive linemen use retail 4-3 line
positions: three have the existing tutorial idle assignment; the right end
at `(365, 0)` uses the retail lane-11 rush with its requested delay raised to
four seconds. The two old Power Pocket detours are removed. The user's option
remains under the user's control; it should be Off for the delayed-rush witness.

This remains a passing-practice approximation with eleven players on each
side: QB, snapper and five skill players against seven coverage players, plus
the line and delayed end. It does not remove roster actors or guarantee a
four-second whistle, a free rush, or no blocking contact.

The fifth Practice Type still selects mode 1 and loads `PRACTICE-pb.iff` for
both teams. The four ordinary choices clear the flag and use their retail
stubs. Basic Training retains its retail loader path; other mode values use
team books even with a stale flag. Menu increment and decrement each cycle
through all five choices, including repeated wraparound.

## PROVED: the authored out-of-bounds cause is removed

The recorded earlier witness was a huddle that never broke. The local memory
and v2 branch identify the cause: the old `+/-2300 cm` targets were relative
to the ball, while practice can put the ball on either `+/-281.94 cm` hash.
A target then reached `+/-2581.94 cm`, about **143.54 cm beyond** the retail
`+/-2438.4 cm` sideline. The old verifier checked only the unshifted coordinate.

The regression reads the actual retail hash constants at `0x4F0F40` and
`0x4F0F3C`, reproduces that old overrun, and checks all eleven positions in
all five new formations at both hashes and centre field, in both directions:
**330 cases**, with about **785.46 cm minimum lateral clearance**. Production
verification checks every encoded x variant using conservative 282/2438 cm
bounds. Separate tests compare line positions, pass-set nodes, centre snap,
QB opener and end-rush lane directly with their retail donors.

This proves that the new authored targets are inside the field. It does not
execute the complete huddle walker or prove that every player's live arrival,
animation, collision and readiness state completes. Actual huddle break and
repeated snaps remain Noah's required witness.

## PROVED: the three earlier crash fixes survive

- The only owned runtime byte remains at writable `0xA69970`; the cave contains
  instructions and immutable tables. Native switch and loader tests run with
  `.text` protected read/execute, reproducing the permission boundary that
  caused the first freeze.
- Every real formation-menu link keeps bit `0x8000`, group 3, and its bounded
  play index; empty slots remain `0x07FF`. All 21 new menu links are checked.
- The existing cave remains exactly `0x1AC170..0x1AC260`, ending before the
  live callback at `0x1AC260`. The next 64 bytes are byte-identical to retail;
  the complete cave-reference gate also retains its retail-reference scan.

The owner uses **103 instruction bytes** of the existing 180-byte code area
inside the **240-byte reservation**, plus the existing one-byte writable flag.
`OWNER` is `nfl2k5_seven_on_seven`; `REQUESTS=()` adds **zero** RX, RW or RO
budget. The 42-request full allocator union still produces a 12,300,288-byte
v3 XBE. The committed budget table and allocator page counts are unchanged.

Seven complete edit spans change **274 retail XBE bytes**, including the
`.text` digest. The output remains 11,948,032 bytes when installed alone:

```text
retail: 73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9
v2:     47e0f8d1e1b3892c0c4387a7a3d083aabbb5a9de5c0acd611a4d625f16f022a8
```

`status` checks all nonempty section digests, the complete seven-site state
and both unchanged Power Pocket reads. `apply` is idempotent. Partial installs,
foreign cave bytes, stale digests, and v1 rush detours paired with v2 code
refuse before a write/repin. Old installations require a rebuild from base.

## PROVED: book composition and transaction behavior

The resource stays **78,768 bytes**, including its unchanged 32-byte wrapper.
It has **28 formations, 42 plays, 16 personnel groups and 703 nodes**: three
passing formations with nine concepts and two defensive formations sharing
six coverages. Each supported source changes exactly **4,135 bytes**. All
42 plays pass the existing validator. Original drill assignments and formation
geometry survive; their AI-exclusion flag is the intended original-play edit.

The old writer rejected an already depth-role-processed practice book. Added
full SHA-256 pins for exactly the retail and pooled-position resources with
the 12-byte depth-role transformation. The six pooled-position bytes are
independent. The final new personnel rows also pass through the existing role
writer when the source already carries that transformation.

All six orders of 7-on-7, pools and roles produce identical bytes. Four exact
output pins recognize retail-based, recoded, role-processed and combined v2
books. Recognition covers the whole wrapper, unused space, routes, links,
old drills, personnel and geometry; a merely valid custom book is foreign.
Pure-byte and archive replays return zero changed bytes and exact hashes.

The archive writer rechecks its source immediately before the fixed-span
write, verifies read-back and restores the complete original resource after
a short write, a write exception or a read-back mismatch. If rollback itself
fails, the error explicitly says to discard that output copy. Unsupported
sources cause no write. Existing `OuterImage` context management closes all
handles; no new raw descriptor or archive transport was introduced.

Complete source/output hashes, counts, byte receipts and geometry measurements
are in `docs/mod_editor/nfl2k5_seven_on_seven_v2_receipts.json`. That document
contains no executable, disc or archive payload.

## Composition, manifest and test-fixture corrections

Both XBE gates now install v2 through `tests/nfl2k5_allocator_stack.py`, so
forward/reverse tests actually change its order among the owners. The shared
owner-call list also drives individual 7-on-7 pairs against the complete
allocator stack, including the existing read-option diagnostic, MyCareer,
Historic team reload and coverage-trail owners. Their implementation modules
were not edited. Legacy dispatcher owners and allocator-first/last paths have
separate pair coverage. V2 also joins the pre-existing general pair matrix.

The manifest builder includes its empty requests, real installation/replay,
synthetic-owner probe and status check. A freshly observed **executable-only**
scratch manifest contains **10,599 reservations from 107 writer calls**, with
**275 source fingerprints**. Its composed XBE hash is:

```text
3ba8c6700ae7d7b217fa85ee6d86c0695892a700e75d73a36e4f9bae2befb107
```

The recorder rejects unattributed bytes and verifies ownership/source pins.
Two test-fixture defects were corrected without weakening production checks:
the shared synthetic XBE's section table at `0x200` overlapped certificate
bytes at `0x310`; it now uses retail's `0x370`. The full-stack adapter captured
the Historic team's apply function before recorder wrapping, hiding the
existing write at `0xC2319`; the test call list now captures the observed
function. No Historic-team owner behavior changed.

The oracle's release-disc assertions remain in place. A scratch manifest with
no image steps additionally requires the exact executable-only model, a path
inside this tree's `.scratch/`, changed-byte observations for the runtime,
calendar and 7-on-7 owners, and `runtime_witnessed=False`. It never invents
`scorebug_runtime` or `season_2026` disc-build steps. The scratch manifest is
not a replacement for the protected release manifest.

## Validation

Final standalone command results are recorded below. Earlier iterations found
and fixed the synthetic section-table overlap, the missing position-pool
prerequisite in the new pair fixture, the recorder adapter omission, and the
oracle test's assumption that every scratch manifest came from a disc build.
Those failures were not ignored or converted into skipped safety checks.

Each command ran standalone with `/usr/bin/time -v`; the environment prefixes
below are part of the exact command. No test process reached 2 GiB RSS.

| Command | Result | Time | Peak RSS |
| --- | --- | ---: | ---: |
| `python3 tests/mod_editor/test_nfl2k5_seven_on_seven.py` | PASS, 19 tests | 3.211s | 337.9 MiB |
| `python3 tests/mod_editor/test_nfl2k5_seven_on_seven_v2.py` | PASS, 63 tests | 135.440s | 176.8 MiB |
| `python3 tests/mod_editor/test_nfl2k5_seven_on_seven_recode.py` | PASS, 5 tests | 0.236s | 33.5 MiB |
| `python3 tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py` | PASS, 130 tests | 815.478s | 180.8 MiB |
| `env NFL2K5_CAVE_MANIFEST=.scratch/seven-on-seven-manifest.json python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | PASS, 95 tests | 966.529s | 323.1 MiB |
| `env NFL2K5_CAVE_MANIFEST=.scratch/seven-on-seven-manifest.json python3 tests/mod_editor/test_xbe_patch_cave_references.py` | PASS, 107 tests | 1102.197s | 517.2 MiB |
| `env NFL2K5_CAVE_MANIFEST=.scratch/seven-on-seven-manifest.json python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` | PASS, 28 tests | 262.211s | 888.0 MiB |
| `env NFL2K5_CAVE_MANIFEST=.scratch/seven-on-seven-manifest.json python3 tests/mod_editor/test_nfl2k5_seven_on_seven_manifest.py` | PASS, 3 tests | 0.525s | 106.6 MiB |
| `env NFL2K5_GUARDIAN_MANIFEST_OUTPUT=.scratch/seven-on-seven-manifest.json python3 tests/mod_editor/test_nfl2k5_guardian_manifest.py` | PASS, 1 tests | 173.951s | 232.7 MiB |
| `env NFL2K5_CAVE_MANIFEST=.scratch/seven-on-seven-manifest.json python3 tests/mod_editor/test_nfl2k5_my_career_manifest.py` | PASS, 3 tests | 9.812s | 132.8 MiB |
| `python3 tests/nfl2k5_throw_tuning_test.py` | PASS, 39 tests, 1 skipped | 8.761s | 94.8 MiB |
| `python3 tests/mod_editor/test_nfl2k5_formation_play_writer.py` | PASS, 8 tests | 1.234s | 39.1 MiB |
| `python3 tests/mod_editor/test_nfl2k5_depth_roles.py` | PASS, 22 tests | 62.296s | 74.7 MiB |
| `python3 tests/mod_editor/test_mod_build.py` | PASS, 11 tests | 1.947s | 79.4 MiB |

**Total: 534 tests, 533 passed, 1 skipped; zero failures.**
The sole skip is the pre-existing throw-tuning test whose private authored
image is absent. All new feature, native, ownership and composition tests ran.

`python3 tools/nfl2k5_xbe_space.py plan --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json`
also passed. `git diff --check`, changed-source parsing, receipt JSON parsing
and byte comparison of all eleven explicitly protected files passed.

## Noah's witness list

Every item below is pending for the new revision. Retain the complete build
receipt, source/output XBE hashes, book hash and exact option settings.

1. After the protected integration, build a copied disc with only the explicit
   `seven_on_seven` opt-in, then with Advanced and Experimental settings.
   Keep the option Off by default in all three presets. Enter Practice >
   Scrimmage; cycle Practice Type both directions through all five choices.
   Select both offensive and defensive plays without a freeze or crash.
2. With Power Pocket Off, try Trips, Spread and Ace against Cover 43 and
   Nickel. Select all nine concepts and six coverages. Break the huddle and
   take at least ten consecutive snaps, changing sets between plays. Repeat
   on both hashes and with the attacking direction reversed, including
   red-zone and backed-up practice ball positions.
3. Check the centre snaps normally, the offensive line uses normal pass sets,
   the three idle defensive linemen remain stable, and the seven coverage
   players take their assignments. Watch for blocked arrivals, jitter,
   unexpected contact, running routes from linemen or a stalled play call.
4. Hold the ball through the intended four-second delay and compare a timed
   recording across repeated snaps. Confirm when the right end starts and
   whether it can beat the line. Repeat with Power Pocket On, then Off; the
   choice must remain under user control. Do not describe the delay as proved
   or as a whistle before this witness.
5. Leave 7-on-7 for Full Scrimmage, Special Move, Offense Only, Kickoff and
   Basic Training. Verify normal books, kick behavior and tutorial progress.
   Return to 7-on-7, quit to menus, start a regular game and repeat. With
   Franchise Practice enabled, enter/exit it and verify its roster and return
   destination. Check that a stale practice flag does not select the wrong
   book on a later entry.
6. Repeat with merged positions and depth roles, with the complete intended
   option combination, and after loading existing settings. Inspect play
   menus, repeated snaps, controller selection, field boundaries and frame
   pacing. An executable pair proof does not establish whole-game coexistence.

## Known gaps and delivery boundary

The in-game huddle, real delayed-rush timing, coverage behavior, original drill
completion, save/settings transitions and console loading are unwitnessed.
There was no game/emulator boot, GUI display, audio playback or network access.
Unicorn was used only for bounded instruction fixtures. No whole disc or pack
was loaded into RAM, and no retail source was written.

Disk inspection showed about 105 GB free (98 GiB). A 6.3 GB acceptance copy
would cross the brief's 100 GB floor, so no full-disc build was started. The
fresh manifest observes actual XBE writers only; resource proofs read the
single bounded practice entry. No acceptance disc or pack copy remains.
The scratch directory contains logs, JSON and patch/continuation notes.

`WIRING.md` specifies the existing dispatcher tuple and kwarg, four status
dictionaries, receipt keys, BuildPlan field, opt-in availability, all presets
Off, image gating, Retail/Patch help, a 30-character Build caption, allowlist
and runtime imports, and the required later release-manifest regeneration.
This restores the existing surface and adds no registry ID. The protected
product files and release reservation JSON were not edited.

The first explicit-path staging attempt succeeded. Final staging then failed:
`Unable to create .../index.lock: Read-only file system`. The brief
explicitly authorizes the bundle fallback, so the final commit is made with
explicit paths in isolated Git metadata under `.scratch/`, based on `be99b324`
and using the assigned branch name. The deliverable is
`.scratch/seven-on-seven-v2.bundle`, with the base as its prerequisite.
The edited files remain in this worktree. `ASTRA_BRIEF.md` and `.scratch/` are
excluded from the commit. No push is performed.
