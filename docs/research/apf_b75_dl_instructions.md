# b75-a1: called defensive line instruction versus apparent Gap

2026-09-21. Research only. No gameplay patch. Cause of Urianus's reported
failure remains **unproved**. The supplied images do not expose the live call
tuple, assignment pointer, shift selector, or player coordinates. The actual
beta 73/74 game folder and its installed patches were not available locally.

The bounded proofs establish three useful facts:

1. 4-3 Base has distinct assignments and survives the native assignment reader
   and CPU player lane resolver on BASE and TU 1.1, including with the tested
   shipped runtime options installed.
2. A controlled production export changes O-ManBlock but leaves MASTER and
   every roster-referenced defensive book type byte-identical to retail.
3. A constructed displacement case produces exactly the Gap Left/Right **lane
   vector** while retaining Base's assignment and modes. Appearance alone does
   not establish that a named Gap play was selected.

This does not disprove the tester's symptom. It rules out specific mechanisms
under the recorded inputs and identifies the runtime values needed to close it.

## Inputs and evidence ownership

Checkout: `56b537342331a2c9ee2f2208c2efbe31ae32208c`, beta 74.
Job a2 had produced commit `8adddbc0426507c7ea1aa155d5adb2f231b5757a` in its
separate bundle; it was not in this checkout's `origin/main`. This job does not
modify or claim integration validation of a2. Import this research after a2.

| Input | SHA-256 |
| --- | --- |
| Retail default.xex | `981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f` |
| Decoded BASE image | `cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf` |
| Reconstructed TU 1.1 image | `65f522ce1cdda42cf19c112e9ec07302e89c81e4148c9f22e6db5e03952f9457` |
| MASTER PLAY body | `2de9d17dd4de29c37b005fabf4b1e5db7017556ae538fde2be6b3aca1c70a891` |

Owned inputs are read from the retail extraction. Reused, hash-checked flat
images were `/tmp/b75-a2-native.pe` and `/tmp/b75-a2-tu.pe`. No executable,
compressed game resource, or media copy is included in this change.

Viewed evidence under
`/home/noah/Desktop/2K5-8 Editors/discord-dump-2026-09-21-dms/`:

- `attachments/dm_urianus_67a3cbfda12860b5da80d91e3d7f8ec520c256d6_2.jpg`:
  the visible call page says 4-3, A Base, B Raz... .
- The corresponding `_3.jpg`: the manager lists GAP LEFT and GAP RIGHT.
- The `67a3cbf..._4_*.png` and `2_dl.mp4_*.png` frame sequences: visual line
  geometry, without a memory trace. No match was run or witnessed by this job.

## 1. What the instruction actually is

`PLAYBOOK_MASTER.IFF`, outer 180 in this retail archive, filename ID
`33CDF8E3`, contains `mpb` / `PLAY`, body size `0x2C750`. SPLB books contain
membership and call metadata referencing this shared MASTER. They do not each
hold a separate copy of Base's rush nodes.

DRCT is a different director graph. Its read-only inspector does not identify
a DL technique enum. See [director_format.md](director_format.md). The generic
capability-matrix PLAY/DRCT row is insufficient to describe the later PLAY
codec and writers; use [apf_play_format.md](apf_play_format.md).

MASTER play records begin at `0x80C4`, stride `0x64`. Each has name pointer
`+0`, flags `+4`, features `+8`, then eleven eight-byte assignments at `+0x0C`.
Each assignment has a descriptor and a relative node pointer. Resolve the
pointer as `pointer_field - 1 + signed_stored_value`. Descriptor high nibble
is node count; `descriptor & 0x800` selects ownership in defensive composition.
Neither flags nor features alone identifies Base, Pinch or Gap.

For the visible **retail** 4-3 Base label, the matching play is 277 at
`MASTER+0xECF8`, formation 141 (4-3) at `MASTER+0x679C`. This is a decode of
the retail counterpart of the screenshot, not a dump of the tester's runtime
play. Another Base exists in 3-4 and must not be substituted for this record.

Base flags are `11400000`, features `00001000`. Slots 0..3 own the front;
slots 4..10 do not. All four front chains start with opcode `1B`
(`DefenseStart`, packed `80400000`) then opcode `0B`, flags `60`.

