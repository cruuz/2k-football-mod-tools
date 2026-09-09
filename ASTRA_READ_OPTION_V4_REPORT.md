# Read option v4 engagement diagnostic, 2026-09-08

**EXPERIMENTAL / UNWITNESSED. Live engagement is UNPROVED.** Noah played v3 on
bm and reported that the quarterback ran forward, no handoff occurred and the
option/RPO appeared unchanged. He did not report seeing the EDGE cue; this
investigation assumes it did not draw. That is the only gameplay witness.
A paired build receipt and a successful CPU replay do not establish that the
running game entered the owner.

Base: `77d1c49f682e380b75f1a7290a806a47845608a9`, branch
`astra/r64-read-option-v4`. Work stayed in this worktree, with read-only retail,
bm and Ghidra evidence. No game boot, game emulator, GUI, display, audio or network
was used. Unicorn runs below are bounded instruction tests, not gameplay.

## Delivered result and conditional scope

The existing runtime now has an explicit diagnostic variant which draws native
FONT4 text through the existing HUD hook and records snap, lookup, dispatch,
input and decision values in its own RW allocation. Claude can build the
instrumented candidate with the existing runtime flag and the tested scoped
adapter in [WIRING.md](WIRING.md). Normal v3 executable output remains byte for
byte identical to the pinned base writer. There is no new preset default.

**Decision:** do not install a third proposed controls fix before learning
whether the running game reaches it. Item 3 of the brief explicitly requires
the controls redesign **once engagement is proved**. That prerequisite has not
been met. A real, cancelable handoff starting at the snap, pass/pitch cancellation
and an explicit keep button are consequently **not implemented or claimed in
this delivery**. The post-witness design below is specific, but remains a design.
The diagnostic is the deliverable needed to resolve this prerequisite without
repeating the earlier unsupported assurance.

The normal owner already consumes all 2048 code bytes. Both variants keep
**2048 RX / 256 RW / 88 RO**, aligned to 16. The diagnostic uses **1928 generated
code bytes and 120 padding bytes**. Its text and observations replace the normal
EDGE marker and CPU edge resolver/snapshot. **Diagnostic CPU reads give; use a
human QB for the engagement witness.** Human v3 decision, timing, movement
suppression and native dispatch behavior match normal v3 in the tested frames.
No new cave, allocation, table capacity, pack recipe or script geometry was
introduced. The unchanged option pack remains a useful comparison with bm.

`apply(..., diagnostic=True)` or CLI `--diagnostic` selects the probe on a
supported rebuild. Status validates both complete variants, their matching RO
prefixes, all six hooks, zero initial RW, section digests and allocator seals.
Omitted settings preserve an installed variant and table. An explicit change of
mode/table or mixed/foreign bytes refuses before mutation. Receipts/settings
report version 4 and `diagnostic=True` only for the probe; normal reports version
3. Both retain `runtime_witnessed=False`. HELP_TEXT now acknowledges the failed
v3 play observation instead of presenting the intended controls as established
live behavior. The existing capability document has the same evidence boundary.

## Identity finding from the actual bm disc

**PROVED, bounded reads and native instructions:** bm contains an installed v3
owner with two authored records. The exact MIN resource differs from the old
fixture's final resource, while its paired lookup table is identical. Thus
fixture equality was not assumed and whole-book identity was not substituted
for the disc evidence.

Read-only input:

```text
/home/noah/2K5 Mod Studio Builds/NFL 2K5 MOD TEST 2026-09-08bm (beta-62 RC86 FINAL CANDIDATE: Experimental + gameplay opt-ins + MyCareer v4 + read option v3 + kickoff v6 + rim).xiso.iso
```

| Evidence | Value |
| --- | --- |
| bm disc length | 6,324,822,016 bytes |
| XDVDFS default.xbe extent | offset 6,312,521,728; length 12,300,288 |
| bm XBE SHA-256 | `a607da2b454021e078fc51935d62c62280e8f8c679d6ed9c12b583c3658d6f9b` |
| Actual MIN resource | 78,768 bytes, including the 32-byte resource wrapper |
| Actual MIN SHA-256 | `c8eaf4057de5b280b7fd1423fa574c13a3d2bb471167a18a7e9f20b121356cf0` |
| Earlier fixture MIN SHA-256 | `5d03682a9444331a611a5ec79aee81ed011ec8d3e5810d01ec6682eecb473dd4` |
| Actual 64-byte table SHA-256 | `fb0d3d290771ef6f6653dc4f6edc50a6c25de4a3555a47a11f264066d205064c` |

