# r62 gameplay levers

Branch `astra/r62-gameplay-levers`, base
`5f5b5047d42984ee41449c4a03669e0945a22f2a` (the supplied beta-61 stack).
**EXPERIMENTAL / UNWITNESSED.** No game, console emulator, GUI display, audio,
network or push was used. Native helper tests below use bounded Unicorn
instruction fixtures with synthetic objects; they are not played witnesses.
Qt ran offscreen. Retail sources and the research hub stayed read-only.

## Delivered and integration boundary

- `nfl2k5_coverage_slider.py`: direct Coverage response remapping, two pinned
  operand repoints, 16 immutable owned bytes, exact mapping and byte receipts.
- `nfl2k5_scramble_tuning.py`: a native acceleration curve selector for slow
  QB ball carriers, one pinned call, 160 immutable owned bytes, no new history.
- `nfl2k5_throw_arc.py`: flatter deep-flight speed table, strict reader/table
  recognition, idempotent apply, ballistic preview points, source-preserving
  transactional XBE/disc-copy adapter using the existing streaming writer.
- `nfl2k5_penalties.py`: an independent interface to the already-shipped Chop
  Block repair, retail-dead-toggle evidence, native truth table and complete
  composition with the existing rate profiles. No second stub is allocated.
- The existing Throw Distance & Arc panel offers flatter flight, exclusive
  selection against the other flight options, an 80-yard starting setting,
  the existing per-arm numerical table, and a gray/blue flight-curve preview.
  Read-back and adding another patch to an already-flat source work. Its
  numerical preview now also uses the actual relocated high-arc table when
  that existing mode is selected. Its obsolete acceleration tooltip is fixed.
- `nfl2k5_gameplay_lever.py` shares strict preflight, immutable allocation,
  section repinning and exact receipt logic. The allocator appends these two
  owners after all beta-61 owners without moving their reservations or adding
  any page. The manifest generator observes the new owners and alternative
  flat-flight table; the protected generated JSON remains untouched.
- New standalone tests, extensions of existing penalty/Throw tests, both
  complete executable gates, four schema-valid capability handoff objects,
  and a full appended `WIRING.md` integration specification.

The protected dispatcher, BuildPlan, Gameplay/Build panels, release allowlist,
runtime checker and manifest JSON were not edited. Their exact wiring is
delivered for Claude as required. Therefore this branch implements the new
backends and the owned Throw workspace; it does **not** claim the protected
Gameplay/Build switches or a release package are already integrated.

## Research decisions and corrections

Inputs were the supplied retail `default.xbe`, RC85 changelog, earlier
`ASTRA_*_REPORT.md` constraints, the hub coverage/interception memo, throw
distance solved memo, penalties study and later Momentum research. The
Ghidra corpus/index was read only. USA retail SHA-256:

```text
73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9
```

**PROVED:** The coverage memo's second consumer at `0x2E91F0` does not subtract
Human Coverage from CPU Coverage. Instructions at `0x2E9356` and `0x2E9366`
load indices **3 and 6**: offensive Receiving and defensive Coverage. The
result enters a clamped randomized branch, with difficulty/context terms.
Calling this simply a coverage delay/cushion slider would misdescribe it.
That routine and its shared constants are unchanged by this patch.

**PROVED:** Beta 61's later Momentum study corrects the older coverage memo's
claim that retail has no acceleration. The native command increment depends
on a curve, weight and effective Agility. The old optional Speed-rating
envelope is a separate layer and treats valid CPU marker -1 differently.
The new slow-QB experiment selects the existing native curve, applies equally
to human/CPU carriers, and does not modify that legacy owner or Momentum.

**Decision:** Use small bounded profiles rather than invent unproved
calibration sliders: expanded Coverage contribution; raw QB Speed <=60 and
65% acceleration increment; 25 yd/s deep lob speed. These values are an
unwitnessed first experiment, not NFL calibration or a promised exploit fix.
All new switches are off in every preset in the handoff. Existing Advanced/
Experimental penalty profiles still include their previously shipped repair.

## Coverage: exact mapping

**PROVED:** `0x17B8F0` selects the side table at `0xAAB8C0 + 40*(side!=0)`.
Index 6 is the runtime Coverage entry. `0x1F4250` uses that side's Coverage,
two context curves, and the native RNG comparison. The original contribution
is `(C + .25) * .15`; the new nominal contribution is `C * .225`.

| Coverage setting | Retail contribution | Patch contribution |
| --- | ---: | ---: |
| 0 | 0.0375 | 0 |
| 50 | 0.1125 | 0.1125 |
| 100 | 0.1875 | 0.225 |

