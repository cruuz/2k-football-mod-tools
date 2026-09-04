# Practice squads — experimental beta-60 handoff

Built **53 active + up to 12 reserves**. The requested 16-index tail format
is disproved: `+0x19C..0x1A9` holds future cap accounting (`0x13ECA0`,
`0x13ED30`), and `+0x1AA..0x1F1` holds live statistics (`0x134DD0`,
`0x127C90`, reset `0xC3F60`). A bounded reset destroys the proposed indices.
This rules out that storage plan, not a future redesign of the save format.

The permitted fallback uses the existing 65 pointer fields: active players,
then 0–12 reserves, then NULL. Only padding bytes `+0x19B` (version 1),
`+0x1F2` (count), `+0x1F3` (marker A5) are repurposed. Legacy metadata is
all zero. Every pointer uses retail field-relative save encoding and all-65
relocation; no saved absolute pointers or mutable `.text` state.

## PROVED locally

- Atomic, pinned `status/apply`, idempotence, conflict refusal and repaired XBE
  section digests. Freestanding C/assembly rebuilds reproducibly into the
  checked-in Python payload; private executable bytes are not committed.
- Bounded retail execution with read-only `.text`, balanced stacks and
  preserved callee-saved registers: demote/promote, capacity/ownership refusal,
  CPU 65→53 season cuts (`0x2BFAA0`), full save/reload (`0xC0730/0xC0500`),
  unchanged rating (`0xC46B0 -> 0xC4400`), clear/reuse (`0xE64D0`), draft
  allocation (`0x2BD390`), actual draft signing (`0x325B50`), and complete
  rollover (`0x247B40`, including `0x31E210` and `0x2BD380`). Surviving reserves
  gain experience; retired references are removed.
- Complete single/two-team export and single-team import (`0xC0B90`,
  `0xC0FA0`, `0xC1030`). Twelve reserves remap into new primary slots and the
  source is restored byte-for-byte. Insufficient capacity/busy destination
  fails before mutation. Both preserved real version-0 franchise fixtures
  retain reserves through serialization, EXTRA signing, and reload, with
  opaque framing/suffix and original source files preserved.
- IR transfer retains ownership on failed insertion. Signing guards run
  before FA/draft ownership changes; trade preflight refuses insufficient
  temporary capacity. Draft limits include hidden physical slots.
- Both mandatory XBE gates pass, including composition with existing patches.
  A stricter scan finds zero external references into the four runtime caves,
  including entries and unaligned callback pointers. The combined-patch CPU
  gate/save/reload also executes successfully. Details: [audit ledger](tools/practice_squad/AUDIT.md).

## HYPOTHESIS / deliberate beta limits

No xemu, GUI, audio or in-game witness was used. Native roster/depth-chart
loops retain the active count; no reserve list or label is added in game.
CPU excess season cuts populate reserves automatically; no automatic
promotion or replacement filling is added. Human reserve management awaits
Claude's Rosters integration; Python storage APIs and runtime transactions
are supplied. The native season-limit message now says 53.

Reserves cost **zero current cap space** and keep frozen contract terms until
promotion; existing dead-cap accounting is preserved. A team has 65 physical
slots total even off-season: active players must be released to make draft
room when 53+12 is full. Imports require an empty destination. Trades needing
a temporary extra slot are refused before mutation. Full UI signing/trade
dialogs, an entire generated rookie class, postgame simulation and every
computed pointer alias remain unwitnessed; static scans do not prove those.
Use this XBE with reserve-bearing saves: unpatched append/removal code does
not understand hidden ownership. Fantasy re-drafting a loaded reserve-bearing
franchise has not been validated.

## Validation and handoff

Run from this worktree:

```sh
python3 tools/practice_squad/build_runtime.py --check
env -u DISPLAY QT_QPA_PLATFORM=offscreen python3 -m pytest -q tests/mod_editor/test_nfl2k5_practice_squad.py tests/mod_editor/test_nfl2k5_save_rost.py tests/mod_editor/test_xbe_patch_memory_writes.py tests/mod_editor/test_xbe_patch_cave_references.py
python3 tools/practice_squad/audit.py --output /tmp/astra-practice-squad-audit.json
python3 packaging/repin.py --apply
```

Final result: **40 tests passed, 28 subtests passed**; reproducible runtime;
zero external cave references; **0 pin updates**. Private inputs and optional
Unicorn/Capstone have precise skip reasons on machines without them.

The private patch-only build and receipt are in
`/tmp/astra-practice-squad-build/default.xbe` and `receipt.json`; the separate
`combined-gate.xbe` is a composition test artifact, not a disc build. No ISO
was changed. [WIRING.md](WIRING.md) gives exact additions for Claude's protected
build, preset, GUI and packaging files; those files and release pins remain
untouched. Commit contains only explicit implementation/test/document paths;
the supplied `ASTRA_BRIEF.md` remains untracked. No push.

## Noah's in-game checklist

1. Start a copied franchise, carry 65 active players to the CPU season gate,
   and confirm 53 active plus up to 12 owned reserves in an inspected save.
2. Play/simulate games: verify depth charts, dressing, rating, statistics and
   cap screens; ensure reserves do not appear as free agents.
3. Save, quit and reload. Inspect the signed save for the same identities;
   repeat on both new and existing franchises.
4. Advance a season: inspect surviving/retired reserves and experience, cap,
   IR returns, and draft room. Test a full 65-slot roster and one free slot.
5. Import an exported team into an empty slot; verify all reserve names.
   Test blocked full-roster signing/trades and a trade with spare capacity.
6. After the Rosters controls are wired, test demote/promote at 52/53 active
   and 11/12 reserves; refused actions must retain the original owner.
