# Momentum model 1 build report

**EXPERIMENTAL / UNWITNESSED.** Branch `astra/r61b-momentum-build`, starting
commit `4eda2d6`. This implements the brief's one-level Momentum experiment,
with a separate contact flag. No gameplay, loader or animation-asset witness
is claimed. No push, network, console emulator, GUI, display or audio was used.
Unicorn ran bounded isolated instruction fixtures, as requested.

## Delivered

- `mod_editor/core/nfl2k5_momentum.py`: pinned pure-byte `status`,
  `read_settings`, idempotent `apply`, exact receipts and named reservations.
  A small command-line entry point inspects an XBE or writes a new copy without
  overwriting an existing file.
- `mod_editor/core/nfl2k5_momentum_code.py`: deterministic relocated instruction
  template. Its annotated source is `tools/nfl2k5_momentum.S`; the standard-library
  ELF32 generator is `tools/nfl2k5_momentum_assemble.py`. GNU as is a development
  dependency only; patching does not invoke it.
- `nfl2k5_accel_ramp.py`: docstring correction only. Code, constants, guards,
  thresholds, status and legacy second-apply refusal are unchanged.
- Standalone Momentum tests, both composed XBE safety gates, and the manifest
  builder now include the actual owner. The allocator's allocation-evidence
  default includes the same dormant-owner union as the manifest builder; its
  allocation policy, sections, capacity and runtime behavior are unchanged.
- `WIRING.md` contains the protected BuildPlan, dispatcher, four dictionaries,
  presets, Gameplay/Build controls, closure, allowlist and capability handoff.
  The complete capability row is `docs/mod_editor/nfl2k5_momentum_capability.json`.

Every preset remains Retail/off in the handoff. Product integration is deliberately
left in WIRING.md because those files are protected by the brief. No protected
product file or `data/nfl2k5_cave_reservations.json` was edited.

## Decisions and exact calibration

The supplied hub memo `MOMENTUM_RESEARCH_2026-09-05.md` was read in full. Its
retail observations were checked against the pinned USA image, SHA-256
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
The read-only Ghidra corpus was used to trace the simulation clock and motion
consumers. No other checkout was modified.

### Turning: the smallest effective table experiment

**PROVED:** The 44-byte turn record at `0x50A588` is in `.rdata`. Byte-granular
address scans find just the ordinary turn helper's encoded count/table readers
at `0x237CCC` and `0x237CDA`. The floor's encoded reader is `0x237D11`.
Retail also embeds the floor as an immediate in the complete eight-byte
instruction at `0x237D20`; changing the data constant alone would not change
that selected value. All complete records/instructions are pinned.

Let `m = level/100`. Keep the count and abscissas fixed and the first two
ordinates unchanged. Multiply the ordinates at q=.7/.9/1 by
`1-.15*m`, `1-.35*m`, `1-.50*m`, respectively. Set both floor copies to
`19114*(1-.40*m)`. Only the four immediate bytes of the inline instruction
change. No turning trampoline or extra heading write is needed.

This is the memo's Tier A lever, chosen because the brief explicitly prefers
an existing data curve. It is not the larger Tier B speed-estimate formula.
The Agility calculation, turn history, reversal zero, shortest-angle wrapping,
orientation synchronization and fixed-role exceptions remain retail. At full
command and level 100 the bounded helper returns 11,468.4 instead of 19,114.
Jogging points remain unchanged; intermediate interpolation is intentionally
changed. Like retail, this curve is command-dependent, not a physical-speed
measurement or a new Speedster-aware calculation.

**HYPOTHESIS:** Fast cuts should be wider. This shared curve also reaches
ordinary-helper callers such as shoulder charge, which applies its own factor.
Strafing's separate heading path and move-specific motion are unchanged. This
is not a universal limit on every player animation or facing change.

### Braking: one input envelope around native locomotion

**PROVED:** Momentum owns the six bytes at `0x1CD5D7`, immediately after
kickoff's seven-byte dispatcher hook. The wrapper unwinds the displaced
ESI/EDI saves, runs its preparation, then replays the complete original
prologue through `0x1CD5DD`. Its internal call captures both the ordinary RET
and the RET reached through the tail jump into `0x2FCAC0`. Stack alignment at
the native continuation is unchanged modulo 16.

Eligible scope is live phase 14; player kind 1; current/requested command 0;
ordinary descriptor `0x50F4EC`; stable locomotion type 1; no locked or alternate
facing bits; finite q/throttle/Agility in 0..1; and `0 < dt <= .1`. Null/sentinel
steer/state/locomotion pointers bypass the added effect. The retail caller still
owns the validity of its entity graph; these are not arbitrary-memory validators.
No controller-index, team, position or possession test gates braking.