| Slot | Descriptor | Pointer field | Stored pointer | First node offset | 0B packed word | Mode | Lane |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | `2210B800` | `ED08` | `0000EA2D` | `1D734` | `68000001` | 1 | 13 |
| 1 | `2210B800` | `ED10` | `0000EA35` | `1D744` | `18000001` | 1 | 3 |
| 2 | `2220B800` | `ED18` | `0000EA3D` | `1D754` | `48000000` | 0 | 9 |
| 3 | `2210B800` | `ED20` | `0000EA45` | `1D764` | `28000001` | 1 | 5 |

All offsets in that table are relative to the decoded MASTER body. The rush
node is eight bytes after the listed first node. Opcode `0B` stores mode in
bits 0..3, lane in bits 27..31, delay in bits 4..9 (tenths); delay is zero in
these chains. Lane mirroring is `16-lane`, with sentinel 17 unchanged.
The native reader proves these numeric operands. Do not rename mode 0/1/2
as Base/Gap/Pinch. Opcode `1C` is APF's separate dual-lane assignment, with
different packing from NFL 2K5.

| 4-3 component | Play | Flags | Modes, slots 0..3 | Lanes, slots 0..3 |
| --- | --- | --- | --- | --- |
| Base | 277 | `11400000` | 1,1,0,1 | 13,3,9,5 |
| Razor Left | 279 | `11480000` | 1,1,0,1 | 14,4,10,6 |
| Razor Right | 280 | `11480000` | 1,1,0,1 | 12,2,8,4 |
| Fan | 284 | `11500000` | 2,2,1,1 | 14,2,10,4 |
| Pinch | 285 | `11500000` | 1,1,0,0 | 13,3,8,7 |
| Gap Left | 288 | `11500000` | 2,1,1,1 | 15,5,11,7 |
| Gap Right | 289 | `11500000` | 1,2,1,1 | 11,1,7,3 |

Full descriptor/node decode and retail book membership:
[retail_dl_decode.json](../../reports/b75_a1/retail_dl_decode.json).
Retail USER-d's 4-3 membership excludes 288/289; X-43Cover2 includes them.
That does not remove their nodes from MASTER. Saved book overrides also mean
the manager list alone cannot identify the runtime source book.

## 2. Writer and runtime-option audit

| Writer/option | Actual scope | Evidence and limit |
| --- | --- | --- |
| Situation mask | XEX call-draw hooks, reserved code/data; no MASTER writes | Category/form guards exclude defensive rows. Identical DL native results with patch installed. |
| Personnel comparison row | Changes local comparison-row register at `8486B090` on BASE | `_row_leaf` bypasses requested or category row above 10, plus other guards. No assignment writes. Identical DL native results. |
| Fourth-down triggers | Specific constant-load sites plus reserved block/trampoline | `apf2k8_fourth_down.SITES`; not a rewrite of shared source constants or DL nodes. Identical tested DL native results. |
| Assignment-route writer | Explicit target descriptor and relative pointer | Cloning Gap Left slot 0 onto Base slot 0 changes that requested assignment. It can alter DL data when explicitly asked; it does not globally rewrite fronts. |
| Formation alignment writer | Formation geometry and slot-order lists | Explicit 4-3 slot 0/1 swap changes MASTER geometry, with zero changed defensive records/chains. Geometry can still affect runtime behavior. |
| O-ManBlock export | Changed named SPLB allocations; MASTER only if state.master changes | Production `playcalling_build.finalize` test below leaves all defensive resources unchanged. |

The controlled archive test copied retail packs into
`/tmp/b75-a1-controlled-game`, then used the real production backend, apply,
recipe validation and finalizer. Requests, in order: O-ManBlock automatic
audibles; exclude formation 14 for key 8; category 6 comparison row 10 for
key 8; enable situation masks. No writer was mocked. The finalizer exported
both situation-patch profiles and verified archive bytes outside its changed
resource allocations.

- O-ManBlock SHA changed from `18de1e3ee886aceba6535be2c8472d0af3f5554f8c9023d553068005416dd1f5`
  to `3142d1380fd60bd2097f1a7f2567580793db588249dfecaced4b83897016e794`.
- MASTER retained its pinned SHA. All 266 defensive records and resolved
  assignment chains were unchanged.
- USER-d, X-34Base, X-34ZoneBlitz, X-43Blitz, X-43Cover2 and global-d retained
  their whole-body hashes. These cover the retail roster's shared defensive
  types plus USER-d/global-d, not every possible custom saved book.

The complete receipt is [controlled_export.json](../../reports/b75_a1/controlled_export.json).
This is a controlled export, **not the beta folder from the clips**. Arbitrary
other staged edits, custom saves, mismatched installs and other active patches
remain outside that proof. No situation weights, VIP or charged abilities were
changed or investigated.

