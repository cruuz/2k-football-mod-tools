# beta-63.1: catch-slider interception scaling no longer applies to kick returners

Implemented on `astra/hf63-catch-slider-kicks`, based on beta-63
`9c17c538847c4fc7511f127bae538f2c6bb5874a`. No push, xemu, GUI display, or audio.
Retail inputs were read only; no retail executable/disc fixture is committed.

## Reproduction and root cause

Read `ASTRA_BRIEF.md`, `HOTFIX_CONTEXT.md`, the supplied verification report's
“Separate interception-slider diagnostic,” and its probe/results. Added a
standalone regression before changing the writer:

```sh
PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_catch_slider_kicks.py -v
```

It enters retail `0x1C8312`, executes the installed `0x1C8317` RNG hook and
retail comparison, and stops at the native catch (`0x1C832F`) or deflect
(`0x1C834C`) branch. Only RNG is substituted. Inputs are explicitly supplied:
probability 1, no veto, opposite-team CPU catcher, both Catching factors 50,
ball kind 3 or 4, phases 2/4, and draws 0/0.05/0.5/0.99. `.text` is protected
read/execute during execution. These are deterministic decision counts, not
gameplay catch rates, approach/contact simulation, or an in-game reproduction.

Before the fix, the kick regression failed with this table. Each cell is
four draws times two phases:

| Installed patches | INT 0 | INT 25 | INT 50 | INT 100 |
| --- | ---: | ---: | ---: | ---: |
| Retail | 8/8 | 8/8 | 8/8 | 8/8 |
| Dynamic kickoff only | 8/8 | 8/8 | 8/8 | 8/8 |
| Catch-slider only | 0/8 | 4/8 | 8/8 | 8/8 |
| Dynamic kickoff + catch-slider | 0/8 | 4/8 | 8/8 | 8/8 |

Red output tail (`.scratch/hf63-catch-slider-red-fast.log`):

```text
kind=3 catch_slider_only: 0/8 | 4/8 | 8/8 | 8/8
kind=3 dynamic_and_catch_slider: 0/8 | 4/8 | 8/8 | 8/8
FAIL: test_kicked_ball_ignores_interception_at_native_boundary
Ran 2 tests in 9.813s
FAILED (failures=1)
```

Root cause: beta-63 `mod_editor/core/nfl2k5_catch_slider.py:92-115` uses only
`[catcher+0x38] != [0xE60280]` to classify a defender. A returner before the
possession swap satisfies that predicate. The cave returns
`rand / (2 * Interception)` without the native forward-pass guard. At INT 0,
positive draws become infinity and draw 0 becomes unordered; the native
comparison rejects both even against supplied probability 1. This establishes
a cause for the reported symptom when that slider is lowered; the reporter's
actual setting and a complete live-play reproduction remain unobserved.

## Retail instruction proof of the discriminator

The field is the dword at **`0xE602C0`**. Kind **4** is a forward pass;
kind **3** is a non-forward loose ball, including kicks and backward passes.
It is not an exclusive “kickoff” enum. The implementation uses equality to 3,
so kinds other than 3 keep their previous cave behavior. A phase-only test
would be wrong because punts and forward passes both occur in phase 4.

Instruction evidence from the read-only retail XBE:

```text
00222D01  E8 9A AF EB FF                 call 000DDCA0  ; kick launch release
000DDCCB  E9 40 2C FC FF                 jmp  000A0910
000A092D  E8 BE 77 01 00                 call 000B80F0
000B8110  A1 C0 02 E6 00                mov eax,[00E602C0]
000B8115  83 E8 02                      sub eax,2
000B8118  75 2D                         jne 000B8147   ; keep a forward pass (4)
000B811F  A1 B8 02 E6 00                mov eax,[00E602B8]
000B8124  83 F8 0E                      cmp eax,14
000B8127  74 14                         je 000B813D
000B813D  C7 05 C0 02 E6 00 03 00 00 00 mov [00E602C0],3

000B7410  C7 05 C0 02 E6 00 03 00 00 00 mov [00E602C0],3 ; kick/loose-ball setter
000B6705  C7 05 C0 02 E6 00 04 00 00 00 mov [00E602C0],4 ; forward-pass setter
000B6745  C7 05 C0 02 E6 00 03 00 00 00 mov [00E602C0],3 ; backward-pass setter

001C807D  83 3D C0 02 E6 00 04          cmp [00E602C0],4
001C8084  0F 85 AD 01 00 00             jne 001C8237   ; bypass native INT block
001C808A  8B 0D 84 02 E6 00             mov ecx,[00E60284]
001C8090  3B 4B 38                      cmp ecx,[ebx+38]
001C80C4  D9 05 0C 02 E6 00             fld [00E6020C] ; native INT, forward-pass path
001C8312  B9 A0 FC E5 00                mov ecx,00E5FCA0
001C8317  E8 74 08 E8 FF                call 00048B90  ; common RNG, patched here
```