Native loader `0x161E30` loads the actual resource body into a pool selected by
`0xE2F10`: `0xB75A40` or `0xB88DD0`, stride `0x13390`. Its field-relative pointer
relocation uses `field address + encoded value - 1`. The loaded book name pointer
is at base `+0x30`; each play record starts at base `+0x33FC + index*96`; the QB
slot-zero descriptor is eight bytes into that record. A descriptor's script
pointer is at `+4`, and its play name pointer is eight bytes before it.

| MIN I Jokers play | QB descriptor offset | Pool 0 pointer | Pool 1 pointer | Name hash | QB script hash |
| --- | --- | --- | --- | --- | --- |
| 155, SD Zone Read EXPERIMENTAL | `0x6E24` | `0xB7C864` | `0xB8FBF4` | `0xFAE7C3F2` | `0x786CFC17` |
| 157, SD RPO Slant EXPERIMENTAL | `0x6EE4` | `0xB7C924` | `0xB8FCB4` | `0xC91A6DEB` | `0x27B02D10` |

Both records carry book hash `0x5612647F`, back script hash `0x60CEE39A`, back
slot 10 and authored EDGE slot 1. The RPO receiver is slot 7. The runtime derives
the index from the bounded, 96-byte-aligned descriptor offset and verifies all
four FNV-1a hashes. It never accepts a name-only match or an arbitrary copied
pointer. Original authoring fixture defender slots 2/6 are not runtime indices.

The native assignment producer was also executed, rather than merely planting
the descriptor for this test. `0x1CEAC0` selects the descriptor from the supplied
team primary/alternate play selection, using the native slot mapping, then
calls `0x1CE600`. At `0x1CE634`, the initializer stores that exact descriptor
pointer into actor state `+0x41C`; native `0x1B8790`/`0x1B84E0` initialize/decode
node -1 (byte 255). This path **retains the relocated descriptor; it does not
copy it into the actor**. The selector and initializer prefix pass for both
plays in both pools. Visibility, animation transition and movement-vector reset
are named ABI boundaries; the selected menu records are supplied inputs.

**Finding:** relocation by this retail loader and assignment path is compatible
with bm's table. The simple explanation that these actual 155/157 records were
compiled against incompatible offsets is not supported. **HYPOTHESIS:** another
live selection/copy/reassignment path, a later pointer change, missing snap
invocation, or failure to reach condition node 2 could still prevent engagement.
The tests do not establish which occurred in Noah's session. A descriptor copy
outside both pools deliberately produces a diagnostic miss; hashes are not
relaxed to hide that finding.

## What the diagnostic observes

The existing snap hook is `0xB6FBD`, inside native `0xB6F30`, during phase 13 to
14 transition. It clears the owner's state, records `snap_seen`, resolves the
actual offense slot-zero QB through native `0x1894F0`, and records its descriptor
and table result. Diagnostic snap identity deliberately does **not** require
condition node 2; snap at nodes 255, 0, 1 or 2 is observable. Missing actor state
records a miss safely. The normal v3 lookup remains unchanged.

The scheduling hook at `0x21516A` records the snapped QB's actual descriptor,
node, callback, raw held/rising input, controller context/layout and interpreted
command/throttle **before** the owner's intervention. The tick hook at
`0x1AF009` separately counts condition calls and accepted distinct-clock samples.
A copied decision survives native task disposal for a photograph. Native
new-play reset at `0x1AD9C3` and the next snap clear all private telemetry.

