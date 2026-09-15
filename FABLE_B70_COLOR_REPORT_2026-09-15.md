# Beta 70: Modern colour and lighting for ESPN NFL 2K5 (Fable line 2)

Written by Claude Fable 5.1, 2026-09-15, branch `fable/b70-color` = 3b10af5f (worktree `~/2k-worktrees/fable-b70-color`,
base `local/stack-beta-70` = df9b9dcf, one commit, explicit paths, not pushed). EXPERIMENTAL / UNWITNESSED: everything below is proved offline by byte receipts and
decoder read-back, or measured from broadcast stills; no one has watched the option in game.

Noah's ask: "the game looks very dull versus the screenshots you have of the chiefs broncos game... I want the grass, at
arrowhead at night and other comparable places, to look this green. and the red of the jerseys to look like that. Can we
do a modern lighting/color mod patch?" and "get stills of every team and then look up and match to the time of day it
happened, the stadium, etc, and use all of those references to perfect the lighting/color mode".

## 1. What ships

One Build tab option, **Modern colour and lighting (experimental)** (`BuildPlan.modern_color`, `nfl2k5_modern_color`
owner, off in every preset, needs a disc image). Two data-only edit families, no executable code, no cave, no hook:

1. **Light rigs (executable, .rdata).** The game keeps seven 0x120-byte light tables and picks one at game entry
   (`FUN_000641c0`) by indoor, rain, snow, day, afternoon (dynamic sun position from the stadium node) and night;
   `FUN_000f2360` installs the ambient colour times its intensity and then two or three directional lights (colour,
   direction, intensity, 0x40 bytes each). The option rewrites ambient colour and intensity and every light's colour and
   intensity in place; directions, light counts and the shadow value at +0x100 keep their retail bytes. The seven
   tables, the selector, the installer and the per-light push are pinned by SHA-256; a foreign table refuses.
2. **Stadium bundles (all 477 `sNN{d,a,n}{d,r,s}.iff` archive outers, 53 stadium art sets times day/afternoon/night times
   dry/rain/snow).** Per bundle: the Fldd time-of-day tint word (uncompressed), the `detail_normal` grass bump palette
   (raw or compressed chunk, refit in place), and the `field` scene refit into its own fixed VC-LZ span with the
   wrapper untouched (the 2026-09-03 rule: never raise wrapper word +0x14): the grass colour-map and outside-grass
   palettes re-graded, the afternoon vertex tint softened, and for the seven turf stadiums without a colour map the
   grass material colour word re-graded instead. Every bundle carries retail and modern SHA-256 pins for each site
   (`data/nfl2k5_modern_color_pins.json`); the build refuses any bundle that is neither retail nor already modern.

Off restores the retail light rigs; the stadium bundles are only written by a build that starts from a retail (or
already-modern) source, and Off leaves whatever the source carries.

## 2. The evidence, in the order it was found

See `docs/modern_color/README.md` on the branch for the full per-game table (all 32 teams), the bucket model and the
previews. Headlines:

