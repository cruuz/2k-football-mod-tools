# r62 abilities runtime, 2026-09-05

Public path notation: `<home>` and `<media>` identify the original local home and mounted input directories. Recorded hashes, measurements and outcomes are unchanged.

**EXPERIMENTAL / UNWITNESSED. All presets off.**

Implemented abilities rules v1 in `nfl2k5_abilities_runtime.py`, its GNU
assembly source, reproducible Python byte template, standalone integrity and
bounded instruction tests, both XBE gates, the complete allocator union and
manifest generator. Protected product integration is specified concretely in
`WIRING.md`, with a complete capability handoff JSON. No protected file was
edited. No game, console emulator, GUI display, audio, network or push was
used. Unicorn executed bounded native instruction fixtures only.

The read-only authority was the hub's
`ABILITIES_SYSTEM_RESEARCH_2026-09-05.md`, the beta-61 RC85 product changelog,
the existing ASTRA reports, the shipped roster codec, Momentum and ramp, and
retail bytes checked against the Ghidra corpus. USA XBE SHA-256:
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
The memo's linked scratch artifacts were absent in the hub, so the relevant
byte scan, command tables and descriptor map were reproduced locally.

## Decisions and implemented contract

The seven shipped flags remain at record +0x52/+0x53. The runtime reads the
word mask `0x1EE0`: Speedster `0x20`, Right-Stick Moves `0x40`, Juke `0x80`,
Spin `0x200`, Truck `0x400`, Hurdle `0x800`, Stiff-Arm `0x1000`. It never writes
roster bits, ratings, depth locks, cosmetic stars or future flags. Existing
roster/save editing and its masked undo remain the authoring path. There is
no automatic assignment, tier, import clamp or migration. Zero-flag players
lose these special moves when this opt-in runtime is installed.

Speedster follows the memo's explicit movement rule. The wrapper first calls
the real effective-attribute accessor, preserving its stack modifier and both
native clamp stages. For flagged raw Speed 100..127 it multiplies that result
by raw/100 and bounds it to 0..raw/100; otherwise it caps movement speed at
0..0.99. Negative/nonfinite results are normalized to zero. This is an added
movement-cache rule, not a reconstruction of uncapped retail rating math or
a promise of 28% faster running. Raw 127 with no flag reaches .99; with the
flag it reaches 1.27 at neutral/healthy settings. Native reductions remain
proportional. The first getter still returns 1.0 for both 100 and 127.

Human move filtering is scoped to live phase 14, an attached player holder,
and controller contexts 8/10. The carrier chain is the actual retail
`[0xE5FC00] -> holder`, then `holder+0x1C == 1`; the ball object's +0x1C is
not used as the holder kind. CPU controller marker -1 uses the same live
carrier and permission rule without indexing a human controller table.
Only the command and native charge-request bit are cleared on denial;
throttle and heading are preserved. Denial picks ordinary command 0 and
does not re-decode a lower-priority simultaneous button. Passing, kicking
and QB-evade command contexts are excluded from the move filter.

| Command/state | Required flags |
| --- | --- |
| `18/19` | Stiff-Arm |
| `1A`, stick-click hurdle | Hurdle and Right-Stick Moves |
| `1B/1C` | Spin |
| `1D/1E/20/21/22` | Juke |
| `23` | Truck |
| `24..2B`, all directional/gesture commands | Juke and Right-Stick Moves |
| `5C/5D`, native resolved juke variants | Juke |

This explicitly couples each move's base and powered permission, within the
existing seven flags. Independent base/charge permissions are not encoded.
The common state-initializer gate also protects direct/CPU transitions. It
matches the requested descriptor against the state or steering command; if
neither identifies the variant, it requires the complete known descriptor
family. The shared Spin/Juke descriptor consequently requires both flags
for such ambiguous direct transitions. Denial uses the ordinary native
state descriptor through the real cleanup/store path, before animation entry.

**Meter policy decision:** this opt-in rule confines the native special-move
meter to live ball carriers with at least one applicable move permission.
Generation, CPU instant-ready, and common command processing clear stale
meter/active state on loss of eligibility, no permitted move, or an active
mapped move whose bit was removed. This writes only native state +0x44
(meter), +0x48 (timer sentinel -1), low two bits at +0x90, and the charge
request at steering +0x18. Upper native charge bits are preserved. Native
allowed generation, timers, cheat-ready and consumption execute the original
instructions. There is no global/controller-shared timer or new writable
state; different entities use their own native meters.