For eligible input, use `t_stop = m*(.4-.12*agility)` and
`filtered = max(raw_throttle, previous_q - dt/t_stop)`. Increases pass straight
to retail acceleration. The current q already reflects retail's earlier command
clamps/cut penalties; it is not the cached Speed rating. A same-tick invocation
reuses its existing envelope, allowing a newer increased request to pass through.
For exact neutral input retain the current locomotion heading inside the wrapper.

Both the native tick `0x213310 -> 0x1E0F90` and native animation-rate helper
`0x2382E0` see the substituted input. Restore only throttle/heading values that
still equal our substitution; preserve any values or action commands written by
retail during the call. Recheck eligibility after either return and invalidate
history after a transition. Added arithmetic saves/restores the complete x87
state during preparation; no SSE register is used by the new code.

**PROVED, bounded:** Native command and native animation rate remain positive
on release and decay to zero; human marker 0 and valid CPU marker -1 produce
identical added envelopes in the fixture. Relaunch uses retail's q=.7 initial
floor, with no new acceleration law. Native registers, nonvolatile registers,
x87 depth/control, SSE values, continuation alignment and returned flags are
checked. The flag check preserves flags produced by the wrapped native return;
retail ADD ESP parity can differ between different absolute stack addresses.

**PROVED, static interval trace:** `0x1E0280` writes raw throttle to `S+0x1BC`
after the dispatcher. The inspected corpus has no locomotion read of that
state offset. The following `0x2180D0 -> 0x218010` motion pass invokes the
animation machinery at `0x31BEB0`; its track-rate consumers and callback
`0x2CC570` use animation/root-motion data. The latter updates the transform
from the supplied root delta and player scale, without rereading throttle.
This supports retaining the dispatcher interval for the ordinary prototype.

**HYPOTHESIS / boundary:** Bounded tests use a tail fixture that calls the real
animation-rate helper; animation asset selection/decoding and full-frame world
motion are not executed. Static tracing is not an exhaustive alias/callback
proof. Actual stopping distance and foot sliding remain mandatory witnesses.
The AI's existing producer prefilter remains, so identical added envelopes do
not establish identical controller-to-motion latency across human and CPU.

### Runtime identity and contact

**PROVED:** `0xAF2C0` increments the dword at `0xB71D10` and publishes dt before
`0x11A7C0` invokes `0x1E08D0` and its active/auxiliary locomotion passes. The
increment instructions are pinned. Each history slot records entity, state,
roster, simulation tick, state age and eligibility. Changed identity, decreasing
state age, lost eligibility or a nonconsecutive tick resets run history.
A full 32-slot search prevents hash aliasing; exhaustion falls back to retail
and increments a counter. Stale slots may be reused. A catch or controller
switch preserves continuous valid ordinary-running history.

The allocation has a 16-byte header and 32 slots of 64 bytes, all initially
zero in the grown RW page. No runtime data lives in `.text` or the RX page.
Tests cover repeated calls, identity reuse, catch/controller changes, transition
invalidation, exhaustion and stale-slot reclamation. A universal maximum player
population and every save/load lifecycle remain unwitnessed.

**PROVED, bounded contact rule:** A slot counts at most 21 consecutive simulation
ticks with horizontal speed above `.55*v_ref`, where the fixed calibration is
`v_ref = 640.080017 + 274.320007*.99`, about 911.657. This is a 21-frame rule;
it is about .35 seconds at 60 Hz, not a guarantee under another tick rate.
Unlike the memo's more expensive proposed reference, this initial calibration
does not apply the retail player's conditional .975 factor.

At the first Break Tackle read `0x1D9D62`, call the original attribute accessor
with its unchanged modifier, then use current pre-resolution carrier velocity
projected toward the opponent. For `u = closing_carrier_speed / v_ref`, add
`0.08*m*clamp((u-.55)/.45,0,1)^2*(run_frames/21)`, capped together with the
retail rating at 1. Null possession, no valid run history, stale identity/tick,
stationary/retreating/perpendicular motion, zero separation and nonfinite inputs
add zero. The holder predicate matches the pinned `0x1CE280` retail attached
player lookup through `[0xE5FC00]`, with the eligible player-kind check.

Store the sampled bonus with carrier identity, frame, opponent and resolver
stack-frame identity. The later read at `0x1DA39F` reuses it. Both hooks retain
retail's ret-4 accessor convention; no roster, cached attribute, charge meter,
Tackle value or velocity is permanently changed. This strengthens an existing
contact system by adding a small Break Tackle rule, not by replacing velocity
or weight with a mass-times-velocity simulation.

