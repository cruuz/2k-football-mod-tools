# Storage and transaction audit

The source is the hash-pinned US retail executable. Addresses are virtual.
This ledger records the reviewed paths and the boundaries of the proof; the
read-only disassembly corpus and private fixtures are not copied into Git.

| Region/path | Observation and disposition |
| --- | --- |
| Team `+0x000..0x103` | 65 pointer fields. Both team relocators (`0x2418C0`, `0x241A20`) process all 65 regardless of active count. Serialized NULL is 0; other words resolve as `field + signed_word - 1`. No saved absolute pointers. |
| Team `+0x11C` | Active count remains the boundary used by roster/depth-chart consumers and rating (`0xC46B0 -> 0xC45A0 -> 0xC4400`). No reserve index is put into a depth-chart slot. |
| Team `+0x19A` | Existing byte accessors `0xBF3B0/0xBF3C0`; preserved. Initial zero is not free-space evidence. |
| Team `+0x19B` | Alignment padding before the word array; version byte. |
| Team `+0x19C..0x1A9` | Seven words used for future cap accounting. Accessors `0xBF3D0/0xBF3E0`, `0x13EB20/0x13EB30`; cap lookup `0x13ECA0` and adjustment `0x13ED30`. Preserved, including existing dead-cap accounting. |
| Team `+0x1AA..0x1F1` | Live team statistics. Reset `0xC3F60`, result accumulation `0x134DD0`, assignment `0x127C90`, display/read `0x58330`. A proposed 16-index side-list is overwritten by the reset and aliases future cap words. Preserved. |
| Team `+0x1F2/0x1F3` | Final alignment padding; count and marker. Exact-displacement writes `0x398CDE/0x398DC8` belong to a codec object, not team records. Width-overlap candidates include stack slots, floating-point structures and SDK objects. No identified team writer uses these bytes except record copy/relocation. |
| Root save/load `0xC0730/0xC0500` | Full disc and version-0 save arenas round-trip. Root primary allocation does not move player identities during these routines. All 65 team pointers relocate, so moving the arena preserves targets. |
| Remove `0xC3EB0 -> 0xC3AB0` | Patch the inner compaction to move through slot 64 and clear that last slot. Removing an active player now preserves the contiguous reserve tail. Retail depth-chart maintenance remains in the original routine. |
| Append `0xC3EE0` | Validate format and physical capacity before insertion; shift reserves to make an active slot. Refuse reserve theft. Regular-season active cap is 53. Off-season capacity is `65 - reserve_count`. |
| Season gate `0x2BFAA0 -> 0x2BFA00` | Capture the actual cut callback at `0x2BFA6E`. At phase 7, cuts above 53 demote until 12 reserves; otherwise ordinary `0x2BD900` release. CPU and human threshold sites become 53. The user-facing maximum-54 string at `0xE892B6` becomes 53. |
| Rollover `0x247B40` | Reserve retirement uses the original decision at `0x2BCF90`, then removes retired references and marks retired bit 8. The complete original rollover still executes, including `0x31E210` (draft order), `0x2BD380` (live-player predicate), stats reset, contract loop, and player experience loop. Surviving reserves gain years-pro via `player+0x24` bits 8..12. |
| IR return `0x246F90` | Retail clears the IR owner after ignoring append failure. Hook `0x246FB6` makes insertion and IR clearing conditional on success. At physical capacity the player remains on IR. |
| Draft allocation `0x2BD390 -> 0x2BE900 -> 0x2BE6F0` | Allocation skips live bit 4; reserves keep it. `0xE64D0` purges reserve references before record clear/reuse. The allocator and clear path execute in tests; the full rookie generator is statically inspected, not run. |
| Team size/export `0xBFC30`, `0xC0B90`, `0xC0FA0` | Expand the source active view only while the complete retail exporter runs, then restore it. Size includes reserve records and names. Retail's 65-entry college-ID stack remains large enough. One- and two-team exports are tested. |
| Team import `0xC1030` | Preflight a compact single-team source and enough free primary slots; require an empty destination. Temporarily include reserves in the active view, execute the complete retail import, restore active/count metadata, serialize the source again, and restore its college IDs. Destination pointers are remapped by retail copy allocation. Source returns byte-for-byte unchanged. |
| Pool compaction | Import/export compaction is covered above. An external reorder must remap every active/reserve pointer; the Python helper refuses incomplete identity maps. No claim that an arbitrary future third-party compactor understands this format. |

