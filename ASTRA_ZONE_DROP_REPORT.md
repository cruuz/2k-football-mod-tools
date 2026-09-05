# Initial corner deep-zone drop cap

**EXPERIMENTAL / UNWITNESSED. All presets remain off.**

Built the scoped initial-drop experiment in
`mod_editor/core/nfl2k5_zone_drop.py`, with standalone integrity and bounded
Unicorn tests. The implementation replaces the five-byte call at `0x001A65D1`
with a call to a **78-byte wrapper in an 80-byte named RX allocation**. It has
no persistent writable state. The backend is ready for explicit isolated
witness builds; protected UI/build integration and the complete all-owner
combination are not finished by this branch. `WIRING.md` gives the concrete
handoff, including the allocator prerequisite discovered below.

Read the full hub memo `CB_DEEP_ZONE_RESEARCH_2026-09-05.md`, including its
saved candidate, ABI caveat, facing/interception separation and witness list.
No game boot, console emulator, GUI, audio or network was used. Unicorn runs
synthetic instruction fixtures only. No source game image was modified and
no played observation is claimed.

## Implementation and decisions

- Exact byte `[P+0x2C] == 18`; no masked-position shortcut. Require
  `(zone_mode & 0x0C) == 8`, using the record selected by `A+0xA4`. Modes
  12..15, including fallback 15, are excluded despite sharing bit 8.
- Forward the original signed-depth argument to native `0x001B0AE0` exactly
  once. Return the smaller of its float32 result and the configured depth
  cap for eligible actors. Default is float32 **0.84** (`0x3F570A3D`).
- Decide the configuration range as **0.50..0.84**, inclusive. The memo only
  specifies 0.84; this range preserves the same experiment. Higher values
  would trigger retail's promotion to at least 0.91. Lower values cannot
  beat the final 0.50 floor. Lateral interpolation is unchanged and can still
  raise a lower configured depth cap to 0.84. This is a depth-term setting,
  not a promise of a lower final throttle in every lateral fixture.
- Preserve the native leaf's returned GPRs and EFLAGS. Compared with the
  memo's candidate, add `PUSHFD/POPFD` and a stack-local 28-byte
  `FNSTENV/FLDENV` save/restore. The entire body still fits 78 bytes, followed
  by two owned `INT3` padding bytes. ECX/EDX keep the native leaf's behavior.
  The original and copied arguments each receive their own `ret 4` cleanup.
- Only the returned x87 value can change. The caller immediately stores it
  as float32; the wrapper uses that same precision. Deeper live x87 values,
  TOP, tags, control and status are retained. The save area and temporary
  float occupy 32 stack bytes, released before return. No SSE/MMX or MXCSR
  instructions are added. See the FIP/FDP proof limit below.
- The patch does not change the zone record, shared thresholds, curves,
  animation tables, receiver pickup, callbacks, later steering, fast-latch
  helper, ball-response routines or interception-slider catch hook. Pins
  cover both sides of the initializer call, the full curve leaf, both curve
  tables and the decisive scalar thresholds. Section-aware address mapping
  is used for all reads; `.rdata` is not assumed to share `.text`'s raw delta.
- `status` recognizes retail, an empty preallocated owner, or an exact
  installed body/hook/configuration. Mixed hooks, filled body with retail
  hook, altered body or padding, changed prerequisites, wrong allocation
  shape, stale digests and malformed extents refuse before mutation.
  `apply` is idempotent; requesting different settings on an installed image
  refuses. Receipts retain cap, witness flags, exact edit spans, hashes,
  changed-byte count, allocation reservations and zero persistent-data size.

When retail would request 1.0, the default patch leaves `A+0xAC=1` and the
initializer's earlier default `A+0x60=0.9`; retail instead sets `A+0xAC=0` and
computes `A+0x60=distance/maximum_speed`. These are intended changes in this
experiment, not evidence that `A+0x60` is a universal snap timer.

## PROVED: bounded execution and ownership

The new Unicorn suite executes **564 retail/patched initializer slices**,
**80 isolated wrapper ABI cases**, **120 native ordinary-bank selections**,
and **120 fresh animation selections**. Every invocation has a 1000-instruction
limit and an asserted stop address. All reached callees use actual retail
instructions; none is replaced by a Python result or a stub. Synthetic actor
and game-state memory supplies the explicit fixture inputs.