The regression pins these native instructions independently of the emitter.
It also executes the unmodified `B80F0` release and its `B6DA0` callee in phases
2 and 4 with live state 14: kind 2 becomes 3; kind 4 stays 4. This is a bounded
native state-transition check, not a complete kickoff, punt, or onside replay.
Onside selection does not alter this ball-kind gate; the catch fix does not
add a playbook-type or phase predicate.

Ghidra corroboration under the supplied
`/media/noah/Storage/for codex 1.0/research/functions/nfl2k5/pseudo_c/`:

- `shard_003584_004095.c`: `FUN_000b6700`, `FUN_000b6740`,
  `FUN_000b73b0`, `FUN_000b80f0` (kind assignments and live release).
- `shard_004096_004607.c`: `FUN_000ddca0` (release-to-`A0910` chain).
- `shard_003072_003583.c`: `FUN_000a0910` (call to `B80F0`).
- `shard_008192_008703.c`: `FUN_001c78d0` (forward-pass guard and shared roll).

## Fix, allocation decision, and byte diff

The 48-byte main cave is completely full; simply inserting the selector would
overwrite scorebug floats at `0x10A40`. The chosen growth path uses the final
22 unused bytes of the same existing boot-logo bitmap, `0x10CAC..0x10CC2`.
The EDGE legend ends at `0x10CAC`, and the retail bitmap ends at `0x10CC2`.
No `.text` cave, XBE section growth, allocation request, runtime variable,
neighboring-owner edit, preset change, or protected dispatcher edit is added.
This layout is documented in the writer and pinned in `_sites()`.

`cave_bytes()` replaces just its five-byte offense-team load with a jump to
`kick_gate_bytes()`. The helper initially loads the original offense team.
For kind 3 it replaces that value with `[ebx+0x38]`, the catcher's own team,
then jumps back to the existing comparison. That comparison now selects the
existing Catching branch for kicked balls. Its controller load uses the
catcher's team, so CPU returners get CPU Catching and human returners get
Human Catching. Same-team recoveries take that branch too.

The RNG call and every arithmetic instruction in the main cave remain
byte-identical. Non-3 kinds return the original team to the original comparison;
the helper's flags are immediately overwritten. The helper adds no stack
operations and changes only EAX/flags. Kind-3 backward passes also receive
Catching rather than Interception, consistent with retail's non-forward guard.

Main cave, `0x10A10..0x10A40` (beta-63 authored bytes -> fixed authored bytes):

```text
before: e87b810300a18002e6003b433875168b50306a0459e8c6ae1600d8c0d8f9dbe9dbc1ddd9c3d9050c02e600d8c0def9c3
after:  e87b810300e9920200003b433875168b50306a0459e8c6ae1600d8c0d8f9dbe9dbc1ddd9c3d9050c02e600d8c0def9c3
```

Tail helper, `0x10CAC..0x10CC2` (retail bitmap pin -> new code):

```text
before: 034373a3d3f3e373130b03235347030749130749030d
after:  a18002e600833dc002e6000375038b4338e958fdffff

00010CAC  mov eax,[00E60280]
00010CB1  cmp dword [00E602C0],3
00010CB8  jne 00010CBD
00010CBA  mov eax,[ebx+38]
00010CBD  jmp 00010A1A
```

`status()` requires all five sites to match either retail or the exact new
installation. `apply()` replays an exact installation with unchanged payload
and `changed_bytes=0`; mixed, foreign, and old beta-63 installations are
refused. Old installed discs must be rebuilt from retail. The existing
`_apply_all` dispatcher already handles this new writer and its boot-logo
relocation; replay there was also byte-identical.

The new header-reference audit finds no foreign reservation, decoded absolute
operand, aligned data pointer, or bytewise relative-transfer target into the
22-byte helper. Raw unaligned code words that resemble header addresses were
inspected: they are instruction encoding fragments or relative offsets, not
absolute header references. The existing boot-logo relocation still handles
the kernel's boot-time bitmap read.

Retail SHA-256:
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
Catch-writer-only patched SHA-256:
`1a5ca969c9cf215af5174988d3212e5b4bbb10ac3682150e8278f1187d2ca51f`.
The writer changes **96 bytes** versus retail, including the recomputed
`.text` digest (section 0), without changing file length. All section digests
verify. This hash is the bare catch writer's result, before boot-logo relocation
or other preset patches.

## Verification

The new regression gives **8/8 in every kicked-ball cell** of the table above.
Forward-pass rows remain exactly the red table's counts. Additional cases
verify Catching 0/25/50/75/100/200 for human and CPU catchers on both sides of
the possession predicate, with a different opposing-side factor to expose
wrong-team selection. Existing forward-pass cave arithmetic tests remain green.
This preserves the existing Catching arithmetic, including its floating-point
edge behavior; the boundary table uses Catching 50, as explicitly stated above.

