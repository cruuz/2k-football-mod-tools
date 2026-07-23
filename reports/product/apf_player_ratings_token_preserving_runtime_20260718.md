# APF 2K8 player-rating token-preserving runtime receipt — 2026-07-18

## Completed experiment

**Positive for transport and edited-player record load; inconclusive for the
numeric gameplay effect.** Player 788, Dan Marino, received one authored base
rating change: Speed `40` → `99`. The decoded roster diff was exactly one byte,
and 284,014 of 284,015 original H7A tokens were preserved.

The complete candidate booted through APF's fresh-profile route, reached Team
Create and Gold Player selection, selected Dan Marino, and rendered his card
normally. The Star Card exposed biography and special abilities but no numeric
base ratings. Therefore the run proves the repaired transport and player-record
load/selection path, but it does not by itself prove that a Speed gameplay
consumer observed `99`.

## Pinned environment

- Project root: `/media/noah/Storage/for codex 1.0`
- Emulator: Xenia Canary `canary_experimental@6e5b8324f`, built 2026-07-08
- Title ID: `54540807`
- Isolated graphical session: `DISPLAY=:99`
- Candidate game: `.codex-tmp/apf-marino-speed99-alpha15`
- Persistent roots:
  `.codex-tmp/apf-four-family-runtime-sdl/runtime-marino-speed99-alpha15/{storage,content,cache}`
- Xenia reported `ProfileManager: Found 0 Profiles`, proving this was the fresh
  profile path.
- All visual inspection and controller operation used spark-hands. The
  operator's live desktop was not touched.

## Source and build receipt

| Property | Value |
| --- | --- |
| Untouched source | `extracted/All-Pro Football 2K8 (USA)/0A` |
| Source `0A` SHA-256 before and after | `dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e` |
| Candidate `0A` size | 1,140,850,688 bytes |
| Candidate `0A` SHA-256 | `19a09f9bcd98adf592a541a2dc1d96e503059479fc906fdb9f95df006c72769e` |
| Build receipt | `.codex-tmp/apf-marino-speed99-alpha15/.apf2k8-mod-studio-build.json` |
| Build-receipt size | 1,649 bytes |
| Build-receipt SHA-256 | `18f118b44aaf04a7a5bcd3b2fc10a94744ccdbaf5dcb6d4023e276a4794790ea` |
| Changed outer entry | index 1,126, `roster/ROST` |
| Rebuilt outer-entry size | 436,224 bytes |
| Rebuilt outer-entry SHA-256 | `e852d656ab304400ecef91fed19baed2b4285e212159800423421ad5d3d21836` |
| Stable target | `apf:player-rating:788:speed` |
| Authored value | `40` → `99` |

The receipt records `source_modified: false`, a read-only source, distinct
source/output inodes, atomic publication, successful reparsing of the changed
entry, byte identity outside changed outer entries, and exact matches for all
unchanged sibling files.

The full candidate and rebuilt outer entry are retail-derived private data and
must not be distributed.

## Semantic and transport diff

| Property | Value |
| --- | ---: |
| Player index | 788 |
| Rating ID | `speed` |
| Rating record-relative byte | `+0xBA` |
| Original stored integer | 40 |
| Replacement stored integer | 99 |
| Decoded bytes changed | 1 |
| Original H7A tokens | 284,015 |
| Original tokens preserved | 284,014 |
| Tokens repaired | 1 |

No neighboring rating, identity string, pointer, count, membership field,
ability bit, tier field, or padding byte was intentionally changed. No rescale
or derived-Overall rewrite was involved.

## Runtime transcript

1. The private launcher started the candidate from its separate complete-game
   directory with isolated storage/content/cache roots.
2. Xenia loaded the title and reported zero profiles.
3. APF rendered its title flow without the historical generic-ROST crash.
4. The run entered Team Create and then Gold Player selection.
5. Dan Marino was selected and his player card/presentation rendered normally.
6. The card showed biography and abilities but did not expose numeric base
   ratings; no visual `99` claim was made.
7. Xenia exited cleanly. The log's final line was `Cheap-skate exit!`.

The discriminating historical signature—guest PC `0x84AB1D40` and its host
access violation—was absent.

## Evidence chain

| Exact evidence path | Bytes | Mode | SHA-256 | Proved observation |
| --- | ---: | ---: | --- | --- |
| `/home/noah/backbreaker-research/evidence/live-captures/apf-marino-speed99-token-preserving-runtime-20260718.mp4` | 734,146 | `0600` | `113de8c9d5f2547e88c024a0333910c21be7cdb1993da9f4aba2db807f4f45a1` | Dan Marino can be selected and rendered normally from the edited candidate. |

Runtime logs:

| Artifact | Bytes | Lines | Mode | SHA-256 |
| --- | ---: | ---: | ---: | --- |
| `.codex-tmp/apf-four-family-runtime-sdl/logs/xenia-marino-speed99-alpha15.log` | 119,729 | 1,838 | `0600` | `97fca17386ba732e113a202cf4b45a67d8972e0fd3a5ef15e002371d234e35fe` |
| `.codex-tmp/apf-four-family-runtime-sdl/logs/controller-marino-speed99-alpha15.log` | 124 | 7 | `0600` | `d9b436738d2647f3c465afad8b04fe19aab56a77aa5aa6eee2954a7cd78e8c98` |

The Xenia log pins:

- build banner at line 1: `canary_experimental@6e5b8324f`;
- zero-profile record at line 48;
- title ID `54540807` at line 216; and
- normal `Cheap-skate exit!` at line 1,838.

## Classification

### Proved

- semantic resolution to player 788's Speed byte;
- exact one-byte decoded authoring;
- token-preserving H7A compilation with only one repaired token;
- safe complete-game construction with an untouched source;
- normal APF boot through a fresh profile;
- normal load, selection, and rendering of the edited player record; and
- absence of the old generic-rebuild crash signature.

### Not proved

- a numeric on-screen `99` readout;
- a Speed-dependent gameplay or animation difference;
- effect size versus the stock value of 40;
- runtime behavior of `0`, `50`, native `100`, or the other 27 fields;
- overall-rating, ability, tier, dynamic-modifier, save, or roster-capacity
  semantics; or
- Xbox 360 hardware behavior.

## Cleanup and rollback receipt

After capture:

- Xenia exited and no private control FIFO remained;
- the private launcher was restored byte-for-byte to SHA-256
  `724708e07c90fe49a90a5b3005aa5648053c2ad3effe4c84e6397eb483bd46aa`;
- the controller injector was restored byte-for-byte to SHA-256
  `d5f3f1eede014097d80f5d3f13ba0547cec03f1851b091c58a24dcd778bcffda`;
- the user's source remained unchanged;
- no sealed release tree, archive, or checksum sidecar was modified; and
- the candidate remains private because it contains user-owned retail bytes.

## Best next experiment

Repeat a fixed sprint or deep-route scenario stock versus Speed 99 with the
same player and enough trials to separate the rating effect from input and
animation variance. Preserve this exact one-byte/token-preserving build route.
A direct player-editor numeric screen, if recovered, can add a visible-value
spot check but should not replace the gameplay A/B.