## Append caller review

All nine direct callers listed for retail `0xC3EE0` were inspected:

- `0x246F90`: conditional IR transfer described above.
- `0x2A5E80`: fantasy-draft roster reconstruction. It clears/rebuilds active
  lists and relies on upstream selection. A new fantasy franchise has no
  reserves; rebuilding a loaded reserve-bearing franchise through this path
  has not been executed and is outside the witnessed claim.
- `0x2B8310`, `0x36F830`: roster move/manual FA screens have 53-player checks
  patched before their destructive ownership changes.
- `0x322BB0`: CPU signing now checks capacity at entry, before FA removal.
- `0x323B30`: pending CPU offer acceptance now checks capacity at entry.
- `0x323D80`: the existing early offer-limit check now uses `65 - reserves`
  off-season and 53 in-season; existing contract-renewal logic stays intact.
- `0x325B50`: draft signing checks capacity before changing the draft owner.
  CPU draft selection at `0x325B9E` and human draft limit at `0x3269DF` use the
  same physical-capacity calculation. A full physical roster cannot add picks.
- `0x2BC670`: trade entry simulates retail's sequential removals/appends first.
  If a temporary intermediate roster would exceed capacity, the whole trade
  returns failure before changing either owner, even if its final net counts
  would fit. This beta does not reorder retail's trade execution.

Promotion rotates an existing hidden pointer into the active list, then drops
the reserve count only after successful insertion. Demotion verifies a single
active owner, no competing active/FA/IR/reserve owner, available reserve space,
and a primary player identity before calling retail removal. Both recalculate
the current cap with `0xC3F00`. These runtime operations preserve callee-saved
registers and stack balance in bounded execution.

## Static scan limits

`audit.py` checks byte-granular rel32 branches, all unaligned text dwords,
aligned pointer tables in every section, and decoded immediates including
short branches. Cave entries are included. It additionally reports unaligned
non-text dwords as possible pointers, independently of the aligned-table gate.

### Relocation from the kickoff cave

`0x2890F0..0x289883` now belongs exclusively to dynamic kickoff. The original
practice-squad builder listed five available spans but emitted code into four;
the fifth (`0x3BABE0`) was unused. No single remaining function large enough
to replace the kickoff span passed the conservative reference scan. The
unchanged C/assembly was repacked, with complete functions kept together:

| Start | Exclusive end | Pinned capacity | Generated bytes | Allocation |
| --- | --- | ---: | ---: | --- |
| `0x374111` | `0x37439C` | 651 | 650 | Retained |
| `0x3BA610` | `0x3BA860` | 592 | 589 | Retained |
| `0x3DCB20` | `0x3DCC9D` | 381 | 380 | Retained |
| `0x3BABE0` | `0x3BAD2D` | 333 | 330 | Previously offered, now used |
| `0x3D1E20` | `0x3D1F5F` | 319 | 317 | Two adjacent unreferenced functions; includes one alignment byte |
| `0x3E1600` | `0x3E16E1` | 225 | 225 | New |
| `0x3E81B0` | `0x3E824E` | 158 | 157 | New |
| `0x3EE0D0` | `0x3EE162` | 146 | 146 | New |
| `0x2EAEE0` | `0x2EAF6F` | 143 | 143 | New |
| `0x3D1610` | `0x3D169E` | 142 | 136 | New |
| `0x2952B0` | `0x29533C` | 140 | 127 | New |

Every capacity is SHA-256 pinned in `CAVE_PINS`; trailing bytes are NOP fill.
All runtime symbols and inter-cave branches are regenerated. In particular,
`count/listed/owner` move to `0x3D1630/0x3742FC/0x3BAC64`. The payload uses
3,200 generated bytes in 3,230 pinned bytes. No storage-layout or runtime
C/assembly behavior changed.