The existing HUD hook at `0x646A1` builds a bounded UTF-16 line in owner RW,
clones the same HUD path's FONT context at `0xA95040` to 128 stack bytes, and
calls native `0x47420` -> `0x46DF0` -> the native 2D glyph path. Text is white with
the inherited shadow, left/top aligned at native HUD coordinates **32,64**.
The shared font context and caller x87/XMM state are preserved, and the displaced
native HUD call still executes. It does not depend on the EDGE marker queue.
The committed font test supplies the real FONT4 resource and reaches 192 native
vertex submissions for `READ 155 pend 1 1.05`, including when the adjacent
widescreen and team-column owners are installed. GPU submission and actual
on-screen visibility remain unwitnessed.

| Line or state | Interpretation |
| --- | --- |
| No line before the first snap/reset | Expected; the HUD cannot activate the line without `snap_seen` |
| `READ 155 snap 0 0.00` | Snap hook and identity matched; no accepted condition sample yet |
| `READ 155 pend 3 1.05` | Three distinct clock samples; still pending; absolute since-snap deadline 1.05 seconds |
| `READ 155 give 6 1.05` | Give decision committed; this alone does not prove animation or ball transfer |
| `READ 155 keep 6 1.05` | Existing v3 keep decision committed |
| `READ 157 pass 6 1.05` | Existing v3 RPO pass decision committed; this alone does not prove a thrown ball |
| `READ miss 155` | A bounded index was derived but a paired identity was not found |
| `READ miss 154` | An unpaired known play, useful as a negative control |
| `READ miss ???` | No bounded index was available, including an out-of-pool descriptor at snap |

The examples use replay times 0.05, 0.30, 0.55, 0.80, 1.00 and 1.05 seconds.
Actual sample counts and deadline depend on live condition entry and update
rate; **do not require the literal count 6 or deadline 1.05 in a photo**. Deadline
is first accepted sample plus one second, not remaining time or animation
progress. It is displayed to hundredths, while gameplay uses the original float.
The full unsigned sample count fits without a three-digit wrap. Miss lines may
have trailing spaces, with no effect on their meaning.

An absent line is not conclusive by itself. If the snap hook never runs, nothing
is drawn, as requested. However, a missing HUD callback/font also prevents a
visible line. RW distinguishes these: `snap_seen=0` means no snap was recorded
since reset; `snap_seen=1,hud_calls=0` means no subsequent diagnostic HUD call;
nonzero HUD calls with `font_pointer=0,text_calls=0` indicate unavailable native
font context. A nonzero text-call count proves submission, not display. A
permanent `snap 0` with nonzero dispatch calls but zero condition calls points
toward callback/node routing; a `pend` count that freezes points toward clock
or lifecycle gating. A matched snap row followed by a zero latest lookup row
records a later failure rather than silently treating the initial match as live
engagement.

### RW capture contract

Read exactly **256 bytes** at this build's `read_option.allocations(xbe)['data']`
VA. Do not hard-code bm's address, read a whole memory image, or use the file's
zero-filled initial RW as runtime evidence. All offsets below are decimal;
pointers/counters are little-endian dwords and the three named floats are IEEE
single precision.

| Offsets | Fields |
| --- | --- |
| 0, 4, 8, 12 | active actor, task, descriptor, roster |
| 16, 20 | sample clock (float), accepted sample count |
| 28, 32, 44 | sampled controller, queued receiver, deadline (float) |
| 48, 52, 56, 60 | snap seen, latest lookup row, snap QB, last derived play index (`FFFFFFFF` unknown) |
| 64, 68 | snap descriptor, last dispatch descriptor |
| 84, 88, 92, 96 | raw held, raw pressed, input context, controller layout |
| 100, 104 | interpreted command, throttle (float), before suppression |
| 112, 120, 124 | dispatch callback, dispatch controller, snap lookup row |
| 128, 132, 136, 140 | HUD calls, native text calls, font pointer, condition calls |
| 144, 148, 152 | retained decision, last dispatch node, dispatch calls |
| 160..255 | 48 UTF-16 code units including terminator |

Decision is `FFFFFFFF` pending, 0 keep, 1 give, 2 pass. Use snap/lookup/sample
fields to distinguish idle or missed from decision zero. Unlisted offsets are
retained v3/private bookkeeping, not a new public state format. The CLI decoder
prints those observations with `runtime_witnessed=False`, bounds its read to
257 bytes, and represents nonfinite float dumps without invalid JSON.

