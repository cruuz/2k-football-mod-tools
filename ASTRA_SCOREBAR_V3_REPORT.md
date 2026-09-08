# r64 scorebar v3, 2026-09-07

**EXPERIMENTAL / UNWITNESSED.** The default static bar is now
`espn-broadcast-exact-v3`. Its down pill and three clock cells stay requested
through all six sampled native states. Existing live abbreviation callbacks
read each team's retail primary color and tint the two existing materials.
The static path uses retail FONT4/FONT8, with no runtime owner, entry hook,
resource lookup, cached team pointer or new allocation.

Branch: `astra/r64-scorebar-v3`. Base: `ae99298`. Work was confined to this
worktree and temporary files. Retail XBE, archive slices, original disc,
research corpus and hub reports were read-only. No console emulator, game,
GUI, audio, network or push was used. Unicorn ran bounded native CPU
fixtures with explicit world inputs. No disc or archive copy was created.
The protected integration handoff is the section
[“r64 scorebar v3, 2026-09-07”](WIRING.md#r64-scorebar-v3-2026-09-07).

## Noah's witness and its reconstruction

Noah's three disc-bf captures are preserved under
[docs/scorebug_ingame/v3/witness](docs/scorebug_ingame/v3/witness/).
They witness **installed v2**, not this revision. The new
[comparison.png](docs/scorebug_ingame/v3/comparison.png) shows the original,
reconstructed v2 and v3 forecast side by side, plus a second live clock sample.

The independent v2 compiler is the exact previous source, pinned at SHA-256
`7626ade9cf27019e86e13ee8bf5c69b74851620846edfcab0b5461c1d0d6faba` in
`tests/fixtures/nfl2k5_scorebug_exact_v2.py`. It reconstructs the installed
SCNE span `6c3cad4eee9dc3aab4d4cc2ffba60dfdfc579c40fa6d60b18d013deab0529eea`
and atlas `a4055637d479233c9e929f73fa3ee60da5826e28f47b0f562ed39771a50d90f3`.
The historical context installs that compiler's own XBE spans. It does not
simulate the old defect by turning off nodes in the new scene.

**PROVED:** native scene relocation, material binding, descriptor updates,
FONT selection, string formatting and glyph submission reproduce the v2
center disappearance. The live negative control requests neither down nor
play clock and has neither middle background in its visible geometry.
One viewport transform per capture comes from its frame rails; text bounds
are independent checks. All 14 measured ink boxes match within one pixel.
No text-specific scaling or displacement was fitted.

| Capture | Native state and visible values | Viewport affine | Independent ink checks |
| --- | --- | --- | --- |
| `165742`, BAL at JAX | Presnap, home possession, `2nd & 10`, `2ND`, `1:28`, `15` | 1.5 ×, offset (86, -26) | Two scores, down and three cells: all errors 1 px |
| `170211`, MIN at NYJ | Presnap, away possession, `3rd & 2`, `1ST`, `4:18`, `30` | 1.5 ×, offset (92, -10) | Five exact boxes; play-clock error 1 px |
| `170222`, MIN at NYJ | Live, away possession, middle absent in v2 | 1.5 ×, offset (89, -12) | Both score boxes exact |

The third capture cannot reveal hidden middle values. **HYPOTHESIS / fixture
inputs:** its quarter and down carry forward from presnap; the forecast uses
`4:15`, followed by `4:14`, and an unavailable play clock `--`. Those values
are labeled in the image. Native callbacks format each sampled value anew.
The reused empirical video-range correction is gain 1.082, bias -21.1.
GPU filtering, shader execution and video capture remain modeled. Matching
ink bounds is a calibration result, not an exact photographic pixel claim.
[calibration.json](docs/scorebug_ingame/v3/calibration.json) records every
input, bounding box, native draw, material and raster limitation.

## Persistent middle: native mechanism and decision

**PROVED:** `FC9C0` owns the native visibility requests. Descriptor records
start at `A959C8`, stride `0x70`; `+38` is the request, `+3C` the current
slide, `+2C/+30` its closed/open endpoints, and `+58` binding availability.
The down and play-clock requests are `A95A00` and `A95A70`. Both the native
material updater and `FC360` text submission use the slide. Keeping text
bindings alone was insufficient, as v2's live state demonstrated.

The complete span `FCA87..FCCCC`, 581 bytes, is rewritten inside the existing
function. Unchanged native event decisions remain; removed center-hide
branches free room for two small helpers in that same owned span. Its common
active-state epilogue writes one to both requests. The native mode-zero early
return and the function prefix are retained. There is no branch into an
unreserved cave and no mutable data in `.text`.

| State | Retail/v2 requests, down / clock / hangtime / flag / ball / fumble | v3 requests |
| --- | --- | --- |
| Presnap | 1 / 1 / 0 / 0 / 0 / 0 | 1 / 1 / 0 / 0 / 0 / 0 |
| After play | 1 / 0 / 0 / 0 / 1 / 0 | 1 / 1 / 0 / 0 / 1 / 0 |
| Live | 0 / 0 / 0 / 0 / 0 / 0 | 1 / 1 / 0 / 0 / 0 / 0 |
| Kickoff | 0 / 1 / 1 / 0 / 0 / 0 | 1 / 1 / 1 / 0 / 0 / 0 |
| Flag | 0 / 0 / 0 / 1 / 0 / 0 | 1 / 1 / 0 / 1 / 0 / 0 |
| Fumble | 0 / 0 / 0 / 0 / 0 / 1 | 1 / 1 / 0 / 0 / 0 / 1 |

Decision: ball-on, flag, fumble and hangtime replace the down text within the
same red pill. Their opaque panel is at z=-7 and text at z=-8. The clock row
keeps its v2 size and depth below them. Down still submits behind the event,
which is permitted by the brief. Native strings include `Ball on WAS 35`;
event glyphs clear the clock cells and three-digit scores in the fixtures.

`FBE30..FBE51` is pinned and replaced as one 33-byte formatter, retaining its
caller-buffer ABI. Helper `FCCA6` reads native play-clock owner `E60294`.
A null owner or native unavailable flags `owner+18 & 6` writes UTF-16 `--`;
otherwise it tail-calls the retail `FBB10` getter and retains native rounding
and the existing `%02d` suffix. Quarter and the short/long game-clock
callbacks stay live. The latter naturally switch at ten minutes; an empty
short-clock callback is paired with a populated long-clock callback.

Six states, both aspects and both placement modes run native request and
slide updates. Transition fixtures keep both slides fully open across 140
frames while preserving binding availability. Existing tests retain clock
boundaries, OT labels, `4th & Inches`, all 32 abbreviations, both possessions,
999 scores, score-flip phases and native decompression.

## Live retail team colors

**PROVED:** getters `61C50` and `61C60` return the home and away live contexts
(`B30864` and `B30A58`). Native team records hold asset-code strings at `+10C`
and live abbreviation strings at `+13C`. The existing `FC010` and `FC030`
callbacks already obtain these contexts; v3 uses those same draw callbacks.
No game-load or entry callback is introduced.

Retail primary accessor `68D70` reads the 80-row table at
`4E7FE0..4E88A0`, stride 28, primary ARGB at row `+8`. Its case-insensitive
asset-code comparison is `30B90`. The full table is pinned by SHA-256
`0713d8ca89333142d86dad04904d4804ea76687301a50df7265b5407302036e6`.
This is the game's table, not the host's authored `TEAM_LOGOS` palette.
The host fixture uses asset-code metadata only to construct live team
records; the callback obtains every color by executing the retail accessor.

The native Team Select function `31F1D0` supplies an independent consumer:
`31F48F` resolves its material, `31F4B0` calls `68D70`, and `31F4B6` stores
EAX at material `+18`; its other branch calls secondary accessor `68DC0`.
The call/store bytes and hash are preserved in
[colors.json](docs/scorebug_ingame/v3/colors.json), alongside the table reads
from all three required matchups. The read-only Ghidra corpus identifies the
same menu path.

| Team | Asset code | Retail primary ARGB | Resulting panel ARGB | Native primary read |
| --- | --- | --- | --- | --- |
| BAL | 02 | `FF31145C` | `FF31145C` | `4E8020` |
| JAX | 12 | `FF0C586D` | `FF0C586D` | `4E8138` |
| MIN | 15 | `FF422259` | `FF422259` | `4E818C` |
| NYJ | 19 | `FF253F36` | `FF253F36` | `4E81FC` |
| WAS | 29 | `FF86364A` | `FF3B1821` | `4E8314` |
| NYG | 18 | `FF191C5C` | `FF191C5C` | `4E81E0` |

Contrast rule: retain RGB if every channel is at most 112; otherwise replace
each channel c with `floor(c/2) - floor(c/16)`. Set alpha to 255. The maximum
resulting channel is 112, guaranteeing at least 4.5:1 contrast against both
white and native possession yellow `FFFFFF40` under the standard sRGB
luminance calculation. Every channel value and key gray boundaries run
through the native implementation as well as the host rule. These synthetic
math probes restore the retail table; the three pair proofs use untouched
retail bytes.

Helper `FCC1F` copies the live abbreviation into its caller's buffer, calls
the accessor, applies that rule, and writes the resident material's `+18`
field. It preserves callee-saved registers and the source string. The home
and away material table indices are 6 and 10, table stride `0x80`, obtained
from `[A95528]+20` only when the scene has its expected 11 records. Null scene
or table skips the store; null abbreviation yields an empty string and
neutral `FF252625`. Unknown or null asset codes retain the native accessor's
fallback color, with the same contrast rule. No `449E0` texture lookup occurs
in these callbacks. Recorded writes are limited to the caller stack, output
buffer and the single expected material word.

**PROVED to the CPU submission boundary:** native renderer instructions
`241EC..241FB` read material `+18` and call `23BF0`. The pinned native function
emits a 28-byte shader-constant command with header `41EA4, 6, 100B80` and
RGBA channels divided by 510, the game's half-scale protocol. An unchanged
color emits no second command. The bounded test uses the callback-written
material and validates every write. **HYPOTHESIS:** the final GPU tint is
represented in the raster by multiplying the white texel by the material
color; no GPU shader was executed here.

Timing limit: `FC360` submits the mesh before running its abbreviation
callbacks. A freshly loaded scene therefore starts neutral; the next draw
uses the new colors. If a scene is reused across a team change, one draw may
still have the previous colors. No cached team binding or entry work was
added to remove that one-draw delay.

## Exact edits and resource receipts

All new native spans include complete retail and replacement bytes in
[receipts.json](docs/scorebug_ingame/v3/receipts.json) and
`mod_editor/core/nfl2k5_scorebar_v3.py`. Replay is byte-identical; mutation of
every new span or dependency guard refuses before mutation. Existing section
digests are repinned through the normal writer.

| Span, end exclusive | Bytes | Change |
| --- | ---: | --- |
| `FCA87..FCCCC` | 581 | Native visibility body plus helpers at FCC1F and FCCA6 |
| `FC010..FC02D` | 29 | Existing home abbreviation callback plus lazy color |
| `FC030..FC04D` | 29 | Existing away abbreviation callback plus lazy color |
| `FBE30..FBE51` | 33 | Complete play-clock formatter, live value or `--` |
| `A95CB0..A95CB4` | 4 | Existing material-name pointer, E6C780 to E6C6E8 |

The 581-byte retail span hash is
`e563e5240911c235ffb43a773f40a319fe53e9af03aa6b98403f38b2931ef44d`;
replacement hash is
`e2d2c3006998c1263c8039b1fdfa99106141e73f2ecc976bd97c7474be1a3d3f`.
The checked-in [assembly](docs/scorebug_ingame/v3/visibility_and_color.s)
assembles to those exact replacement bytes with GNU `as --32`, `ld -m
elf_i386 -Ttext=0xfca87` and `objcopy -O binary -j .text`. Its L-address
labels identify corresponding retail instructions, not relocated addresses.
No additional RX, RW or RO space is requested.

The static scene repurposes the old corner mark as the home panel and keeps
`zscore_buga` for away. Both use a white atlas texel and root-palette vertices,
independent of score rotation. Home's disjoint-triangle topology is filled
with two complete triangles; both have the existing negative winding. Its
material name becomes the existing `score_buga` literal. Only geometry,
vertex data, text transforms, this name and the two materials' `+14/+18`
color words change. Index strips and the 16,512-byte decoded SCNE size remain.

Both fixed resource spans retain their entire retail wrapper and its
16-byte overlap-scratch declaration. Native overlapping decompression agrees
with host decoding. Scene refit consumes 4,785 of 4,800 stored bytes; the atlas
consumes 2,389 of 2,400. There is no archive growth.

| Output | SHA-256 |
| --- | --- |
| Static XBE | `5ec31f2351d6e0257b978ca577585161cf44b2f76cd85fce183e75a8a13f46fd` |
| Static SCNE span | `7b072c04b9d35f59a5645ce196cd209238ff5426d657e5bae43de6e26a5f7a35` |
| Static atlas span | `0bdaba82bfa2fc9a2862994ad39f4620a96fcd23f8800773a1a7b622765ee039` |
| Decoded static SCNE | `b59a76a64911a168c8d577860d469730fd7662ce44c18ed45f391d57af43bfdd` |
| Decoded diagnostic SCNE | `1dfb3467aceec7fc598643ae9585387b1940135d891140cf2352f52d81e3ac1b` |
| Diagnostic HUD after | `bb5b2ef49ced9bd0ce3425cd8beccdb852d364505800054e8419787ea44a26d8` |

The diagnostic scene shares the renamed, collapsed corner material and the
atlas's new white texel. Its geometry and existing private-font/entry-hook
code remain unchanged; its panel/font appendix is still
`846864649a3b2309c476edb55fc9b14a912e062548d1a2abf474a8e3acf44063`.
Its probe resource pins were updated and revalidated. This preserves the
existing diagnostic contracts; it does not fix or enable the runtime owner
whose custom team-binding hooks the tester tied to the entry hang.

An explicit artwork folder remains byte-identical v10: XBE
`0d0eee5163c1d5edbc41a8a0a522f3c55d74e9c5699f078aab37bd9e01b8d23f`,
SCNE `8bf58e95bdc4ddbfe627ee705165f7a639d5ba033dc3d6c9732f622ef3e364f2`,
atlas `a208b56329eec1dc285dfc8f04dcf66883b62d502c549ed70583d2fb7b0b1609`.
Cross-version application and mixed XBE/resource combinations refuse.

Read-only real-disc preflight plans exactly three fixed-span writes: XBE at
2,396,160 (11,948,032 bytes), SCNE at 1,741,675,264 (4,832 bytes) and atlas at
1,741,540,432 (2,432 bytes). No acceptance disc was built. Rebuild old v2
installations from a clean retail source; do not layer this over disc bf.

## Validation and delivery

Both full XBE gates passed: **87 memory tests and 99 cave-reference tests**,
including forward/reverse owner orders and scale-out. The static writer is
now explicit in the common composition tuple and its replay checks. The
reference gate groups complete pinned replacements, including retained byte
islands, and keeps adjacent independently called entries separate. It
verifies old/new bytes before excluding displaced internal branches. All
external references and oracle unknowns retain their existing rejection.
There is no new reservation JSON or allocator budget change.

**372 passed, 11 skipped, 0 failures/errors across 383 tests in 22 standalone suites.**

Each command was run as `python3 <path> -v`. The legacy layout command also
sets `NFL2K5_SCOREBUG_EMULATION_TEST=1` for its bounded native CPU checks.

| Standalone test path | Tests | Passed | Skipped |
| --- | ---: | ---: | ---: |
| `tests/mod_editor/test_nfl2k5_scorebar_v3.py` | 9 | 9 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_author.py` | 12 | 12 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_exact.py` | 8 | 8 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_fonts.py` | 9 | 9 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_freeze.py` | 7 | 7 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_ingame.py` | 11 | 11 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_ingame_fix.py` | 9 | 9 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_native.py` | 4 | 4 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_projection.py` | 14 | 14 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_resources.py` | 6 | 6 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_runtime.py` | 12 | 12 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_source_art.py` | 13 | 10 | 3 |
| `tests/mod_editor/test_nfl2k5_scorebug_template.py` | 19 | 19 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_template_release.py` | 5 | 5 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_unified_adapter.py` | 5 | 5 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_v10_ingame.py` | 11 | 11 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_v10_projection.py` | 14 | 14 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_versions.py` | 4 | 4 | 0 |
| `tests/mod_editor/test_xbe_patch_cave_references.py` | 99 | 99 | 0 |
| `tests/mod_editor/test_xbe_patch_memory_writes.py` | 87 | 87 | 0 |
| `tests/nfl2k5_scorebug_layout_test.py` | 15 | 14 | 1 |
| `tests/nfl2k5_scorebug_mod_project_test.py` | 10 | 3 | 7 |

Largest test process: 516,172 KiB (504.07 MiB); witness tool:
287,628 KiB. Every process stayed below 2 GB. Three source-art skips require
absent old importer/comparison exports, one layout skip an absent intermediate
glTF, and seven typed-project skips an absent historical JSON fixture. All
current native, resource, version, template and gate proofs ran.

Exact commands, timings, RSS, log hashes, source/artifact hashes, assembly
reproduction and the protected-path audit are recorded in
[validation.json](docs/scorebug_ingame/v3/validation.json). All edited Python
files compile; `git diff --check` passes. No protected file changed. The
recorded root free space is 108.405 GB, above 100 GB;
scratch contains only small development evidence and the supplied captures.

Development checks exposed a half-filled home triangle, retained-byte islands
splitting the native rewrite in the reference scan, and a shared material-name
mismatch in the diagnostic scene. All were fixed before the passing runs.
Tests that asserted the former collapsed mark or lower event row were updated
to check the new bounded material fields, complete panel and clear clock row.
The reference gate still rejects external retail references and oracle unknowns.

The explicit-path `git add` was refused because the shared worktree index is
on a read-only filesystem. The authorized fallback is
`.scratch/r64-scorebar-v3.bundle`, containing one commit based on `ae99298`
under `refs/heads/astra/r64-scorebar-v3`. Isolated Git metadata and new
objects live under `.scratch/r64-delivery.git`; the shared branch/index were
not changed. The bundle was verified and imported into another temporary
repository, with its tree and changed paths checked. Commit ID, bundle
SHA-256 and final disk usage are in `.scratch/DELIVERY.json`. No push.
Neither `ASTRA_BRIEF.md` nor `.scratch/` is in the commit.

## Noah's precise witness list and known gaps

1. Build from clean retail with the Experimental static scorebar, blank
   artwork folder and runtime effects off. Enter and finish several games,
   then return to menus and change teams. Confirm entry and re-entry without
   a hang, and colors settling on the following draw.
2. Play BAL at JAX, MIN at NYJ and WAS at NYG. Check correct side ownership,
   recognizable primary colors, white scores and yellow possession labels.
   Change possession and start another matchup without restarting the app.
3. Check presnap, snap/live action, whistle/ball-on, kickoff/hangtime, flag and
   fumble. The red pill and all three clock cells must retain their size.
   Events may replace down text; clocks must remain readable below them.
4. Watch the game clock count during live action, including 10:00 to 9:59,
   0:00 and quarter/OT changes. Check the live play clock, under-five values
   and `--` while the native clock is unavailable. Confirm `4th & Inches`.
5. Exercise both field-direction placements in 4:3 and 16:9, score changes,
   three-digit score replays/test states if available, kick meter and lineup
   suppression. Confirm events, names and scores do not overlap the cells.
6. Select an explicit painted artwork folder separately and confirm the
   retained v10 appearance. Its unchanged contract does not add v3's default
   dynamic colors or center-persistence behavior.

Only Noah's supplied v2 captures are gameplay witnesses. V3 color appearance,
GPU material behavior, first-frame timing, unsampled game states, longevity
and game-entry safety remain unwitnessed. Timeout marks remain decorative;
no static logos, private fonts or live timeout counters are claimed. The
protected help/packaging/manifest changes must be integrated before release.