The shared Unicorn loader now merges adjacent mapped page ranges. It maps the
same file-backed pages while avoiding thousands of individual mappings per
draw. Existing `_run` callers retain their defaults; new arguments select ball
kind and the non-possession team's controller. The synthetic throw-tuning
fixture includes the new retail tail pin and checks zero-byte replay.

Completed standalone commands and output tails:

```text
$ PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_catch_slider_kicks.py -v
kind=4 catch_slider_only: 0/8 | 4/8 | 8/8 | 8/8
kind=4 dynamic_and_catch_slider: 0/8 | 4/8 | 8/8 | 8/8
kind=3 catch_slider_only: 8/8 | 8/8 | 8/8 | 8/8
kind=3 dynamic_and_catch_slider: 8/8 | 8/8 | 8/8 | 8/8
Ran 8 tests in 72.002s
OK

$ PYTHONPATH=. python3 tests/nfl2k5_catch_cave_emulation_test.py -v
Ran 3 tests in 1.007s
OK

$ PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/nfl2k5_throw_tuning_test.py
Ran 39 tests in 10.332s
OK (skipped=1)

$ PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_discord_bugs_1.py DiscordCoreTests.test_B7_PROVED_retail_catch_patch_replay_is_byte_identical -v
Ran 1 test in 0.738s
OK

$ python3 packaging/repin.py --apply
[1] mod_editor/core/providers.py: mod_editor/core/nfl2k5_catch_slider.py
    c69f022b6328abcb0dcb74fef277297ac6d6471a96790559ef43ecc7cae26abe
 -> 0ea12e1f558463538a154f50c38036389a8c0432c7ba55ac2862cd706b85498f
applied 1 pin update(s)

$ python3 packaging/repin.py
would apply 0 pin update(s)
```

The throw-tuning suite's one skip is its pre-existing private **patched disc
image** smoke test; the retail XBE tests executed. At this base the old catch
writer unit tests live in `tests/nfl2k5_throw_tuning_test.py`; the new standalone
regression supplies the requested `tests/mod_editor/test_nfl2k5_catch_slider*.py`
entry point. Full local logs are in `.scratch/hf63-catch-slider-final.log`,
`hf63-catch-cave-suite.log`, `hf63-throw-tuning-suite.log`,
`hf63-production-replay.log`, and the `hf63-repin-*.log` files.

Full XBE memory-write gate (`.scratch/hf63-memory-writes.log`):

```text
$ PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_xbe_patch_memory_writes.py
Ran 111 tests in 1164.867s
OK
```

Full XBE cave-reference gate (`.scratch/hf63-cave-references.log`):

```text
$ PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_xbe_patch_cave_references.py
Ran 123 tests in 1327.252s
OK
```

Both gates passed without skips, including normal and reverse installation
orders on both allocation layouts. `git diff --check` also passed. No test gate,
retail pin, or source-drift guard was disabled or relaxed for this fix.

## Protected-file handoff

`python3 packaging/repin.py --apply` was run and updated one integrity pin,
in `mod_editor/core/providers.py`. Claude must regenerate
`data/nfl2k5_cave_reservations.json`; it was not edited, per the supplied rules.
`WIRING.md` gives the exact span, source hash, and full regeneration command.
The release manifest's old image/source receipts are not being represented
as a fresh acceptance build. No other protected file needs a change.

## Exact xemu witness for Noah

1. Rebuild from the clean retail source with this hotfix, first Basic and then
   Advanced and Experimental. Do not patch an old beta-63 output in place.
2. In the game's Custom sliders set **Interception 0**, **Human Catching 50**,
   and **CPU Catching 50**. Keep teams, rosters, weather, and other settings
   fixed. Assign the controller to the kicking/punting team; the receiving
   team must remain CPU-controlled.
3. Kick a normal in-bounds kickoff that the CPU returner fields in the field
   of play. Observe the catch and start of the return, avoiding a touchback
   or an intentionally uncaught ball. Repeat for a punt with CPU fielding.
   **Expected: the CPU can secure the catches and return; INT 0 must not force
   every eligible kickoff/punt fielding attempt into the muff/deflect outcome.**
4. Repeat the matched kicks and punts at Interception 50. Changing only that
   slider should not impose the old deterministic rejection at 0. Include an
   eligible CPU onside recovery to check the same kind-3 route under its native
   recovery rules. Ordinary catch eligibility, contact, ratings, and animations
   still apply; this patch does not force every possible fielding into a catch.
5. Reverse controller ownership and use different Human/CPU Catching values
   (for example 100/50, then 50/100) to confirm each returner follows its own
   side. As a control, throw forward passes with INT 0 and 50: interception
   scaling and offensive Catching must retain their prior behavior.

Offline tests prove the selector, native decision boundary, patch composition,
and byte/ownership contracts. No full gameplay or xemu result is claimed.