## Why earlier replays could pass while the game did not

The opening "PROVED ... records engage" and broad diagnosis in
[ASTRA_READ_OPTION_V3_REPORT.md](ASTRA_READ_OPTION_V3_REPORT.md) were too strong.
They apply only to constructed instruction paths and do not establish the live
cause. Noah's bm observation invalidates using them as a gameplay assurance.

| Earlier supplied assumption | What remains uncertain and what v4 resolves |
| --- | --- |
| Final authoring fixture was the game resource | v4 reads bm's actual XBE/MIN/table and executes its retail loader. The full resources differ; the relevant table matches. |
| Descriptor already in actor state; QB already at node 2 with callback `0x1AEF80`, back at node 1 | The native selection/store path is now exercised, but play-call menus and snap-to-condition transition remain supplied. Snap row, descriptor, node, dispatch and condition counters expose where live execution stops. |
| Snap/reset hook was invoked directly by the harness | `snap_seen` plus the HUD/font counters records actual hook invocation in the instrumented game; a CPU call is not substituted for that witness. |
| Controller index/layout/context and raw held/rising masks were written by the fixture | Raw input, context, layout, interpreted command and throttle are now observable before suppression. The diagnostic does not prove the entire live XInput producer or the timing of a user's release. |
| Native per-frame dispatcher runs for the fixture QB with known ball owner and clock | Phase, ball ownership, active controller and task/lifecycle checks may differ live. Dispatch/condition/sample counters and deadline narrow this; the owner still fails closed. |
| Actor poses were collision-free and sampled at/near mesh approach targets | Native steering and callbacks execute, but contact and real position integration were not proved. A `give` photo with no visible exchange moves the investigation to movement/animation; the line cannot prove collision physics. |
| Real handoff animation descriptor and exchange event were supplied at the chosen frame | Native transfer executes on the event, but the fixture does not establish that the live animation is selected or emits it. Photograph/observe the mesh and possession separately from the `give` line. |
| Font/marker assets were resident; camera/queue inputs and GPU boundaries were supplied | v4 executes real FONT4 glyph code and observes font availability, but Noah must witness display. A text-call count alone is insufficient. |

The full-frame give replay still executes native opcode mapping/initialization,
partner approach/readiness and animation selection `0x313A00`. It supplies
animation descriptor `0x531A08` and exchange callback `0x313520`; native detach
`0xDDCA0` -> `0x26A4C0` and attach `0xDDCD0` -> `0x26A4A0` change ownership to
the back once. Those outcomes are not assigned by the test. This is proof of
the event path, not of the animation's natural occurrence. Pass replay executes
native `0x19C740` and `0x19BAE0` through command `0x42`; rendered release, flight
and catch remain outside the replay.

The inspected native input producer `0x39380` obtains an XInput packet and
converts its eight analog channels to held bits `0x100` through `0x8000`.
The running-context table has command 45 on the `0xC000` column, and `0x121119`
queries command 45 before setting interpreted control `+0x18` bit `0x100`.
Earlier pitch tests wrote that **interpreted** bit directly. They did not prove
physical-button production or all command/context timing. Do not label that
interpreted bit as a physical pitch button based on those tests.

## Post-witness controls decision, not installed

Once the diagnostic proves live identity and condition dispatch, the next
implementation must start both native handoff participants immediately, retain
an explicit pre-exchange cancel window and let no input complete the give.
Waiting stationary for one second and only then starting handoff is not the
requested animated mesh. Merely forcing ball ownership or changing the branch
label is also insufficient.

Chosen proposed retail-button labels are **A, a new press after snap release,
for explicit keep; X for pull-and-pass; the authored B receiver on this RPO;
Black for pull-and-pitch**. These are proposed new bindings, not an assertion
about retail's stock pitch mapping or Noah's xemu host-controller mapping. Before
installation, close the physical packet-to-context-command proof and put these
labels in the actual HELP_TEXT. The current HELP_TEXT describes retained v3
controls and does not claim these future bindings work.