The optional flag is off by default. The fixture executes the complete retail
`0x1D9C50` resolver with deterministic pose-heading, effective-attribute and RNG
boundaries. Eighteen cases across retail/patched images vary rating, carrier
velocity, weight, contact scalar and RNG. Both hook reads, RNG, and both resolver
return paths execute. The native weight/velocity mixture, sliders, charge
comparison and threshold curve remain in that execution. Separate tests prove
angle exclusions, standing/retreating cases, both-read coherence and the eight
point maximum.

**HYPOTHESIS / boundary:** This is not a complete tackle/reaction animation or
RNG-frequency study. Scalar inputs are fixture inputs, not a simulated complete
collision. No monotonic improvement in yards, wins or selected animations is
claimed. Charge, dive, spin/juke and tackle/fall states need Noah's witnesses.

## Ownership, composition and receipts

**PROVED:** 932 assembled bytes including configuration occupy an exact
944-byte RX allocation; history occupies 2,064 RW bytes. With logo and relocated
kickoff, Momentum starts at code `0x14BAA60`, data `0x14BB010`. These are computed
addresses for that request union, not hardcoded allocation claims. Remaining
capacity is 496 code and 2,016 data bytes. A further 512-byte abilities owner
would exceed the current code page; no unknown cave or extra page is borrowed.

Both orders with relocated kickoff produce identical bytes when all requests
are preallocated. Kickoff may hold a player before entering Momentum. Both
orders with the unchanged legacy acceleration ramp also match byte for byte.
The Speedster call at `0x75CC8` is untouched, as is the legacy store at `0x75CD5`.
No second cached-rating or launch envelope is installed. The new product
profile should disable the legacy ramp, as documented in WIRING.md.

**Unavailable integration:** The parallel defensive-try source is not in this
worktree. Its real composition test has a precise skip, not a stand-in owner
or an invented capacity claim. The handoff specifies the request union and
both-order test once that module is integrated. Full future abilities behavior
is likewise not claimed from a free hook site.

All owned code/configuration, hook/table bytes, allocation sizes and on-disk
zero state are checked; mixed/foreign bytes and changed settings refuse before
any returned mutation. Every section digest is repinned through existing helpers.
A repeated `apply` returns the original bytes object with zero changed bytes.
Level 0/off returns exact input bytes without allocating any page. This does not
undo independently installed patches; the product profile normalizes the old
acceleration choice before building from the supported source.

Fresh-retail receipts (counts include file growth and section/header changes):

| Level | Contact | Changed bytes | Result SHA-256 |
| --- | --- | ---: | --- |
| 0 | off | 0 | `73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9` |
| 25 | off | 82567 | `2ee32afb679a7ef4b1322f14f46813fdadd5fc57515daf695c4ea8dcbf522ca5` |
| 50 | off | 82567 | `b0c27431d898dc0fc051b189123434809a155dc072bb4ec6e8a405db30ece1dd` |
| 100 | off | 82566 | `26d50efed86d14ea6ebf8c4effa94bbdcc256072ab363d865d52b7b1f2d24f53` |
| 100 | on | 82573 | `d7038f6604fad17d48f4ca18ade9f227ad0bde2b5ebfeb599005300bc6fecfd6` |

The CLI defaults to read-only inspection:

```sh
python3 -m mod_editor.core.nfl2k5_momentum /path/to/default.xbe
python3 -m mod_editor.core.nfl2k5_momentum /path/to/default.xbe \
  --output /path/to/new-momentum.xbe --level 50
```

Its new-copy writer refuses an existing destination. A disc build still needs
the protected final-stage writer integration, not merely an extracted XBE copy.

## Verification

All commands below were run standalone with plain Python, no pytest. Logs and
proprietary generated images stay under `.scratch/momentum/` and are not committed.
Tests precisely skip absent retail/dependencies; this host has retail, Capstone
5.0.7 and Unicorn 2.1.4. The only Momentum skip is the absent defensive-try owner.

