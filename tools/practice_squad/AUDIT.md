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
short branches. Cave entries are included. The four occupied spans are
`0x2890F0..0x289883`, `0x374111..0x37439C`,
`0x3BA610..0x3BA860`, `0x3DCB20..0x3DCC9D` (exclusive ends).
No external reference lands in them. The separate mandatory repository gates
also pass with the existing patches combined.

The sweep decodes 1,627,402 instructions and produces 1,889 tail displacement
candidates, including 100 padding-width overlaps. These counts include other
object types and stack arrays. It cannot discover every computed alias,
indirect callback or execution path. The three metadata bytes are supported
by the identified team field layout, zero metadata in every team in the disc
and both real save fixtures, and the executed lifecycle; perpetual safety in
all game modes remains a playtest hypothesis. No mutable variable or flag was
allocated in `.text`; runtime state resides in the roster arena or stack.