- At 3 and 5 yards, in both field directions and with 0/4/9 yards lateral
  travel, retail requests 1.0 and the patch requests 0.84. Native phase-14
  group `0x00511178`, bank `0x00511070`, selects mode 4 for the capped values
  versus mode 3 for retail. Backward, both sideways, forward and wrap-angle
  fixtures select the expected native descriptor rows. This proves selection,
  not rendered appearance or head direction.
- Off corners at 7, 10, 15 and 20 yards preserve retail actor memory across
  lateral fixtures. FS/SS identities 16/17, other exact position bytes
  including 50/82/114/255, nondeep modes 0..7 and excluded modes 12..15 also
  preserve retail actor and zone memory. Nondeep fixtures never enter the
  new wrapper. Ordinary modes 8..11, the 5.5/6/just-below-7 boundaries and
  speed inputs 0.5/1 exercise the intended scope and `A+0x60/+0xAC` changes.
- Zone records remain byte-identical. Runtime writes outside the stack in
  eligible initializer fixtures are only native stores to `A+0`, `A+0x34`
  and `A+0xAC`. The wrapper itself writes only its stack frame.
- ABI fixtures preserve leaf GPRs, EFLAGS, x87 control/status/tags/TOP,
  deeper physical x87 registers, XMM registers and MXCSR under all four x87
  rounding modes. Exactly one native interpolator call runs and the final
  stack pointer matches the displaced call's cleanup.
- Exact install/replay/settings, malformed and correctly resealed foreign
  inputs, all prerequisite pins, both relocated calls, padding and complete
  instruction decoding are covered. All final section digests verify.
- With the full pair request set reserved first, zone drop plus relocated
  kickoff and zone drop plus runtime scorebug each produce byte-identical
  images in either installation order, with stable allocations and unchanged
  recognized settings. These are XBE-hook proofs; runtime scorebug resource
  transport and gameplay remain separate.
- The recorder test reserves the complete five-byte hook and 80-byte owner,
  including padding. Existing cave reservations do not collide with the call.
  The allocator's byte-granular retail-reference proof reports no encoded
  references into its owned pages. The new body lives in nonwritable RX code.
  Both composed gates enumerate this owner in an additional compatible stack
  while retaining their previous kickoff/runtime stack.

## Limits and required integration

**Allocator mismatch, PROVED.** This checkout has the original sealed,
one-page allocator, not the append-stable allocator described in the brief.
The automatically included boot logo (690 bytes), relocated kickoff (1939),
runtime scorebug (1408), and alignment occupy 4064 of 4096 code bytes. Adding
the 80-byte wrapper requires **4144 bytes**, exceeding capacity by **48 bytes**.
The full union therefore refuses safely. Applying to a grown image that did
not reserve this owner also refuses; installed addresses are never moved.
The defensive-try and momentum modules are absent, so no composition with
their actual code was possible. Their integration and extra allocator
capacity belong in the shared-owner handoff, not an invented retail cave.
No complete all-owner stack success is claimed.

**x87 model boundary, PROVED observation / limited restoration proof.** In
installed Unicorn 2.1.4, `FNSTENV` saves the correct FIP/FDP and `FLDENV`
restores the tested control/status/tag fields, but FIP/FDP still report the
wrapper's temporary `FLD` afterward. The suite verifies the saved pointer
values and emitted save/restore sequence; it does not claim Unicorn proved
restoration of those two pointers. Their restoration is the intended x86
instruction contract and remains outside this execution-model proof. The
ordinary continuation establishes new floating comparisons before using
their status. No claim is made about arbitrary pending unmasked x87 faults.

**Precision boundary.** Seven yards means the actual signed float depth
computed by the game, not a label rounded to yards. Fixtures use a zero field
reference to represent the exact retail seven-yard knot in both directions.
A development fixture at a nonzero reference exposed subtraction rounding
just below seven yards, where retail requests 0.91 and the patch appropriately
caps it. Record actual coordinates and signed depth in the witness.

