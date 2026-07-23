# APF 2K8 Mod Studio — `SOUNDTRACK` consumer trace

Date: 2026-07-18

## Completed experiment and result

This was a bounded, read-only trace of English localization record
`0x0149ac0b` (outer `1127`, inner `0`, pool allocation `7`, displayed text
`SOUNDTRACK`) against APF's 2K Beats menu implementation.

**Negative runtime-target result:** the 2K Beats playlist screen is not a
supported runtime consumer for this localization edit. Its dedicated executable
code, scene/layout assets, and static menu descriptors do not contain the text
ID and expose no direct edge to the known localization-loader candidate. The
screen instead has its own compiled menu literals plus dynamic track metadata.
Consequently, navigating farther around 2K Beats is not a useful way to look for
the already-built `SOUNDTRACK` -> `MOD MUSIC` replacement.

This result is intentionally narrower than claiming that record `0x0149ac0b`
is unused game-wide. Its exact game-wide source key and consumer remain opaque.
That unresolved global question is now hard-stopped rather than becoming an
open-ended static-research loop.

## Evidence

| Evidence | Finding |
|---|---|
| Parsed localization bank | Record index `6`, ID `0x0149ac0b`, resolves to pool allocation `7` in English outer `1127:0`. |
| Executable ID scan | The big-endian and little-endian forms of `0x0149ac0b` are absent from the decoded PE; the menu therefore does not embed this ID directly. |
| 2K Beats executable cluster | The bounded jukebox implementation is in `0x846ad1e8..0x846af7b0`. A direct-branch scan of the cluster found no call into the known `0x84761xxx` localization-loading area, including structural lookup candidate `0x84761a08`. An indirect, data-driven route cannot be ruled out globally, but no such route is represented by the jukebox descriptors either. |
| Compiled label | Mixed-case `Soundtrack` exists separately at `0x8450c5c8`; its only stored pointer is `0x8200701c`, outside the 2K Beats descriptors and among Reelmaker/Highlight Create strings. It is not the localization-bank allocation and must not be used as evidence that `MOD MUSIC` should appear in 2K Beats. |
| Jukebox resource | `jukebox.iff` is referenced by menu initialization at `0x846ae288` and another jukebox routine at `0x846adaa8`. |
| Layout inventory | `2k_beats_playlist`, `2k_beats_bio`, and `2kbeats_panel` compose named SCNE assets and transforms; none contains the localization ID. |
| Playlist scene text slots | `text_title`, `text_albumname`, `text_biography`, `text_help`, `text_2kplayer`, and `text_help2`. These are scene control names, not resolved localization IDs. |
| Biography scene text slots | `text_title` and `text_biotext`; artist biography text also has a dedicated `artist_bio_english` STRG resource. |
| Executable literal cluster | The jukebox cluster contains `Track`, `Artist`, `2K Beats Playlist`, `To Dismiss`, `JUKEBOX`, `|M_SECONDARY|`, state/mode labels, its layout names, and `jukebox.iff`. This is a separate source lane from outer `1127` pool `7`. |

The read-only trace was performed against decoded-PE SHA-256 identity already
recorded by the APF product work. Temporary disassembly/decompiler output lives
under `.codex-tmp/apf-soundtrack-static/` and is not a release artifact.

## Exact 2K Beats UI mapping recovered

The useful positive result is a precise mapping between menu events and the
three 2K Beats layouts:

| Event key | Callback | Destination/effect | Runtime hypothesis |
|---:|---:|---|---|
| `1` | `0x846ae288` | initialize/load `jukebox.iff` | enter the 2K Beats screen |
| `2` | `0x846ae3f8` | teardown | leave the screen |
| `4` | `0x846f0a58` | jukebox action | transport/navigation action; exact control not named |
| `5` | `0x846ae4a8` | jukebox action | transport/navigation action; exact control not named |
| `12` | `0x846aea90` | jukebox action | exact control not named |
| `13` | `0x846af078` | open `Beats_Bio` / `2k_beats_bio` | secondary/Y action on an active track row |
| `28` | `0x846af0f0` | open `Beats_Panel` / `2kbeats_panel` | right-stick click; already observed at runtime |

The main screen descriptor is `Beats_Main` / `2K Beats Playlist` /
`2k_beats_playlist`. The two child descriptors are `Beats_Bio` /
`2k_beats_bio` and `Beats_Panel` / `2kbeats_panel`.

If another runtime spot check is useful for the menu mapping itself, use this
short sequence:

1. Enter 2K Beats and dismiss the Player panel if it is covering the playlist.
2. Move focus to a real track row; change rows once so focus is unambiguous.
3. Tap **Y** once. Event `13` should open the biography layout. A failed press
   most likely means the row was not active or the panel still held focus.
4. Return to the playlist and click the **right stick** once. Event `28` should
   open the Player panel.

This sequence proves the child-layout mapping; it is **not** expected to reveal
`MOD MUSIC`. LT/RT/LB/RB hunting in this screen should not be used as another
localization-consumer experiment.

## Best next experiment for universal text runtime proof

The efficient next step is runtime request logging, not more static guessing:
instrument the resolved localization lookup path to record requested text IDs
while traversing menus, then match `0x0149ac0b` to the exact screen and widget.
If a lightweight hook is not practical, use one bounded diagnostic build that
changes several candidate allocations to distinct short labels and records
which, if any, appears. Nearby candidate concepts include `TRACK`, `ALBUM`,
`ARTIST`, `BIOGRAPHY`, `Artist Biography`, and `2K Player`, but the jukebox's
compiled literals mean a fanout test can legitimately produce no change there.

Until one of those experiments succeeds, the product should accurately render
outer `1127` pool `7` as **Editable (offline writer); runtime consumer
unidentified**, rather than associate it with the 2K Beats page.

## Distribution note

This report contains coordinates, identifiers, short UI labels, and findings
only. It contains no retail archive entry, texture, audio, executable block, or
other binary game payload. No source volume was modified.