## 3. Native runtime path

Addresses are guest VAs, not XEX file offsets. `M` is the defensive manager;
`D = [M+0x0C]`. `D+8` is formation, `D+0x10` and `D+0x14` are the two called
PLAY pointers. `P` is a player, `R = [P+0x28]+0x804` its assignment runtime.

| Boundary | BASE | TU 1.1 |
| --- | --- | --- |
| Per-player assignment initializer | `84800798` | `84801438` |
| Two-component assignment choice | `848006F8` | `84801398` |
| Store selected assignment at R | `84800060` | `84800D00` |
| Set current node index | `8482DA88` | `8482E728` |
| Integer operand reader | `8482DCA0` | `8482E940` |
| CPU/player rush lane resolver | `847F7208` | `847F7EA8` |
| Nearest lane from position | `847F6750` | `847F73F0` |
| Node decoder dispatch | `84A94098` | `84A95068` |
| Auto front-shift chooser | `8485A7D0` | `8485B470` |
| Apply front-shift selector | `8485EF28` | `8485FBC8` |

Initializer `84800798` loops the manager's player list, uses each player's
slot byte `P+0x36`, and obtains assignments from both called plays. At
`84800980..84800988` it invokes `848006F8`. The rule is:

- Same assignment pointer: keep first.
- Second descriptor owns the slot (`&0x800`): use second.
- Otherwise, a qualifying opcode-0 chain in second keeps first.
- Otherwise, use second only if first does not own the slot.

The native proof checks all 266 defensive plays as second component against
Base's four owned slots: 1,064 choices per configuration. It also checks all
eleven slots for Base with 2 Hard, 2 Man, Gap Left and Gap Right. Base + 2 Hard
or 2 Man retains Base in slots 0..3. Supplying Gap as the second component
selects Gap's owned front; that is evidence of composition priority, **not
evidence that a valid Base call supplied Gap as its second component**.

`84800060` stores the selected assignment pointer at R. `8482DCA0` searches
the actual chain via `8482DB10 -> 84A87820 -> 84A94098`, or uses cached operands
when the current opcode matches. Base/Fan/Pinch/Gap Left/Gap Right read back
their own modes and lanes, mirrored and unmirrored.

`847F7208` reads lane operand 1 and mode operand 0 from opcode 0B (0C fallback),
then considers design and actual lateral positions. Its control test is
`[[P+0x10]+0] == -1`; the constructed CPU player takes that branch. The CPU
branch bypasses the manual-player displacement cutoff. It calculates the
lane offset from the design position, applies it at the actual position,
handles parity and clamps to 0..16. It never looks up a play named Gap.

For the explicit fixture with design X=0 and actual X=0, Base resolves to
`[13,3,9,5]`. With actual X=+152.4 it resolves to `[15,5,11,7]`; with X=-152.4,
`[11,1,7,3]`. Those are the named Gap lane vectors, but Base's modes remain
`[1,1,0,1]`. These are constructed position inputs, **not recovered positions
from the clips or a complete 4-3 formation simulation**. This provides a
testable explanation for an apparent Gap front without book membership,
while leaving the reported trigger unresolved.

### The separate automatic table

There is an automatic front adjustment system. `8485A7D0` indexes six-float
rows at BASE `820B8CC8` / TU `820B8CE8`, using a classifier result and offensive
strength-side input. The 432-byte table SHA is
`fd6ad56963f229bad3008da92c27d3fd05ac96a8f2b47e2b649fafae7ed1c547` on BASE.
The native chooser consumes a random fraction and returns a shift selector
0..5. Class 0 always returns 0; for class 1/balanced input the distribution is
30/30/20/20/0/0 percent. The full 18-row sample is in the native receipt.
These class and selector IDs are not established Base/Gap technique names.

`8485EF28` stores the selector at `D+0xC4`, uses table `84DBB218`, and changes
bits 6..7 of `R+4` before refreshing player alignment. It does not replace R's
assignment pointer. The defensive-start positioning function `847CEB68`
reads `D+0xC4` at `847CEC14`; a nonzero selector bypasses the original 1B
coordinate operands there. A newly committed call at `8485F940` clears
`D+0xC4` at `8485F980`.