**HYPOTHESIS / UNWITNESSED.** The changed selection may look like the requested
backpedal or strafe and may help recognition of curls/comebacks. It also slows
depth gain and may worsen vertical coverage. Later callbacks may request
running again; existing run-state hysteresis and next-snap latch cleanup have
not been proved end to end. This is not a sustained QB-facing policy,
modern match coverage, a guaranteed interception improvement, or a proved
fix for THE1WAM's exploit. No complete initializer-to-renderer/full-play trace
or grown-section kernel-loader witness was obtained.

Protected product files and the protected reservation JSON were not edited.
The staged capability row is `docs/mod_editor/nfl2k5_zone_drop_capability.json`.
`WIRING.md` specifies the BuildPlan field, **False in all presets**, dispatcher
tuple/keyword, all four status dictionaries, settings/receipt propagation,
exact Retail/Patch text plus NEEDS_IMAGE, the 41-character Build caption,
allowlist, runtime imports, registry entry and manifest regeneration. Only
Noah's explicit witness build opts in; Experimental-preset promotion must wait.

## Noah's witness list from memo section 5

Every row remains **UNWITNESSED**. Hold roster, difficulty, sliders, route,
field position and offensive timing constant. Compare retail, data-only off
alignment and scoped-cap builds separately, in both field directions and
on both hashes. Measure actual starting depth rather than Start operands.

| Case | Record and acceptance question |
| --- | --- |
| Cover 3 press versus off CB, go route | Actual depths 1, 5, 6, just below 7, 7 and 10 yards. First turn frame, effective facing, separation and time to depth. Reject better-looking drops that concede materially worse vertical separation. |
| Same Cover 3 pairs, curl | Throw before and after the break. Separate first recognition/break frame from arrival and catch outcome. Check whether facing survives receiver pickup. |
| Same Cover 3 pairs, comeback | Outside/inside leverage on both hashes. Check stopping and downhill drive versus drifting or sliding. |
| SEA retail Cover 3, ATL 3 Weak, modern SD Three Deep | Confirm the six/seven-yard boundary against actual alignment and selected mode; check wider authored landmarks and lateral travel. |
| Cover 2 Hard/Soft/Man safeties and flat CB controls | Safety initialization and flat CBs must retain retail behavior. Include a forced shallow safety start to expose its unchanged depth rule. |
| Retail four-deep calls and modern SD Four Deep Spot | Outside go/seam routes, all four defenders, capped CBs and unchanged safeties. Do not call this match quarters. |
| Retail man-to-zone combination | Transition frame into opcode 0x0D, inherited facing/run latch and a receiver already beyond the CB. No slow chase after a late transition. |
| Release and exceptions | Pass, pump fake, play action, handoff, rollout/scramble, receiver crossing the CB, turnover and user takeover. Pursuit and pass response must remain available. |
| Lifecycle and composition | Audible, mirror/flip, press/back-off adjustment, substitution, next snap, hurry-up, CPU/human defense and low/high Speed. Repeat with relocated kickoff, catch cave and persistent depth locks; after allocator integration, include the actual scorebug/defensive-try/momentum combination. No stale latch, broken animation, crash or collision. |

Begin with ten matched repetitions per primary route/alignment/build/direction
cell and retain raw counts. This is a diagnostic screen, not statistical
proof of an interception-rate improvement. Expand paired samples if results
differ. Repeat useful cases with the catch patch off/on while holding
Interception constant.

Retain video and build/input hashes alongside actor/position/slot, actual x/z
and signed depth, zone mode/landmark, callback, `A+0x34/+0x60/+0xAC`,
`S+0x584` bit `0x40000`, `C+0x10/+0x14`, bank/row/clip at `M+0x14/+0x1C`,
`M+0x28` bit 2, targets `A+0x40/+0x48`, effective facing, ball release, route
break and first defensive break. Reject promotion on delayed release,
unacceptable go-route losses or stale run state.

## Validation and reproducible input/output identity

Retail: **11,948,032 bytes**, SHA-256
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
Read from the user-owned extracted USA `default.xbe`. All proof outputs remain
in memory or uncommitted `.scratch`; no executables or game bytes ship here.
Each recognized grown output is 12,029,952 bytes (81,920 bytes beyond retail,
including preceding storage growth and both allocator pages).