The carrier-only policy also disables noncarrier native special-move charge
and denies the nine consumers outside the researched move contract. This is
a deliberate conservative rule with a material gameplay limit, not a claim
that every retail powered tackle/catch/block is unchanged. Passing/kicking
*input commands* are not filtered, but the impact of native charge cleanup
on other mechanics remains a required witness. No phantom permission is
assigned to an unclassified caller merely to preserve a powered animation.

Off-week settings are None or an integer **zero-based regular-season row
0..17**; UI labels are Week 1..18. Only `(mode, stage, week) == (2, 8,
configured_row)` returns zero effective abilities. The predicate runs on
every check, so loading directly into that row needs no advancement event.
The following row automatically restores the stored flags. Low native meter
state is cleared at the next command/generation/activation check; no frame
clock or persistent switch is introduced. No additional week, schedule
rewrite, saved-season expansion or simulated-game effect is implemented.

## PROVED: consumers, hooks, ABI and allocation

The byte-granular E8/E9 scan finds **15** direct calls to `2D4740`, rather
than relying on Ghidra's incomplete caller annotations. The immutable
120-byte caller map uses the actual native return address plus the current
state's initializer identity. It never infers a delayed charged move solely
from steering +0x1C. Unknown caller, mismatched state/initializer, or missing
specific flag clears charge without entering powered consumption.

| Call PC | Mapped initializer / disposition |
| --- | --- |
| `29089B` | `290880`, hurdle |
| `2DBBCC` | `2DBBC0`, resolved juke |
| `2DC803` | `2DC7F0`, Spin/Juke, resolved by current state |
| `2DCF93` | `2DCF70`, Stiff-Arm |
| `306DF7` | `306DE0`, directional/gesture Juke |
| `30D2C2` | `30D2A0`, Truck |
| `18D2C6`, `18DF7C`, `1E773E`, `1E7BA2`, `2319CB`, `291D60`, `308512`, `30EDA7`, `31793D` | Outside five-move contract; powered consumption denied |

The call inventory is complete for direct E8/E9 encodings targeting that
entry in the supplied retail .text, not a whole-program proof of all possible
computed calls. The entry hook also intercepts computed calls to the entry;
an unknown return address denies permission. No interior direct entry into
any displaced span was found. Descriptor pointer tables and each relevant
20-byte descriptor are SHA-pinned. All three layout tables for contexts 8/10
are pinned, and their direction/gesture columns match the memo.

| Hook VA | Bytes replaced | Purpose |
| --- | ---: | --- |
| `75CC8` | 5 | Wrap the native Speed accessor before the cached store |
| `15647D` | 5 | Post-decode human command gate |
| `18EC6D` | 5 | Common human/CPU command accounting and callback-index gate |
| `1CD550` | 5 | Common state initializer, including direct transitions |
| `2D43F0` | 5 | Native meter-generation entry |
| `2D46D0` | 9 | CPU instant-ready entry |
| `2D4740` | 7 | Shared native charge-consumption entry |

All displaced instructions are replayed with their original continuation and
stack convention. The Speed wrapper returns one x87 value and `ret 4`, with
lower x87 values retained; the other wrappers add no x87 values. Helpers
preserve caller registers and flags as required. No helper calls rendering
or uses cosmetic-star status. Native animation asset initialization and
notification helpers are peripheral fixtures in the bounded tests, not
played animation evidence.

`REQUESTS = (("nfl2k5_abilities_runtime", "code", 1072, 16),)`: **1,072 RX
bytes, zero RW, zero new general RO**, within the 1,536-byte row. Instructions
occupy 836 bytes; alignment, immutable week/float, move masks, caller map and
descriptor-family map account for the remainder. The constants are immutable
RX content outside retail .text, installed with `space.install_code` and
sealed by the existing directory/digests. No retail cave, gap or oracle
unknown was used as an allocation. Standalone allocation VA `0x14DA000` is a
receipt only; the union can assign another address.

The budget planner was run before building on the committed beta-62 fixture,
then on a scratch copy replacing the abilities estimate with its actual
request and adding all three landed beta-62 owners. Both plans fit. The
allocator implementation/page counts and committed budget fixture were not
changed. Outputs are `.scratch/abilities/budget-plan.txt`, `requests.json`
and `actual-plan.txt`.