The exact new spans have **zero external references**, including unaligned
dwords in every section. The byte scan, decoded branch/immediate scan and
the oracle's raw-reference pass cover the entries as well as the interiors.
Function names/bounds from the read-only Ghidra corpus were candidate hints,
not allocation proof. Boundary disassembly shows prior returns at
`0x3D1E0E`, `0x3E15F9`, `0x3E81AD`, `0x3EE0C9`, `0x2EAED7`,
`0x3D1600`, and `0x2952A6`, followed by alignment padding. The first new
span comprises `0x3D1E20..0x3D1EBF` and `0x3D1EC0..0x3D1F5F` plus
the intervening byte; it stops before the next function at `0x3D1F60`.

The oracle reports three speculative external short-branch encodings in the
new spans. Each is inside an instruction, not at its decoded boundary:

| Raw source → target | Containing retail instruction | Disposition |
| --- | --- | --- |
| `0x3E15E4 → 0x3E165A` | `0x3E15E0`, five-byte `mov eax, 0x7fffffff` | Immediate byte, no branch |
| `0x2EAEBF → 0x2EAF09` | `0x2EAEBE`, three-byte `mov [ebp+0x48], edi` | ModR/M byte, no branch |
| `0x2EAFDC → 0x2EAF68` | `0x2EAFDB`, two-byte `jmp 0x2EB05C` | Displacement byte; actual jump goes outside the cave |

Across the retained spans, the additional unaligned non-text scan reports
`0x9F5B25 → 0x3BA7B2` and `0xAF4AA7 → 0x374200`. These were not in the
old aligned-table gate and remain **possible-pointer uncertainties**, not
demonstrated retail pointer uses. They are not silently filtered from the
JSON report. The relocation brief permits retaining those spans after checking
stack ownership; both are unchanged by the actual pre-practice-squad stack.

### Stack reservations and oracle limits

The supplied reservation manifest has SHA-256
`b3f373fef16657ba2e29c01af0df9a7667d6e8671ac1d6c7720d3de12652ae0e`.
It predates seven rebased sources (`mod_build`, `edge_rename`,
`formation_play_writer`, `modern_positions`, `position_pools`,
`roster_records`, `throw_tuning`) and contains no dynamic-kickoff reservation.
As explicitly permitted by the relocation brief, `audit.py --oracle` and the
cave gate load it with `source_root` unset. The manifest and oracle drift
enforcement remain unchanged; the audit records every drifted path.

All eleven capacities have zero overlaps with that manifest. The gate also
applies the current `_apply_all(..., dynamic_kickoff=True)` and pools/rows,
then compares each complete practice-squad capacity with retail **before**
applying practice squads. This independently covers rebased stack writes and
verifies kickoff's full cave remains byte-for-byte unchanged afterward.
The kickoff/practice-squad order test compares both final executables, patch
statuses, idempotence and section digests. The combined CPU season cut and
save/reload runs in Unicorn with read-only `.text`.

The recorded oracle run processes 2,782,776 references (budget 6,000,000,
not exhausted) and 250,000 instructions (budget exhausted), with 176,300
unresolved cases. All eleven verdicts are **unknown**, with zero reserved or
definitely reachable verdicts. Indirect transfers, imported code and computed
memory accesses prevent a closed-world proof. An earlier 4,000,000-instruction
probe also exhausted its budget; increasing the budget does not eliminate
those semantic unknowns. No oracle `allocatable` result is claimed.

Reproduce the evidence with:

```sh
python3 tools/practice_squad/build_runtime.py --check
python3 tools/practice_squad/audit.py --oracle --output /tmp/astra-practice-squad-relocated-audit.json
```

The separate mandatory repository gates pass with kickoff and the current
patches combined. Full relocation validation: **57 tests passed, 115 subtests
passed**, no skips; reproducible runtime; **0 packaging pin updates**.

The sweep decodes 1,627,402 instructions and produces 1,889 tail displacement
candidates, including 100 padding-width overlaps. These counts include other
object types and stack arrays. It cannot discover every computed alias,
indirect callback or execution path. The three metadata bytes are supported
by the identified team field layout, zero metadata in every team in the disc
and both real save fixtures, and the executed lifecycle; perpetual safety in
all game modes remains a playtest hypothesis. No mutable variable or flag was
allocated in `.text`; runtime state resides in the roster arena or stack.