| In-memory XBE from pinned retail | SHA-256 |
| --- | --- |
| Default zone drop alone, wrapper VA 0x014BA2C0 | `cfbea099440633a42f08b96f63a8191297c91fb7f7d9b83099b9d3f07ac12946` |
| Relocated kickoff + default zone drop, wrapper VA 0x014BAA60 | `84c94c5e9332dd077fea5634699f7be070503ae08ac7a37f32f1f662cb8347a6` |
| Runtime scorebug hooks + default zone drop, wrapper VA 0x014BA840 | `16833b921fb914249a417c17ab28914e4739ede349135f0379d44209ea312ae4` |

The default standalone 80-byte wrapper SHA-256 is
`7ec068e14635f5c667b0149f69ef1a9108da1c7f40e5b6a58b99c5567c148cc5`.
Reassembling at another owned address changes its relative call as required.

Commands run with plain Python 3.12, Capstone 5.0.7, Unicorn 2.1.4:

| Command | Result |
| --- | --- |
| `python3 tests/mod_editor/test_nfl2k5_zone_drop.py` | PASS, 9 tests, including owner recorder/manifest and both pairwise orders |
| `python3 tests/mod_editor/test_nfl2k5_zone_drop_unicorn.py` | PASS, 5 tests containing the bounded matrices above |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | PASS, 12 tests |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | PASS, 13 tests |
| `python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` | 27 pass, 1 ERROR: pre-existing stale protected manifest fingerprint |

Evidence files and optional dependencies get precise standalone unittest
skips when absent on another host. They were present for every feature and
composed-gate test reported above; no test in those four commands was skipped.
Development failures were corrected: malformed short XBE errors now normalize
to ValueError; fixture depth subtraction is explicit; repeated Unicorn slices
also stop in the instruction hook to handle a cached longer block; FIP/FDP
are reported at their actual proof boundary. No test failure was waived as a
played success.

The full cave-oracle suite refuses the supplied protected manifest at
`mod_editor/core/nfl2k5_formation_play_writer.py`. Its current SHA-256 is
`bb9163808fb5c8418e23346f9faa22a8d78871bf8bd1f6125bacacdc7451e033`,
but the manifest expects
`e0712331cc2ec8d64c11d490df3366aa3fa68e828500f0d7103ed3a48d237665`.
The file is byte-identical to this branch's starting HEAD; this is not a
zone-drop source change. The protected manifest was not rewritten and the
source-drift check was not weakened. The new owner-recorder test and both
composed gates pass independently. Claude must regenerate the full manifest
as directed in WIRING.md.

Additional handoff checks:

- `python3 -m py_compile` on the backend, both feature tests and both modified
  gate files: PASS.
- Runtime import and 80-byte assembly with Capstone and Unicorn imports
  deliberately blocked: PASS. The full application's existing Pillow import
  remains necessary; an exploratory `python3 -S` import cannot omit it.
- The staged row combined with the current registry, sorted by ID, passes
  `python3 mod_editor/capabilities/validate_registry.py --registry
  .scratch/zone-registry.json --skip-file-checks`. The row's own evidence
  paths, backend command/module and validation command were then checked with
  the same validator helpers: PASS. Global file checking is independently
  blocked by the pre-existing missing `docs/research/apf_audio.md`; no registry
  entry or validator was weakened to conceal that missing unrelated file.
- The requested plain UI text is present in the backend and handoff; the
  Build caption is 41 characters. All preset instructions explicitly say
  False. `git diff --check`: PASS.
- With `NFL2K5_RETAIL_EXTRACTION=/nonexistent-zone-proof`, the standalone
  integrity suite passes its 2 public tests and skips 7 evidence tests; the
  native suite skips all 5 with its missing-evidence/dependency reason. This
  separately verifies the intended portable CI fallback, not the retail proof.

Starting branch: `astra/r61b-cb-deep-zone-build`, HEAD
`2ccb926bc1071cd3d235e7f2f00d7960bb437b68`. The working brief describes an
earlier stack base; this is the actual checkout used for all results above.
Only this worktree was edited. The brief and `.scratch` are excluded from
delivery, except that the prescribed fallback bundle may reside in `.scratch`.
No push is authorized or performed.
