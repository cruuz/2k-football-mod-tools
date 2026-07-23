# APF 2K8 Mod Studio — universal text runtime result

Date: 2026-07-18

## Completed experiment and result

**Positive.** The bounded APF TXT/STRG writer produced a complete, separate
game folder in which English localization allocation
`apf:text-pool:1127:0:11` changed from `Artist Biography` to the
user-authored value `MOD BIOGRAPHY`. Xenia Canary booted that output. On the
2K Beats artist-biography page, Spark Hands read the centered header exactly
as **MOD BIOGRAPHY**. The biography body and portrait rendered normally, with
no visible corruption, missing textures, or layout damage.

This closes runtime consumption for that exact allocation and screen. It does
not claim that every other TXT/STRG allocation has been visited at runtime;
the product's remaining 2,409 editable allocations rely on the same bounded,
independently verified writer/build transport and retain their individual
fixed-allocation limits.

## Exact identities

| Item | Value |
| --- | --- |
| Untouched source `0A` SHA-256 before/after | `dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e` |
| Private project SHA-256 | `0f5912209b2660922ad4f17e5ef31ff6f5101c0404a2f969f359e77fbfab0c28` |
| Built output `0A` SHA-256 | `a7d98495fc60a85536cfd00cd000eb829218f83b2446b3bc63c6ca2967b0039c` |
| Built output `default.xex` SHA-256 | `981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f` |
| Changed outer entry | `1127` only |
| Visible target | outer `1127`, inner `0`, pool `11` |
| Runtime | Xenia Canary, title `54540807 v0.0.0.2`, isolated `DISPLAY=:99` |

The private project also retained the earlier pool-7 `SOUNDTRACK` ->
`MOD MUSIC` edit, so the build grouped two user replacements into one exact
outer-1127 compilation. The build receipt reports one changed outer entry,
every byte outside changed entries identical, all changed entries reparsed,
all sibling game files matching the source, distinct source/output inodes, and
atomic publication.

## Runtime path

1. Boot the complete separate game folder.
2. Finish first-run team construction and reach the 2K Nav Main Menu.
3. Open **Features**, then **2K Beats**.
4. Focus a real track and invoke the on-screen Biography action. The private
   SDL controller exposes X/Y with swapped labels, so the diagnostic helper's
   `X` input produced the game's displayed `Y` action.
5. Observe the `2k_beats_bio` page. Its centered title reads
   `MOD BIOGRAPHY`; the unchanged body and portrait remain intact.

All visual inspection and emulator operation used Spark Hands on the isolated
desktop. No action touched the operator's `DISPLAY=:0`, mouse, or keyboard.

## Bounded negative retained from the first candidate

The earlier `SOUNDTRACK` -> `MOD MUSIC` build was a valid writer/build proof,
but a separate bounded trace established that outer-1127 pool 7 is not the
2K Beats playlist's direct text source. Its exact game-wide consumer remains
unidentified. That result is recorded in
`reports/product/apf_soundtrack_localization_consumer_20260718.md`; it must not
be misreported as a failed writer or used to justify more blind 2K Beats
navigation.

## Distribution boundary

This receipt contains identifiers, hashes, short before/after labels, and
observations only. It contains no retail archive entry, executable bytes,
texture, audio, screenshot, emulator state, preimage, or compiled game output.
The private `.apf2k8mod` contains only user-authored replacement strings and
metadata; the complete built game folder contains retail data and is never a
release artifact.