Cancelable give must end both native partner tasks/links safely before the
exchange event, then invoke the native pass initialization/request path or
native pitch kind 1 (`0x300B00` -> `0x2FF7C0`, native pitch command `0x4E`). A
late press after native transfer cannot detach or teleport the ball back to the
QB. An unavailable receiver, absent pitch partner, contact, turnover, play reset
or controller change must keep native ownership consistent. Replays must begin
with actual native play assignment and progress from snap, rather than inserting
condition node 2 or injecting an exchange to assert animated cancellation.
Witness the no-input animated give first, then pass/pitch/keep cancellation,
then late/invalid inputs. Budget the implementation before changing scripts:
the complete normal v3 owner has no spare RX, and this job takes no extra bytes.

## Noah's precise witness list

1. Claude rebuilds from the supported base with the existing option pack and
   final pairing, explicitly selects the diagnostic, and reads back version 4,
   `diagnostic=True`, two rows and actual RW address. Record the candidate name.
2. With a human QB, select MIN I Jokers 155. Before snapping, expect no READ
   line. Snap and photograph/video the small white line near the upper left.
   It may show `READ 155 snap 0 0.00` only briefly before `pend` appears.
3. Release snap and otherwise do nothing. If dispatch engages, expect
   `READ 155 pend N D.DD` with increasing samples, then `READ 155 give N D.DD`.
   Separately record whether the QB runs forward, whether the back approaches,
   whether a mesh animation starts and who actually receives the ball.
4. Repeat 155 holding snap throughout the current v3 window, then holding full
   stick input. Expected decisions are keep for continuous hold, give for
   release/no input; stick should not force an early read exit if engaged.
   These are diagnostic v3 controls, not the future explicit-keep binding.
5. Select MIN I Jokers 157. Expect play number 157. No input should reach `give`.
   Holding snap and pressing the authored receiver during the window should
   reach `pass` if native readiness accepts it. Record whether a throw actually
   occurs. A decision line alone is not a passing-animation witness.
6. Select an ordinary unpaired play. Expect `READ miss <its native index>` after
   snap and normal retail behavior. A wrong number, miss on 155/157, a line stuck
   at snap, or no line is a finding to preserve, not a reason to call the probe
   successful. Capture the 256-byte state when possible and decode it with the
   command in WIRING.md, recording the same play and moment as the photo.
7. Check the next-play reset, quarter change, offense changing sides and a
   controller/layout change. The previous line should clear on reset and the
   next snap should use the new play. Capture a fresh sample rather than assuming
   that a successful first drive establishes every lifecycle path.
8. Only after a witnessed matched identity and advancing condition samples,
   proceed to the cancelable handoff redesign. If `give` appears but no exchange
   is seen, investigate native movement/animation before claiming a controls fix.

## Validation and resource accounting

All commands use plain standalone `unittest` entry points. The XBE gates and
oracle use `NFL2K5_CAVE_MANIFEST=.scratch/read-option-v4/manifest.json`; the
ownership test generates it with `NFL2K5_READ_OPTION_V4_MANIFEST` set to that
path. The diagnostic frame trace uses `NFL2K5_READ_OPTION_V4_TRACE`.

| Command (`python3 tests/mod_editor/<file>`) | Final result | Peak RSS, KiB |
| --- | --- | --- |
| `test_nfl2k5_read_option_runtime.py` | 10 passed | 130012 |
| `test_nfl2k5_read_option_unicorn.py` | 14 passed | 164868 |
| `test_nfl2k5_read_option_controls.py` | 15 passed | 173264 |
| `test_nfl2k5_read_option_frames.py` | 9 passed | 151428 |
| `test_nfl2k5_read_option_diagnostic.py` | 19 passed | 253736 |
| `test_nfl2k5_read_option_diagnostic_manifest.py` | 1 passed (13.472 s) | 173704 |
| `test_nfl2k5_play_intents.py` | 18 passed | 59324 |
| `test_nfl2k5_play_intents_build.py` | 3 passed, 2 opt-in full-disc tests skipped | 149356 |
| `test_xbe_patch_memory_writes.py` | 91 passed (814.004 s) | 342284 |
| `test_xbe_patch_cave_references.py` | 103 passed (940.615 s) | 527940 |
| `test_nfl2k5_cave_oracle.py` | 28 passed (201.195 s) | 908384 |