The actual new slope is float32 **0.22500000894069672**, bytes `6766663e`,
chosen so the contribution at 50 matches the retail float32 store exactly.
The offset is zero, `00000000`. The two unchanged context records at
`0x50B32C` and `0x50B358`, the complete reaction helper and side accessor,
the shared constants and interpolator are hash-pinned before mutation.

For the full beta-61-plus-r62 request union:

| Instruction VA / file offset | Retail instruction bytes | Patch bytes |
| --- | --- | --- |
| `0x1F4282` / `0x1E4282` | `d8056c694e00` | `d805a0994d01` |
| `0x1F432C` / `0x1E432C` | `d80dd8884e00` | `d80da4994d01` |

The first points to `0x014D99A0`, the second to `0x014D99A4`; the 16-byte
allocation is `000000006766663e` followed by eight INT3 bytes. These VAs are
derived from the complete request union, never hardcoded in the patch.
Shared `0x4E696C=.25` and `0x4E88D8=.15` retain their retail bytes.

**PROVED, bounded:** Native reaction math, actual side lookup and both native
context interpolations give the expected three thresholds for both sides.
The angle/facing helpers and random sample are explicit synthetic boundaries.
At zero, context can still cause a reaction. At 100, only the Coverage
contribution doubles relative to neutral; total reaction or interception odds
do not double. The separate catch/interception owner is unaffected.

**HYPOTHESIS:** This wider range changes how soon defenders break on the ball
in a useful way. Man/zone geometry, reaction availability, difficulty and
other context can dominate the effect. No interception rate is predicted.

## Slow QB: bounded native acceleration

**PROVED:** The sole interpolation call in the native acceleration helper
`0x1DF190`, at `0x1DF1A5`, is repointed. In the full union, retail bytes
`e83619fdff` become `e806a82f01`, calling the selector at `0x014D99B0`.
The selector uses the original table unless all of these conditions hold:

1. Live phase at `0xE602B8` is 14.
2. The ball object at `0xE5FC00` has attached-player kind 1 and its holder
   equals EDI, the current native-helper player.
3. Roster position byte `[player+0x3C]+0x35` is QB, code 0.
4. Raw Speed byte at roster `+0x36` is **60 or lower**, inclusive.

The raw rating deliberately avoids reclassifying a fast QB merely because
the old optional envelope lowered his cached Speed. Controller index is not
part of the predicate. The existing descriptor/holder pattern, complete
native helper, interpolation routine and native factors are pinned.

| Prior native movement command | Retail curve | Patch curve |
| --- | ---: | ---: |
| 0.50 | 1.0 | 0.65 |
| 0.80 | 0.75 | 0.4875 |
| 0.90 | 0.50 | 0.325 |
| 0.95 | 0.05 | 0.0325 |
| 1.00 | 0 | 0 |

The original count/table at `0x50A5B4` remains byte-identical. The private
44-byte count/pairs record starts at allocation `+112`, `0x014D9A20` in
the full union. Its exact bytes are:

```text
050000000000003f6666263fcdcc4c3f9a99f93e6666663f6666a63e3333733fb81e053d0000803f00000000
```

The native caller still multiplies by `(1.3 - .002*weight_lb)` and
`(.02 + .025*effective_agility*state_multiplier)`. The selector preserves
flags/EAX around its own decision and tail-calls the original interpolator
exactly once, retaining its return-address and ret-4 convention. It performs
no floating-point work or persistent-state writes. The native interpolator's
volatile EAX table-iterator pointer naturally relocates on interior knots;
the float result remains in ST0. Nonvolatile registers, stack cleanup, native
flags and x87 control/depth are checked.

**PROVED, bounded:** Native-helper fixtures cover interpolation/end clamps,
the 60/61 boundary, all other roster positions, dead/loose/differently held
balls, null/sentinel ball pointers, weights, Agility and valid human/CPU
steering. Only eligible increments become 65% of baseline.

**Limits:** This is not a CPU bailout-decision threshold. It also reaches
eligible designed QB runs after possession, not just pocket escapes. The
retail first-step command floor, potentially 0.7, stays intact. Top speed,
ratings, animation resources and the rest of the native motion pipeline stay
intact. “65% increment” does not mean 65% physical speed or a guaranteed time
to escape. The old acceleration option can still compound this effect if
explicitly selected; compare without it first.

## Flatter deep flight

**PROVED:** The existing five-point lob-speed table at `0x50BCB8` keeps its
count, every distance coordinate, and its first four speed values. Only the
40-yard ordinate at `0x50BCE0` changes, **20 -> 25 yd/s**:
native float bytes `9a99e444 -> 00e00e45` (1828.8 -> 2286 cm/s).
The native interpolator clamps beyond the final point. All throws through
35 yards retain exactly their original speeds; 35..40 interpolate smoothly
to the higher final value. Bullet speeds and both arm-distance curves remain
independent. Both complete reader instructions are pinned; a relocated reader
or foreign/mixed speed table refuses before any copy is published.