| Lever | Where | Evidence |
|---|---|---|
| Light rigs | `.rdata` 0x4E73B0 day, 0x4E74D0 night and indoor, 0x4E75F0 / 0x4E7710 alternate branch, 0x4E7830 rain, 0x4E7950 snow, 0x4E7A70 afternoon base (copied to 0xB34650 with the sun direction) | `FUN_000641c0` disassembled (`mov ecx, table; mov [0xB34774], ecx; jmp FUN_000f2360`); `FUN_000f2360` reads +0x00..0x0B ambient, +0x10 intensity, +0x14 count (dword: 2 for day, 3 elsewhere), +0x20 + 0x40 i colour, +0x40 + 0x40 i intensity; `FUN_000f24d0` pushes the lights. Retail day key light is (1.00, 1.00, 0.72) and every ambient is 0.27..0.40. |
| Field colour map | `field` SCNE, texture `color_premipped` 128x64 P8, plus `grass_outside_premipped` | `nfl_scne_inventory` parse; Arrowhead night median (100, 125, 66), identical across the stadium's nine variants |
| Grass bump | `detail_normal` TXTR 512x256 P8, median (127, 128, 219), bound to the detail layer by `FUN_0009c160` (+0x38) | decoded; four distinct maps across all bundles |
| Time-of-day tint | Fldd word 2: day white, afternoon (255, 238, 205), night (242, 255, 255); afternoon also baked into the field vertex colours | `FUN_0009c160` writes Fldd[2] into the field render block and the yard-line materials (+0x18) |
| Turf stadiums | material `color_premipped` colour word (+0x18): Baltimore 0xFF37683B, Seattle 0xFF538349 | 63 bundles have no colour-map texture |
| Retail look | 9/7 in-game capture: near turf (34, 43, 2), lit blades (71, 84, 18) | same hue as the colour map, a third of its value, blue collapsed: the yellow key plus dim ambient plus bump contrast |
| Fog | haze table 0xA867F0 (dry 0..0.8, rain 0.8..0.9, snow 0.6..0.8; start 3000, end 6000) | owned by the beta-69 haze option; not touched |
| Gamma ramp | `FUN_00033d50` / `FUN_00033e00` set a caller-supplied ramp that retail leaves null | not used: xemu support unverified |
| Fldd words 3 and 4 | per-stadium greens | not read by the field renderer (only `FUN_0009c160` reads Fldd, words 0..2); left alone |

## 3. Broadcast references (all 32 teams)

Anchor: Arrowhead night (Broncos at Chiefs, MNF): turf median (107, 121, 53), HSV 73 degrees / 0.56 / 0.47 over 752
sampled frames; whites (231, 218, 213); skin (137, 96, 76). The Week 1 compilation was cut into sixteen games by hand
from the scorebugs and end-zone art (frame ranges in the README): six day open-air games, two late-afternoon open-air,
two night open-air (Arrowhead, MetLife) and six domes. Bucket medians: day (88, 105, 61); late afternoon (98, 119, 72);
night (107, 121, 57) at Arrowhead and (71, 91, 61) at MetLife; dome (100, 118, 69). Constants across every bucket:
turf hue 73..96 degrees, saturation 0.33..0.56, value 0.36..0.50, whites neutral, skin (120..158, 86..113, 69..86).

## 4. Values the option writes

Light rigs (ambient x intensity; lights colour x intensity), retail then broadcast:

- Day: (0.85, 0.93, 1.00) x 0.285, key (1.00, 1.00, 0.72) x 1.20, fill (0.85, 1.00, 0.95) x 0.20 becomes
  (0.92, 0.95, 1.00) x 0.45, key (1.00, 0.98, 0.94) x 1.15, fill (0.88, 0.93, 1.00) x 0.30.
- Afternoon: (1.00, 0.92, 0.65) x 0.27, key (1.00, 0.92, 0.65) x 1.00, fills (0.45, 0.45, 1.00) x 0.15 becomes
  (1.00, 0.95, 0.86) x 0.40, key (1.00, 0.94, 0.84) x 1.10, fills (0.70, 0.78, 1.00) x 0.22.
- Night and indoor: (0.83, 0.97, 1.00) x 0.31, three (0.95, 0.95, 1.00) x 0.67 becomes (0.94, 0.96, 1.00) x 0.42,
  three (1.00, 1.00, 1.00) x 0.72.
- Rain: (1.00, 0.86, 0.86) x 0.35, three (0.79, 0.79, 1.00) x 0.50 becomes (0.92, 0.93, 0.98) x 0.42, three
  (0.92, 0.94, 1.00) x 0.62. Snow: white x 0.40, three (0.89, 0.89, 1.00) x 0.34 becomes (0.96, 0.97, 1.00) x 0.45,
  three (0.95, 0.96, 1.00) x 0.55. Alternate day and dynamic follow the day rig.

