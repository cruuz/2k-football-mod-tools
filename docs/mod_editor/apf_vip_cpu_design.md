# APF CPU VIP assignment: native path and proposed team mapping

Research status: **PARTIAL**. The native opponent-profile attachment path is
proved offline on pinned BASE and TU 1.1. A per-team feature and actual motion
playback are not implemented or witnessed. This document is a design, not an
installable patch. See [the save field map](apf_vip_format.md) for decoded input.

## What the executable already does

The profile manager has eight ordinary loaded slots plus four extra slots.
Each has a `0x1410` primary record and `0x3BD8` supplementary record. The saved
`.USR` is those two records concatenated. Supplementary data contains the
playback input; copying only the primary profile cannot reproduce a VIP.

| Item | BASE | TU 1.1 |
|---|---|---|
| Primary bank | `0x85065D90` | `0x85065DA0` |
| Primary stride | `0x1410` | `0x1410` |
| Supplementary bank / stride | `0x84EB2D48` / `0x3BD8` | same |
| Opponent/viewer binding table | `0x84D4F0C0`, two `(tag, pointer)` rows | same |
| Binding getter | `0x8476DC10` | `0x8476E1D8` |
| Primary pointer to slot index | `0x847644D8` | `0x84764AA0` |
| Slot to playback pointer | `0x84AE7258` | `0x84AE8228` |
| Attachment initializer | `0x8492F8C0` | `0x84930788` |
| Session side rows | `0x850F1218`, `0x850F1260` | `0x850F1248`, `0x850F1290` |
| Initial side playback pointers | `0x8519A820`, `0x8519A824` | `0x8519A850`, `0x8519A854` |

The two binding rows are tagged profile purposes, **not** a home/away or
per-team table. Tag 0 is consumed by match initialization. Tag 1 is consumed
by the VIP profile viewer (`BASE 0x84A6B510`). The initializer calls the tag-0
getter, determines the selected slot, and obtains supplementary bank plus
`slot * 0x3BD8 + 0x1228` as its playback pointer.

Native initialization installs that pointer on the CPU side only when the
session side flags at row `+0x38` differ. The no-binding, two-human and two-CPU
cases leave both initial pointers zero. The opposite side selection works
symmetrically. Thus the game already has a route to attach a loaded profile to
a CPU opponent, matching Urianus's reported quickplay behavior. This bounded
proof does not establish availability or behavior in Season.

After this prefix, `BASE 0x8492F238` performs mode-specific selection and copies
`0x29B0` playback bytes into private side storage, then stores the result at
session row `+0x24`. Static disassembly of `0x8492F188` shows a nonzero playback
flag at the side's playback context `+0x1B4` makes its detail pointer use that
context `+0x28C8`;
otherwise it follows the native default. These later routines were **not**
executed by the attachment-prefix probe. They can clear or replace the pointer,
so bypassing only the initial two-CPU restriction is insufficient proof of a
CPU-vs-CPU or Season patch.

A separate 33-entry ID lookup (`BASE 0x8467D7B0`, setter `0x8467D7C8`) resolves
IDs to loaded profiles through `0x84765690`. Its indices are associated with
other session objects in adjacent code; **a per-team identity is unproved**.
It must not be exposed as a 33-team VIP assignment table.

## Reproducing the bounded proof

Use an owned decoded image; this tool refuses every image except the two full
retail pins. It runs 16 synthetic session cases per profile and writes only a
new receipt. Unicorn is a developer probe dependency, not a Studio dependency.

```sh
python3 tools/apf_vip_runtime_probe.py --image /path/to/owned/base.pe \
  --output /new/path/vip-attachment.json
```

Actual d4 result: 32 cases across BASE/TU, four unittest tests passed, zero
skips. Native profile selection, index arithmetic and pointer stores execute
unchanged; only the shared Xenon GPR29..31 save thunk is adapted for Unicorn's
PPC32 core. Execution stops before mode setup, and uses synthetic session flags.
No game/save bytes are emitted, and no emulator was launched.

## Proposed per-team feature

1. Keep each team's association in an explicit Studio-owned recipe containing
   a stable roster/team key, VIP source hash and supported image profile. First
   prove how that team key reaches both runtime side rows across roster reloads,
   custom teams, Season and quickplay. The current evidence does not establish
   such a key or a native persistent per-team VIP field.
2. Import both native records through the established loader, preserving their
   ID and opaque data. Load only the active teams' profiles into reserved slots
   or validated new storage; eight ordinary slots cannot hold forty profiles
   at once. Extra slots have native lifecycle ownership and cannot be borrowed
   without proving their allocation/release path.
3. At match setup, resolve each side's team key to its selected profile and let
   the mode-specific setup create its private playback copy. Hook locations
   must be selected after tracing the mode guards, later resets and default
   fallback. Preserve human controller input and existing quickplay selection;
   absent/invalid profiles must use the native default.
4. Export separate pinned BASE/TU Xenia TOMLs only after full-width ABI,
   writable-storage, reservation, exact-scope and revert checks. Respect
   `data/apf2k8/patch_reservations.json`, including d3's charge latch and
   situation-weight owners. No cave or writable region has been reserved here.
5. Prove two teams retain independent private copies; then test motion,
   formation flips, adjustments and actual play selection. Test profile changes,
   new games, Season progression and CPU-vs-CPU. Only a gameplay witness can
   establish that the profiles affect football behavior.

No forced-pointer patch ships in d4: the later mode and lifetime guards remain
unproved. A real-Xbox VIP would help verify the signed outer-container route;
it is not needed to make the supplied Xenia payload readable. Controlled
before/after saves and the in-game VIP tendency pages are more useful for
assigning names to the remaining motion/play/formation fields.