At the existing 80-yard distance scale:

| Speed profile | Reach at effective arm 1 | Flight time | Equal-height apex |
| --- | ---: | ---: | ---: |
| Retail deep speed | 80 yd | 4.00 s | 21.4 yd |
| New flatter speed | 80 yd | 3.20 s | 13.7 yd |

Preview uses the existing game gravity constant and the same ballistic model
as the workspace numerical table: `T=distance/speed`, apex `g*T*T/8`.
The chart renders `g*T*T*u*(1-u)/2` for horizontal fraction `u`. It labels
equal-height assumptions and distinguishes retail-speed gray from selected
blue. This is a mathematical guide, not a captured gameplay trajectory.

**PROVED:** The original 80-yard distance edit and the flat-flight data edit
commute. Idempotent apply preserves chosen reach. The workspace selects 80
when starting from its retail 55 default and keeps other chosen ceilings.
Conflicting flight settings refuse in the API and are normalized exclusively
in the panel. Existing-source read-back does not claim a fresh change.
The copy adapter verifies its private output before replacing a destination,
closes every handle, cleans failed stages and never writes its source.

**HYPOTHESIS:** The lower, quicker flight feels better without producing
unacceptable targeting/lead, interception or catch-timing effects. The old
80-yard endpoint has Noah's historical witness in the supplied memo; the
new speed profile has **no** played witness and does not inherit one.

## Chop Block: ignored setting, existing detector

**PROVED:** Retail switch entries `0xB1594` (Clipping) and `0xB1598` (Chop)
both contain `ee140b00`, pointing to `0xB14EE`, which reads the Clipping
slider at `0xE600AC`. The UI's Chop toggle at `0xE60064` does not control that
enable result. The deterministic detector `0xB2900` exists; “dead toggle”
does not mean the penalty itself is absent.

The repair already existed in `nfl2k5_penalties.py` before this job. Its
independent `apply_chop_block` reuses the same reserved 16-byte host at
`0xB4A60` and redirects just the Chop case entry to `604a0b00`. The stub is
`a16400e600e9eecaffff` followed by six INT3 bytes: read the Chop toggle, then
jump to the existing enable store. No second cave or new detector is shipped.
The complete enable pass/jump table and complete detector are hash-pinned;
mixed entry/stub states refuse. The independent repair changes no rates,
yardage, default setting or saved profile. The bundled repair and standalone
repair produce identical bytes in either installation order.

| Chop setting | Clipping | Retail Chop enabled | Patched Chop enabled |
| --- | ---: | --- | --- |
| Off | 0 | No | No |
| Off | 50 | Yes | No |
| On | 0 | No | Yes |
| On | 50 | Yes | Yes |

**PROVED, bounded:** The native enable pass reproduces every row. The other
25 records retain their original decisions. Modes 0..3 still disable all
penalties. **UNWITNESSED:** actual flagged contact and enforcement frequency.

## Validation and receipts

Every command is a standalone unittest invocation, not pytest. No entire
disc image/archive was loaded into RAM. Native fixtures map about 22 MiB;
the largest new synthetic disc fixture is a capped 64 MiB logical file,
and an assertion verifies only its embedded XBE extent is read.