Stadium edits: colour map and outside grass pulled 35 percent toward hue 82 degrees, saturation x 0.90, value x 1.04
(Arrowhead's colour map (100, 125, 66) HSV 73 / 0.47 / 0.49 becomes about hue 76, 0.42, 0.51); bump normals flattened
to 55 percent; afternoon tint 0xFFFFEECD to 0xFFFFF5E6 and vertex (255, 238, 205) to (255, 245, 230); night tint
0xFFF2FFFF to 0xFFF8FCFF. A flat-grass estimate (colour map lit by the rig) moves day from (140, 181, 77) to
(160, 200, 105), night from (180, 231, 128) to (213, 255, 142), afternoon from (74, 86, 36) to (97, 117, 58); the bump
map halves those on screen, which lands near the measured broadcast turf.

Coverage: measured for day open air, late afternoon open air, night open air and domes; extrapolated for rain, snow,
the alternate selector branch, and every stadium not in Week 1 (each keeps its own colour-map hue and only receives the
shared pull). Night and domes share one retail table; a separate dome rig would need a new table allocation and a
four-byte operand change at 0x642BE, and is not in this build.

## 5. What could not be proved

- The drawn field colour: the field pixel shader combines the colour map, the Fldd tint, the bump map, the specular map
  and the rig; the bump lighting math and the specular contribution were not decoded, so the on-screen result is an
  estimate. The 9/7 capture shows a third of the colour map's value with blue collapsed; whether the new rig alone
  restores the blue is exactly what a witness will tell.
- Uniform reds: the jersey textures were not changed; the rigs are the only lever applied. The measured Chiefs red is
  (138..148, 7..29, 30..51).
- Player skin and white uniforms under the brighter night rig (0.42 + 0.72 + two 0.51 side lights on an upward face,
  about 12 percent above retail): clipping is possible on the brightest whites.
- xemu versus console: nothing here depends on the emulator, but nothing has been watched on either.
- 21 field scenes (alternate stadium sets s48..s59, day variants) and 18 bump spans keep retail bytes because their
  retail VC-LZ streams cannot be re-encoded inside the wrapper without raising the loader scratch word (the 9/3 hang).
  They still get the rigs and, where the bump span fits, the flatter bump map.
- Build cost: the 366 distinct spans refit in about 8 minutes here with eight workers (21 of them need the optimal
  parser at one to four minutes each); a Windows laptop will be slower. The help text says so.

## 6. Tests and gates run

Pins (`data/nfl2k5_modern_color_pins.json`, generated from the pinned retail extraction with the module's own
transform, 8 worker processes, about 14 minutes): 477 bundles, 7 light tables. Sites changed: field scene 456 of
477, grass bump map 459 of 477, tint 260 of 477 (the 217 unchanged tints are the day white 0xFFFFFFFF and one odd
dome value, both left alone by design). 21 field scenes could not be refit inside their retail wrapper and keep the
retail colour map: the day, day-rain and day-snow variants of the alternate stadium sets s48, s50, s51, s53, s55, s57
and s59 (rows 48 to 59 of the climate table are the alternate and historic stadiums, not current NFL homes); 18 bump
spans (one of the four distinct maps) keep their retail bytes for the same reason. Every unfit span is recorded with
retail == applied in the pins, so status and verification stay exact.

Standalone runs, `python3 tests/mod_editor/<file>.py`, all green unless stated:

| File | Result |
|---|---|
| `test_nfl2k5_modern_color.py` (new: palette, bump, tint, rig definitions, retail XBE apply/replay/restore/foreign, Arrowhead bundle equals its pin, pins cover 477 and the extraction reads retail) | 8 passed |
| `python3 -m mod_editor.capabilities.validate_registry` on the hydrated tree | PASS, capabilities=173 |
| `test_build_panel_qt.py` | 13 passed |
| `test_mod_build.py` | 11 passed |
| `test_studio_shell_layout_qt.py` | 18 passed |
| `test_phase1_packaging.py` (allowlist, registry count 173, nfl2k5 catalog 100) | 23 passed |
| `test_b68_a1_audit.py` (registry 173, nfl2k5 100) | 10 passed |
| `test_b69_a1_registry.py` (173 / 168 / 5 / 126) | 7 passed |
| `test_b69_a1b_game_audit.py`, `test_b69_a1_runtime_imports.py`, `test_b69_a2b_game_wiring.py`, `test_gameplay_patches_panel_qt.py` | 4, 4, 8, 1 passed |
| `test_update_check.py`, `test_beta45_honesty_freeze.py`, `test_apf_public_docs_registry_current.py` | 21, 9, 5 passed |
| `test_xbe_patch_memory_writes.py`, `test_xbe_patch_cave_references.py` (with the new owner in the manifest chains) | 119 passed in 1697 s, 131 passed in 1915 s |
| Disposable retail image copy on Storage (`/media/noah/Storage/.b70-fable-color/image_apply_test.py`): retail statuses read (1.0 s); XBE rigs applied (7 tables, 279 bytes changed, verify green); all 477 bundles rewritten through 366 distinct refits in 400 s with eight workers; image status `applied`; a second apply rewrote 0 and reported 477 already applied; Arrowhead night in the image equals its applied pin | PASS |

## 7. What Noah should look at first

1. Play Now, Broncos at Chiefs, Arrowhead, night, clear: compare the field against the MNF stills (turf around
   (107, 121, 53), whites neutral). Then Cowboys at Giants at night (MetLife, cooler turf).
2. A 1 PM game at Jacksonville or Nashville (day rig) and a 4:25 PM game at Philadelphia (afternoon rig).
3. Any dome (the night table also lights domes): Lucas Oil or Ford Field.
4. Rain and snow games, which are extrapolated.
5. Watch white uniforms and skin for clipping; watch the far field for banding after the bump flatten.

## 8. Files on `fable/b70-color`

New: `mod_editor/core/nfl2k5_modern_color.py` (writer, pins, CLI: `status <source>`, `apply <disposable image>`, `pins <retail extraction> --write`), `data/nfl2k5_modern_color_pins.json` (477 bundle pins plus the seven retail light tables), `tests/mod_editor/test_nfl2k5_modern_color.py`, `docs/modern_color/README.md` and three preview PNGs.

Changed: `mod_editor/core/mod_build.py` (BuildPlan `modern_color`, presets Off, availability, inspect, preflight, the XBE step after the haze step, the bundle step after the climate step), `mod_editor/core/nfl2k5_build_settings.py` (saved choice), `mod_editor/gui/build_panel_qt.py` (checkbox, state, has_work, summary labels, restore label), `mod_editor/core/nfl2k5_cave_manifest.py` (owner in both probe chains, status check, extra owners, reservations), `mod_editor/capabilities/registry.v1.json` (row `nfl2k5.presentation.modern_color_lighting`, sorted), `tools/validate_all_mod_editor_capabilities.py` (173 / 168 / 126), `packaging/check_2k5_mod_studio_runtime.py` (product module, Build tab repin, registry count 173), `packaging/check_apf2k8_mod_studio_runtime.py`, `tests/mod_editor/test_phase1_packaging.py`, `tests/mod_editor/test_apf_studio_installer.py` (registry count 173), `packaging/release-allowlist.txt` (module and pins), `docs/mod_editor/2k5_mod_studio_changelog.md` (RC95 bullet).

Left for the stack integration (parent): the cave reservation manifest must be regenerated as the last code commit, because the manifest builder's probe chain and owner list now include `nfl2k5_modern_color` (seven .rdata reservations when applied); until then the seven manifest suites report the usual stale-fingerprint class. Nothing else is left to wire.