The main automatic entry points `848667D8`, `848668C8` and `84867EF0` check
`M+0x38 == 0`. All three return before the chooser in the native human-team
fixture (`M+0x38=1`), even with an otherwise eligible pre-snap state. The
additional helper `84866860` has no local manager guard, but its direct
callers in `8485FAC0` pass the opponent-manager guard at `8485FB9C..8485FBB0`.
Manual command handler `84884C40` also calls the shift writer. Thus finding
this table is not proof of an unconditional CPU-lineman override on a human
defense. Team control and individual player control are different checks.

## Native proof scope and rerun

[apf_dl_instruction_probe.py](../../tools/apf_dl_instruction_probe.py) reuses
the existing Unicorn PPC instrument. Only assignment pointers are relocated
by the fixture; it does not claim native MASTER initialization. Instruction
adapters and their PCs are recorded. Assignment choice, node search/decode,
lane resolution, human-team bypasses and the weighted table chooser execute
native instructions. RNG, the shift classifier, and the design-position
provider are explicitly supplied callee boundaries. No full alignment update,
collision solver, match, or Xenia execution is claimed.

[native_proof.json](../../reports/b75_a1/native_proof.json) records four runs:
BASE and TU, each retail and with situation masks, personnel rows and fourth
down installed. The comparisons cover 1,064 front ownership checks, 44 full
pair choices, 80 mode/lane operand reads, 48 CPU lane resolutions, three
human-team guard calls and 1,800 shift draws per configuration. The patch
configuration uses all twelve O-ManBlock keys excluding formation 14, category
6 row 10, and fourth-down short cutoff 3 / own-half limit 75 / fallback 1.

```bash
APF_RETAIL_PE=/path/to/base.pe APF_TU_PE=/path/to/tu.pe \
python3 -m pytest -q -p no:cacheprovider \
  tests/mod_editor/test_apf_b75_dl_instructions.py

python3 -m tools.apf_dl_instruction_probe \
  --retail-index '/path/to/retail/0A' \
  --built-index '/path/to/tester-game/0A' \
  --pe /path/to/base.pe --output /tmp/dl-report.json
```

The second command reads the actual built MASTER and defensive book hashes;
it does not pretend its retail native fixture executes that built MASTER.
Images must match a pinned profile. Optional native tests skip if owned
inputs or Unicorn are missing. Synthetic tests verify that shared-node edits
are detected even when the assignment record bytes are unchanged, and that
route/alignment writer ownership is respected.

## Closure path and patch gate

There is no justified production fix yet. Do not zero the auto table or force
all linemen to a literal lane: that would change valid CPU front adjustments
or position-relative behavior without proving the tester's cause.

First compare the actual tester folder with the command above, and record its
executable profile and active patch files. For one failing Base call, capture:

1. At call commit and before `84800798`: `M+0x38`, `D+8`, `D+0x10`, `D+0x14`,
   `D+0x2C`, `D+0xC4`, and the resolved book identity.
2. For each DL at `84800060`: `P+0x36`, selected assignment pointer, descriptor
   and chain hash; then verify the stored R pointer.
3. Watch writes to `D+0xC4`, R and `R+4`, retaining the writer PC. At the rush
   resolver, record the design-position provider result, actual X at
   `[P+0x1C]+0x30`, control value, 0B modes/lanes and resulting lanes.

Use the table above for TU entry points. The operand/position boundary in the
probe must be replaced with captured values before calling it a reproduction.

If the archive comparison finds a writer-induced DL mutation, limit the fix
to that writer and replay its exact staged recipe; require all unrelated
defensive chains and archive allocations to remain identical. If the call
tuple is already wrong, investigate its committer, not the operand reader.
If the tuple/chain is Base but alignment moves it, prove the specific shift
writer or positioning branch using captured state before considering a pinned
BASE/TU runtime hook. Extend `test_apf_b75_dl_instructions.py` with that failing
state and preserve valid CPU-team shifts, manual commands, mirrored fronts and
position-relative lane behavior. Xenia retest by Urianus remains required.

Validation completed with **61 passed, 2 subtests passed** across
`test_apf_b75_dl_instructions.py`, `test_apf2k8_playbook_route_writer.py`,
`test_apf_formation_alignment_writer.py` and `test_apf_b69_build.py`.
The controlled retail archive finalizer also passed independently.
Shared Git metadata was read-only; the import bundle is
`.scratch/b75-a1.bundle`, with commit identity in `.scratch/b75-a1-commit.json`.

Deliverable status: data format settled; controlled writer scope and bounded
runtime behavior proved; actual beta-folder comparison and reported cause
still open. This report supplies a bounded capture/fix decision plan rather
than labeling an unproved hypothesis as a fix.