The memory and cave gates each include forward, reverse, scale-out and reverse
scale-out installation, with every existing owner. The final memory gate was
repeated after the last setup-state guard change; the earlier corrected version
also passed all 91 tests. Runtime, control and frame suites retain the normal
v3 CPU EDGE/hold/give/keep/RPO/Gun coverage. Private-evidence tests name their
skip reason when the retail XBE/archive, bm, Unicorn, Capstone or pinned Git
objects are unavailable. Full-disc opt-in tests were not enabled.

Additional checks: `python3 tools/nfl2k5_read_option_runtime_assemble.py --check`
passed; `python3 tools/nfl2k5_xbe_space.py plan --requests
tests/fixtures/nfl2k5_allocator_beta62_requests.json` passed with unchanged owner
requests. CLI apply with the actual two-row table, `--diagnostic`, status readback,
exclusive-output refusal and 256-byte state/257-byte refusal passed; its temporary
12 MB XBE was deleted. Capability schema validation and all revised-entry evidence
and module-command file checks passed. The broader registry file check stops at
an unchanged missing `docs/research/apf_audio.md`, outside this feature; no claim
is made that that whole-registry check passed. Report links/labels and exact
comparisons of all eleven named protected files to the base passed. Final
`git diff --check` and current scratch source-pin validation passed before
commit. The selected suites total 313 tests: 311 passed and two full-disc cases
skipped. The largest measured process used 908,384 KiB, below the 2 GB cap.

The initial stack attempt correctly refused a font dependency slice that
included the neighboring widescreen/team-column caves. It was corrected to pin
only the actual 2D glyph helpers, line walker/table and string wrapper, with an
added both-orders native glyph test. No foreign bytes were normalized or exempted
to make that check pass. Missing pre-live actor-state telemetry was also guarded
and tested. Final source/template and manifest checks are recorded below.

A full disposable disc build would violate the 100 GB free-space floor. At the
recorded preflight there were 105,980,936,192 free bytes; one 6,300,499,968-byte
plain source copy alone would leave 99,680,436,224, before growth or writer
staging. `df -h /` was checked. A read-only 1 MiB block scan found no all-zero
blocks to make a simple sparse copy useful. No disc/archive pack was loaded into
RAM and **no disposable disc or pack copy was created or remains**.

The scratch oracle manifest is a labeled, test-only revalidation of unchanged
reservations. Its standalone test verifies every unaffected source fingerprint,
executes hash-pinned base v3 and current normal writers with empty/paired tables
in two allocator layouts, requires byte identity, and restores only the
existing diagnostic owner bytes before recomputing legitimate metadata to prove
exact equivalence. Original disc fields are explicitly labeled inherited;
`new_disc_built=False`, `release_manifest=False`. The oracle still checks current
source pins. This is not a replacement for Claude's real disc manifest build,
and protected `data/nfl2k5_cave_reservations.json` is unchanged. WIRING.md gives
both the bounded local commands and the required release rebuild.

Scratch evidence contains JSON/logs and small source probes, including
`disc-bm.json`, `diagnostic-frames.json`, `manifest.json`, budget reports and test
logs. It stays below 200 MB. No protected implementation file, main-tree source,
other worktree, release version, workflow or release test was edited. The
remaining gaps are live engagement, actual display/animation/collision and the
explicitly conditional new controls, plus the deferred real-disc release
manifest. No gameplay success is claimed.

Resource check before bundle creation: 3,026,139 scratch bytes and 105,885,945,856 bytes free on the main drive. No disc/pack copies or temporary CLI XBE remain.

## Commit handoff

The final explicit-path `git add`/`git commit` attempt was refused because the
worktree's Git metadata directory is read-only. The brief's authorized fallback
is `.scratch/read-option-v4.bundle`, containing a commit whose parent is the
base named above, created with explicit paths in a temporary Git directory.
The original worktree HEAD remains at the base; its earlier staging may predate
the completed report. The finished files on disk and the verified bundle are
the handoff, not that earlier index snapshot. The bundle receipt alongside the
logs records the commit ID, paths, verification and cleanup. No push was made.