`status` and `apply` recognize complete retail or exactly installed state,
verify dependent native code/tables, allocation geometry, code/settings and
all section/directory seals, and refuse mixed/foreign bytes before mutation.
Replays preserve installed week when omitted. Explicit None or another week
on a configured installation refuses with a rebuild message. Receipts give
whole hook before/after spans, the code installation, allocation, byte count,
source/result hashes and reservations. No proprietary output is committed.

Momentum's turn/contact hooks and ramp's `75CD5` store remain separate.
All six application orders of abilities, Momentum and ramp produce identical
bytes, and the actual Speed-call/store instruction path runs with both
Momentum installed and ramp off/on. The complete allocator owner union also
produces identical forward/reverse output. No changes to Momentum's owner
or the Build profile's existing ramp-normalization policy were needed.

## Verification

Feature verification completed so far:

| Command | Result |
| --- | --- |
| `python3 tools/nfl2k5_abilities_runtime_assemble.py --check` | Template reproduced by GNU as |
| `python3 tests/mod_editor/test_nfl2k5_abilities_runtime.py` | 12 passed, 23.040 s |
| `python3 tests/mod_editor/test_nfl2k5_abilities_unicorn.py` | 12 passed, 7.354 s |

The instruction suite executes both native attribute clamps, the native
right-stick priority selector and installed post-decode/shared command hooks,
every required bit for every mapped command on controllers 0..3 and CPU -1,
native meter generation/cheat/CPU ready and all six consuming families,
deliberately stale steering, insufficient/full meter, exact week tuple and
restoration, possession/player changes, state-initializer rejection, flags,
stack/x87 depth and indirect write destinations. Each run has an explicit
instruction bound (normally 5,000) and checks its stop address. Missing retail
evidence, Unicorn or assembler has a precise standalone unittest skip.

The real manifest command completed successfully:

```text
/usr/bin/time -v python3 tools/nfl2k5_cave_oracle.py manifest \
  '<media>/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  --xiso '<media>/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso' \
  --work-dir .scratch --json .scratch/abilities/manifest.json
```

It ran the real experimental-preset build and the separate complete-owner
probe on disposable disc copies, installed abilities with off-week row 7,
read back the resulting grown XBE and verified its section digests. The
builder removed its temporary disc on completion. No supplied disc, archive
pack or extracted XBE was modified. This is a real transport/ownership
proof, not a build with protected abilities UI wiring already installed.
The manifest honestly retains `runtime_panel_resources: false` for the
separate owner probe; the preset build has its own paired scorebug pass.

The manifest records **8,340 reservations, 90 observed writer calls and
89 source fingerprints**. Complete-owner XBE SHA-256 is
`f1824732f9a28b43d2cbac3859b009846a8d28f06dc6b926a3ddfa1c2c09c680`.
The manifest build took **263.73 s**, peak RSS **1,169,520 KiB**, below 2 GB.
All image/pack transport uses the existing bounded descriptor-based writers;
new tests load only the approximately 12 MiB XBE and small synthetic objects.

The first cave-gate run reproduced the base's implicit-v3 versus legacy
assertion: its complete beta-62 union creates v3 even when the test's explicit
`scaleout` switch is False. That assertion now branches on the actual layout
version and still checks all 52 pages, no retail mapping overlaps, zero
legacy-page encodings and the disclosed v3 raw candidates. It does not bless
raw encodings as executed references or use unknown retail bytes as caves.
An added assertion's `Evidence` access was also corrected to its typed API.
No scale-out suite or other known-red allocator-ordering test was changed.

Capability handoff validation passed with the combined registry's schema
rules (`check_files=False`); every newly referenced evidence/backend file
was checked to exist. A full existing-registry file check is independently
blocked by its absent `docs/research/apf_audio.md` evidence. No registry
validator was changed or its file-check default relaxed. The new row remains
a concrete handoff for Claude to merge during protected integration.
Source-fingerprint checks remain enabled; the checked-in protected manifest
intentionally stays unchanged. Final gate and commit results follow below.

## HYPOTHESIS and Noah's required witness list

Nothing here is labelled witnessed. The native byte/ABI proofs do not establish
Xbox loader acceptance, actual displacement, animation quality, game balance,
save lifecycle or CPU franchise simulation behavior.

1. Build an explicitly opted-in disposable comparison after Claude wires the
   protected handoff and regenerates the manifest. Record the XBE hash, rules
   version, request union, selected off-week and the roster/save ability flags.
   Verify boot, practice, exhibition and franchise entry. A rebuilt disc does
   not migrate ability flags into an existing franchise save.