| Exact command | Result |
| --- | --- |
| `python3 tests/mod_editor/test_nfl2k5_gameplay_levers.py` | 12 passed |
| `python3 tests/mod_editor/test_nfl2k5_gameplay_levers_unicorn.py` | 7 passed |
| `python3 tests/mod_editor/test_nfl2k5_throw_arc.py` | 10 passed |
| `python3 tests/mod_editor/test_nfl2k5_penalties.py` | 18 passed |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_throw_tuning_panel_qt.py` | 13 passed |
| `python3 tests/mod_editor/test_nfl2k5_throw_tuning.py` | 45 run, 44 passed, 1 existing test skipped because its private patched disc image is absent |
| `python3 tests/mod_editor/test_nfl2k5_xbe_space.py` | 13 passed |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 24 passed, complete union in both orders |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 28 passed, complete union in both orders |

Additional checks: four capability handoff entries validate against
`registry.schema.json`; `.scratch/runtime_smoke.py` imports from an isolated
copy of the current allowlist plus the four proposed modules under `python3
-I`, constructs the offscreen panel and checks the 80-yard/13.7-yard preview;
module compilation and `git diff --check` pass. This is a staged import smoke,
not the protected release runtime gate or a packaged application build.

The first complete cave run found that simply sorting new owner names would
move existing beta-61 reservations. The fixed allocation ordering and a
regression test preserve every old owner address. No oracle relaxation or
protected manifest edit was used. A native test initially compared the
interpolator's relocated volatile EAX iterator with its old absolute pointer;
the final test checks the exact relocation while preserving the real ABI
requirements. Both were diagnosed, not suppressed as evidence skips.

Local receipts: `.scratch/gameplay-levers-receipts.json` and
`.scratch/gameplay-levers.xbe`, generated by `.scratch/receipts.py`. This
sample installs only the four lever changes plus the 80-yard distance curve,
reserving the full beta-61-plus-r62 owner union; other reserved owners are
intentionally dormant in this **separate receipt sample**. Its SHA-256 is
`fb0a3b5b8af7b300d99c666acd8d55c28582390bc6dc9a0726d96ad81a86688d`,
size 12,099,584. The safety gates separately install **all** existing owners.
Full-union requested RX bytes are 6,677, including the new 176; requested RW
bytes stay 3,242. These totals exclude alignment/padding. No allocator page
count or music/archive storage policy changed.

In that receipt sample, the standalone Chop edit changes 38 bytes including
the .text digest; flight changes 24 including .rdata digest; Coverage changes
300 including allocator seal/digests; scramble changes 403 including seals/
digests. Exact site before/after bytes and allocation receipts explain these
counts; they are not just instruction-size totals. Proprietary payloads and
scratch receipts are not committed.

## Noah's required witnesses

None of the following has been completed. Use disposable output copies from
one original source, record source/output hashes, roster, settings, difficulty,
teams, plays, relevant receipt, and video/tallies. Change one lever at a time
first; then compare the combined stack. Claude's protected wiring and manifest
regeneration precede these playable build trials.

1. **Coverage:** In exhibition, compare retail and patched response at 0,
   50 and 100 with identical interception/catching settings. Use man, Cover 2
   and Cover 3 against outs, curls, crosses and go routes. Repeat both Human
   and CPU sides, swap teams, and compare the same defender facing toward and
   away from the ball. Record first break/reaction frame and completions/picks
   separately over repeated snaps. Verify 50 feels neutral, 0 still permits
   context-driven reactions, 100 does not make every ball a pick, and the
   other side's setting does not silently control this defender. Repeat on
   Pro, All-Pro and Legend, after a saved settings reload and in replay.
2. **Slow QB:** First disable the old acceleration envelope and Momentum.
   Compare two otherwise matched QBs at raw Speed 60 and 61, then a real
   low-Speed pocket passer and a fast passer such as Vick. Test human and
   CPU control, left/right/straight pocket escapes, designed QB runs and a
   pressured throw before escape. Record first steps and distance over
   repeated frames; do not assume the unchanged first-step floor disappeared.
   Run to full speed to confirm its ceiling, then throw, hand off, fumble,
   change possession and enter dead ball. Check RB/WR/defender motion stays
   normal and run animations do not slide. Repeat after substitutions, next
   snap and roster reload. Finally compare with Momentum and, separately,
   the legacy envelope; document any compounded slowing or asymmetry. CPU
   bailout frequency is an observation, not a promised change.
3. **Flatter flight:** Use the witnessed 80-yard-cap route with an effective
   elite arm and compare only the speed option. Verify the actual landing
   still reaches 80 air yards, the apex/hang decrease, and receivers can
   track/catch it. Compare 10, 20, 30 and 35 yards for short-game preservation,
   then 36, 40, 55, 65 and 80 yards for the transition. Test lob/full hold,
   CPU throws, on-the-run throws, different arm strengths, both directions,
   different release/catch heights, accuracy, replay and interceptions. In
   Studio, verify preview selection, flat-source reopening, reset from an
   original source, conflicting flight-mode exclusion and copied output.
4. **Chop Block:** Use exhibition/CPU-vs-CPU games, not practice, to compare
   all four setting combinations in the matrix. Record both Chop and
   Clipping calls independently; repeat low/double-block contact opportunities
   and check referee announcement, yardage and acceptance/decline behavior.
   Toggle within a game and after saving/reloading the profile. Confirm
   practice still disables penalties. Compare standalone repair with the
   existing adjusted-rate profile to distinguish enable behavior from flag
   frequency. No calls in a short sample do not prove the detector is dead.

## Remaining limits and delivery

All gameplay feel, native loader execution of the new grown allocations,
full animation interactions and actual penalty calls remain unwitnessed.
No console boot, full playable-disc build with the protected new controls,
fresh generated reservation JSON, native Windows/macOS run, or release
package is claimed. Complete owner byte composition and the existing loader
architecture do not substitute for Noah's observations. Settings/profile
calibration and any future preset promotion follow those witnesses.

The explicit-path Git staging check succeeded in this worktree. Deliverable
paths are committed on the supplied branch; no bundle fallback is needed.
`ASTRA_BRIEF.md` and `.scratch/` are excluded. No push is performed.