| Command | Result |
| --- | --- |
| `PYTHONDONTWRITEBYTECODE=1 python3 tests/mod_editor/test_nfl2k5_momentum.py -v` | 23 tests: 22 passed, 1 precise skip |
| `PYTHONDONTWRITEBYTECODE=1 python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 11 passed |
| `PYTHONDONTWRITEBYTECODE=1 python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 12 passed |
| `PYTHONDONTWRITEBYTECODE=1 python3 tests/mod_editor/test_nfl2k5_xbe_space.py` | 12 passed |
| `PYTHONDONTWRITEBYTECODE=1 python3 tests/mod_editor/test_nfl2k5_dynamic_kickoff.py` | 23 passed |
| `NFL2K5_CAVE_MANIFEST="$PWD/.scratch/momentum/cave_manifest.json" PYTHONDONTWRITEBYTECODE=1 python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` | 28 passed with the freshly generated private manifest |
| `python3 tools/nfl2k5_momentum_assemble.py --check` | Exact template reproduction |
| Capability row inserted in a sorted in-memory registry: `validate_data(..., check_files=False)` plus new-row file/command closure | Passed; protected registry unchanged |
| Allocation `space-proof` against the final private manifest | No encoded retail references or foreign-owner overlaps |
| Legacy acceleration AST comparison with HEAD, excluding only the docstring | Identical |
| `git diff --check` | Passed |

The full registry file check is blocked by an existing missing
`docs/research/apf_audio.md` reference in capability 0. The Momentum row
passes the registry schema and its own complete file/command closure checks.
Its registry validation command inspects a user-supplied `default.xbe`.

The full manifest was generated by the actual disposable disc build:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/nfl2k5_cave_oracle.py manifest \
  "$NFL2K5_RETAIL_XBE" \
  --xiso "$NFL2K5_RETAIL_XISO" \
  --work-dir /tmp --json .scratch/momentum/cave_manifest.json
```

The allocation proof command was:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/nfl2k5_cave_oracle.py space-proof \
  "$NFL2K5_RETAIL_XBE" \
  --manifest .scratch/momentum/cave_manifest.json \
  --json .scratch/momentum/allocation_proof.json
```

The manifest build observed 39 XBE writer calls and produced 3,346 reservations, including the
new owner and its zero-initialized writable capacity. The production manifest
was not regenerated in place. No source-fingerprint bypass was used.

## Noah's witness list

Nothing below is witnessed. Start with identical roster/sliders, legacy ramp
off, contact off, and compare Retail, Medium/50, then Heavy/100. Only then turn
contact on and repeat. Record settings, player identities, input direction,
video/frame timing if available, stopping distance and repeated contact results.

| Witness | Required comparison / failure signals |
| --- | --- |
| RB cuts | Full-speed run-up versus a jog; 45/90/180-degree cuts in both directions; high/low Agility, light/heavy backs. Look for wider fast turns without snaps or stationary penalties. |
| Stop-and-go | Full release, partial throttle, short/long neutral, relaunch and reversal. Check finite braking, no neutral auto-turn, no sliding or extra launch penalty. |
| Contact | Same carrier/defender/angle, full-speed versus standing carrier, stationary/running defender, approaching and chase cases. Repeat to separate randomness. Record yards, stumbles and tackle outcomes. |
| Receivers after catch | Catch in stride versus stationary reception, turn upfield, cut and stop. Include interception returns. A standing receiver must not inherit a bonus from another player. |
| Pursuit angles | CPU and human defenders in pursuit, contain, coverage, strafe/backpedal, and control switches. Watch overruns, oscillation, broken contain and skipped CPU effects. |
| Human/CPU parity | Same players and requests with legacy ramp off, both teams/controllers. Distinguish the shared new envelope from the retained native AI input smoother. |
| Special moves | Shoulder charge, spin, button/stick jukes, ordinary/charged/dive tackles. Confirm animation-driven moves and recovery remain plausible; the shared turn curve can affect ordinary-helper calls within moves. |
| Lifecycle/composition | New play, dead ball, substitutions, save/load, both-direction kickoff, injury/fatigue, 99/100/127 Speed targets after Speedster exists. Check stale history, loader failures and animation-rate mismatch. |

Known gaps are protected product integration, the absent defensive-try owner,
future abilities allocation, full animation/displacement and tackle-reaction
execution, all-state lifecycle coverage, and Noah's gameplay/loader witnesses.
They are not represented as completed or proved by this experimental build.

## Commit delivery

Normal explicit-path staging initially succeeded. Final staging then refused
`index.lock` with `Read-only file system` in the shared worktree metadata.
Following the brief's fallback, the final files are committed using an isolated
Git directory under `.scratch/` and the same 13 explicit paths. The commit is
exported as `.scratch/momentum-build.bundle`; the worktree's source branch
cannot be advanced while its metadata is read-only. The source files remain
in place. `ASTRA_BRIEF.md` and `.scratch/` are excluded from the commit.
No push was attempted. The final response supplies the bundle commit id.

Integration 3 release note: the commands above use symbolic local-source
variables in place of workstation paths. Set them to the corresponding
private executable and disc before reproducing this historical handoff.