2. Compare raw Speed 99 and 127 with Speedster off/on, healthy/injured/fatigued,
   home/away sliders, human/CPU, Momentum off/on and ramp off/on. Measure actual
   distance and animation through starts, cuts, contact and stopping. Verify
   the 127 permission does not imply a 28% displacement increase.
3. Test every direction and gesture, stick-click hurdle and each button move,
   all three layouts, two controllers, controller switching, scrambles and
   kick/punt returns. Toggle each required flag independently. Verify denial
   preserves ordinary steering, simultaneous denied/allowed input follows the
   documented priority, and passing/kicking/QB-evade inputs behave normally.
4. For Juke, Spin, Truck, Hurdle and both Stiff-Arms, test ordinary and full-
   meter moves with allowed/denied flags, human and CPU. Include the native
   CPU instant-ready and cheat-ready paths, holding through a switch, stale
   steering after activation, turnovers and possession changes. Examine the
   ambiguous shared Spin/Juke descriptor fallback with only one bit granted.
5. Specifically compare **noncarrier** powered tackles, catches, blocks and
   other charge consumers: this prototype deliberately removes their native
   charge. Decide whether that conservative carrier-only rule is acceptable
   before wider release. Further per-action permissions need additional
   researched consumer semantics; the current seven-flag contract does not
   grant them. Check kicking and passing mechanics for any meter coupling.
6. Enter, advance into and load directly into the configured existing regular-
   season week. Verify Speedster, base moves and charge are off for both
   sides; a held/ready/active meter is cleared; the next week restores flags.
   Repeat the same ordinal in exhibition, preseason and postseason to verify
   the exact mode/stage predicate and preserved cosmetic stars.
7. Verify save/reload, trade/release, depth changes, deliberate cloning,
   created/reused identities and season rollover preserve or clear flags as
   intended by the existing roster/save workflow. Check depth-lock and star
   bits separately. Native clone paths that omit +0x52/+0x53 remain a known
   inherited lifecycle risk; this runtime does not repair those copies.

No arbitrary X-factor effects, guaranteed tackle outcomes, independent base
and charge flags, automatic HOF assignment, simulated-game parity, universal
record-padding alias safety, or additional franchise week is claimed.

## Final gates and delivery

All commands below were standalone unittest invocations, with
`NFL2K5_CAVE_MANIFEST=.scratch/abilities/manifest.json` for the three shared
suites. No skip or source-fingerprint bypass was used in these final runs.

| Final command | Result | Peak RSS where measured |
| --- | --- | ---: |
| `python3 tests/mod_editor/test_nfl2k5_abilities_runtime.py` | 12 passed, 23.040 s | Small XBE fixtures |
| `python3 tests/mod_editor/test_nfl2k5_abilities_unicorn.py` | 12 passed, 7.354 s | Bounded mapped XBE and synthetic objects |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 51 passed, 120.676 s | 303,788 KiB |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 63 passed, 194.849 s | 468,140 KiB |
| `python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` | 28 passed, 63.305 s | 898,348 KiB |

**166 final tests passed.** GNU assembler reproduction, Python compilation
of all changed Python sources, full registry schema plus new evidence-path
checks, `git diff --check`, complete-union forward/reverse byte identity and
all 89 fresh-manifest source fingerprints also passed. The largest measured
process was the real manifest build at 1,169,520 KiB. The old failing cave
log is retained separately from its final passing log under `.scratch/abilities`.

Branch is `astra/r62-abilities-runtime`, parent
`490b3c1268eb4515f7e3247d06cfe2306f141992`. The normal explicit-path commit was refused because the linked Git
metadata could not create `index.lock` on the read-only filesystem. The
authorized fallback uses `.scratch/abilities-commit/.git`, this worktree,
the same parent commit and branch name, and explicit paths for both staging
and committing. Delivery is `.scratch/r62-abilities-runtime.bundle`; all
edited files remain here. The shared branch metadata is not advanced.
Commit subject: `Implement experimental player abilities runtime and proofs`.
Only the 14 delivered source/test/report/handoff paths are included.
`ASTRA_BRIEF.md`, `.scratch/`, generated game bytes and every protected file
are excluded. No push. Logs, disposable-build manifest, budget plans and
research notes stay in this worktree's `.scratch/abilities/` for integration
review. Protected UI/build/closure wiring and the release manifest remain
Claude's concrete next step as required by the brief; gameplay witnesses
remain Noah's pending work.
