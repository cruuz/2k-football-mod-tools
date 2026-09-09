# Hotfix beta-63.1: imported shoe textures reach the game, not just Edit Player

Branch `astra/hf63-shoes` from tag `beta-63` (9c17c538). Bug: maumau78, #2k5-bugs
2026-09-09 05:26 / 06:09, beta 63 in xemu: "I can import shoe texture and editor
show them; in-game they load default texture" (screenshot `2k5-bugs_006.png`: the
EDIT PLAYER screen, Right Shoe Style 1, orange imported shoe on the preview
model; stock shoes in the game).

Everything below is proved offline on the pinned retail executable and the
retail pack index (read-only, never copied). No emulator was run; nothing
in-game is witnessed by me. `ASTRA_DONE` is the last line.

## 1. Reproduction

The Studio's shoe import (`facade.replace_equipment_texture` ->
`nfl2k5_equipment_import.stage_equipment_import`) staged exactly one asset:
the selected package's `tset:<outer>:8:0:shoes01`. Behavioural red run on the
pre-fix tree (the new session test against the old facade):

```
AssertionError: Tuples differ: ('tset:0:8:0:shoes01',) != ('tset:0:8:0:shoes01', 'tset:1:8:0:shoes01', 'tset:2:8:0:shoes01')
FAILED (failures=1)
```

One package changed; the game does not read that package for Style 1 in a
game (section 2), so the import could only ever show on the Edit Player model.

## 2. Consumer chain proof (retail `default.xbe`, SHA-256 73105b17...a4a9)

Player shoe materials `SHOE_L` / `SHOE_R` / `SHOE_both` / `SHOE_tapes`
(`SHOE_spikes` on hi_body) live in the shared player scenes `lo_body`
(outer 3 chunk 113) and `hi_body` (outer 3 chunk 114) with unmapped texture
pointers; the binder fills them at runtime. The chain, function by function
(virtual addresses; every range is hash-pinned in
`tests/mod_editor/test_nfl2k5_equipment_consumers.py::XBE_EVIDENCE`):

| Step | Address | What it does |
| --- | --- | --- |
| Shoe style bits | `FUN_0008EFA0` tail, `0x0008F74A..0x0008F7E3` | player record byte `+0x0C`: bits 0-2 and 3-5 are the two shoe styles (0..5, 6 = taped). Equal -> `SHOE_both` (slot 0x3B); different -> `SHOE_R` (0x3A) / `SHOE_L` (0x39); any 6 -> `SHOE_tapes` (0x3C) with style 6. Slot 0x3D `SHOE_spikes` is filled too when `FUN_00077460()+0x1C` is set. Material-slot names are the 62-entry table at `0x004EEE68` (`0x39 SHOE_L`, `0x3A SHOE_R`, `0x3B SHOE_both`, `0x3C SHOE_tapes`, `0x3D SHOE_spikes`). |
| Style -> cache row | `FUN_0008EF20` (`0x0008EF20`, 115 B) with the shoe table at `0x004EF7C0` (8 B per style) | style 0..6 -> cache rows 84 `shoes01`, 85 `shoes04`, 86 `shoes09`, 87 `shoes02`, 88 `shoes03`, 89 `shoes10`, 90 `shoes_taped`; second word = bump map index (`bump_shoes1..7`). Edit Player "Style 1" is `shoes01`, "Style 2" `shoes04`, "Style 3" `shoes09`, "Style 4" `shoes02`, "Style 5" `shoes03`, "Style 6" `shoes10`. Texture = `DAT_00B65428[(mud*2 + side)*96 + row]`, written into the material at `+0x30` by `FUN_0008E3F0` (`0x0008E422`). |
| Cache fill | `FUN_0008E620` (`0x0008E620`, 368 B) | walks the 96-row binding table at `0x004EEAF8` (name pointer, context-first word) for clean/mud x HOME/AWAY through `FUN_0008E5C0` (adds `_mud`) and `FUN_0008E580`. |
| The decision | `FUN_0008E580` (`0x0008E580`, 49 B): `85 C0 74 1A` = `TEST EAX,EAX / JZ global` | context-first word 1: `FUN_000449E0(HOME or AWAY name, 'TXTR', name)` first, global fallback. Word 0: `XOR ECX,ECX; JMP FUN_000449E0` = global lookup only, the team's package is never consulted. |
| Global lookup | `FUN_000449E0` (`0x000449E0`, 104 B) | `ECX == 0`: walk the context list from `DAT_00B09578` (`MOV ESI,[0xB09578]` at `0x00044A19`, `MOV ESI,[ESI]` next) and return the first context whose resource list has a `TXTR` of that name. |
| List order | `FUN_00043DB0` (`0x00043DB0`, 82 B) | every new context is inserted at the head (`MOV [ESI],old_head; ...; MOV [0xB09578],ESI` at `0x00043DE0`). Newest context wins the walk. |
| Game load order | `FUN_00062BE0`, `0x00063261..0x000632A3` | `STADIUM`, then `HOME` (`MOV ECX,0xE6162C 'HOME'` at `0x00063275`, filename buffer `0xB30710` = `<code>h<style>.iff`), then `AWAY` (`0x00063293`, buffer `0xB30730` = `<code>a<style>.iff`). AWAY is created last, so it is the newest uniform context. |
| Front-end preview | `FUN_00091940` (`0x00091940`, 248 B) | loads ONE package into `DAT_00B651A0`: `%sh0.iff` under `HOME` (or `%sa0.iff` under `AWAY` when `FUN_000EC060` and player side byte `+0x34 == 2`), `36h0`/`36a0` for a player without a team. |

Binding-table rows (`0x004EEAF8 + row*8`, pinned 768 B):

| Row | Name | context-first | Where the game reads it |
| ---: | --- | ---: | --- |
| 84 / 85 / 87 / 88 | `shoes01` / `shoes04` / `shoes02` / `shoes03` (Styles 1, 2, 4, 5) | 0 | the newest loaded uniform package |
| 86 / 89 | `shoes09` / `shoes10` (Styles 3, 6) | 1 | the player's own HOME/AWAY package |
| 90 | `shoes_taped` | 0 | outer 3 (global pack) |
| 27-30 / 31-34 | `glove01-04` / `glove05-08` | 0 / 1 | newest package / own package |
| 35, 36 / 37 | `longsleeve01, 02` / `longsleeve03` | 0 / 1 | newest package / own package |
| 68-71 / 72-74 | `elbowpad01-04` / `elbowpad05-07` | 0 / 1 | newest package / own package |
| 78, 79 / 83 | `wristband01, 02` / `wristband09` | 0 / 1 | newest package / own package |
| 91 | `socks00` | 1 | own package |

Only the 634 uniform packages carry `shoes01..04`, `glove01..04`,
`elbowpad01..04`, `longsleeve01..02`, `wristband01..02` (all TSET chunks
4-10; the global pack outer 3 has `shoes_taped`, `elbowpad_rubber/elastic/
taped`, `wristband_qb`, `bump_shoes1..7` and no `shoes0N`; checked against
`reports/assets/nfl2k5_resource_chunks_v2.json` and a decode of outer 3 / 346
TSETs). Therefore:

* **In a game** every player on both teams wearing Style 1/2/4/5 samples the
  AWAY package's copy (`<away code>a<style>.iff`, chunk 8/9). The HOME
  package's copy is never sampled for those rows.
* **On the Edit Player screen** the preview samples the viewed team's `h0`
  (or `a0`) package because it is the only uniform package loaded.
* That is exactly maumau78's screen: he edited a home package (the preview
  model's `h0`), so the preview showed the orange shoe and the game (reading
  the opponent's `a<style>` package, or his own `a` package when away) did not.
* Style 3 (`shoes09`) and Style 6 (`shoes10`) really are per package; imports
  of those were already correct.

The retail art is not identical across packages (chunk 8 has 66 distinct
retail spans across 634 packages; `shoes01` has 66 distinct pixel/palette
combinations), so "whichever package loaded last" is a real visible rule, not
a harmless one.

## 3. Root cause (file:line, pre-fix tree)

`mod_editor/core/nfl2k5_equipment_import.py:57-62` staged the import as
`session.replace_batch(((asset, staged),))`: one replacement entry for the
selected `tset:<outer>:<chunk>:<ref>:<name>` only. The writer
(`nfl2k5_uniform_equipment_writer.py`) and the catalog model every equipment
texture as package-local, which is true for the context-first rows and false
for the global rows the game reads from the newest package. No component knew
which package the game samples.

## 4. The fix

No protected file was edited; no `WIRING.md` change is needed.

1. `mod_editor/core/nfl2k5_uniform_equipment_writer.py`
   * `BINDING_TABLE_ROWS`, `GLOBAL_LOOKUP_NAMES`, `CONTEXT_FIRST_NAMES`,
     `SHOE_STYLE_NAMES`: the binding table knowledge above, documented at the
     top of the module with the addresses.
   * `in_game_lookup(name)`, `sampled_package(selector)`,
     `consumer_targets(target, by_id)`: a context-first name resolves to the
     selected package; a global name resolves to the selected package plus
     every package the game can bind it from: all 317 `<code>A<style>`
     packages (any of them can be the AWAY context) and the 85 `<code>H0`
     packages (the only packages the front-end preview loads). Other home
     styles are never the newest uniform context anywhere, so they are not
     staged unless selected.
   * `EquipmentCompileCache` + `compile_cache=` on
     `build_unified_uniform_equipment_imports`: the compile is split into a
     per-span core (`_compile_group`, keyed by template span SHA-256, chunk
     header, catalog rows and the authored RGBA/mode/scale) and a per-package
     envelope (asset IDs, set selector, preview names, pack offset, hashes).
     Identical retail spans receiving identical artwork compile once; the
     output bytes and receipts are identical to the uncached path. Nothing is
     cached without an explicit cache object (tests that patch the compressor
     keep failing the way they expect).
   * `_rebuild_fixed_span`: a palette-only edit still uses the retail greedy
     transport first (byte-identical spans and receipts for everything that
     fit before). When that overflows, it takes the bounded lossless route the
     own-texture import already uses (retail-observed 10/11/12/13-bit
     geometries, minimum-bit-cost token parse, full decode-and-compare). This
     was needed by the fan-out itself: Tennessee `17H0` chunk 8 (55,776 stored
     / 55,772 consumed, 13-bit distances, byte-identical in 91 packages) has
     its sibling palettes matched against `shoes01`'s, so replacing that one
     palette grows the greedy stream by 19-246 bytes whatever the palette
     budget ("cannot fit ... even with a two-colour palette" from the first
     real build). The optimal parse fits it with 513 bytes to spare at the
     full 34-colour budget.
   * Pack-extent guard: three packages straddle two pack files (`01H11`
     outer 3625, `25H3` 3832, `24A10` 4136). The writer used to refuse the
     whole package; it now refuses only a span that crosses the seam and
     writes a span that lies inside one extent at its real pack offset
     (`24A10` chunk 8 -> pack `B` offset 457,930,128, bytes verified against
     the template hash). `24A10` is an away package and therefore a sampled
     copy; every sampled copy of every global row lies inside one extent
     (retail-gated test).
2. `mod_editor/core/nfl2k5_equipment_import.py`
   * `stage_equipment_import` resolves the consumer set, keeps the existing
     preflight (the selected package's TSET with its staged siblings), and
     stages one `replace_batch` with the selected frozen PNG plus, for every
     other consumer package, a canonical re-encode of the same decoded pixels
     carrying its own explicit texture choice (`npTC` intent names the copy's
     asset ID). One undo action. Importing the original pixels restores every
     staged copy. The receipt gains `consumers` (schema
     `nfl2k5_equipment_consumer_fanout/v1`: lookup kind, the rule, the XBE
     evidence, package counts, every consumer and staged asset ID). The
     message says where it went, e.g. "In a game every player wearing this
     style uses the away team's package copy, so it was staged into all 402
     uniform packages (317 away, 85 home Current Uniform)."
   * `revert_equipment_import(session, asset)`: reverts every staged copy of
     the variant as one undoable transaction.
   * `EquipmentImportResult.consumer_asset_ids` (new, defaulted).
3. `mod_editor/studio/facade.py::revert_asset`: equipment assets revert
   through the consumer set ("Reverted X and the same texture in 401 other
   uniform packages.").
4. `mod_editor/core/nfl2k5_extended_visual_io.py::_decode_uniform_equipment`:
   a bounded per-session cache keyed by the retail span hash (decode each
   distinct span once). First import of a global variant fell from 82 s to
   34 s on the real catalog; a repeat import is 5 s; save 0.7 s, load 1.3 s,
   revert 1.7 s.
5. `tools/nfl2k5_visual_mod_project.py`: one `EquipmentCompileCache` per
   build passed to every equipment group.
6. `docs/mod_editor/2k5_mod_studio_getting_started.md`: the rule, in plain
   words, under the 45-equipment-texture paragraph.
7. `tests/mod_editor/test_nfl2k5_equipment_texture_chain.py`: the synthetic
   fixture accepts explicit names and its segments carry a size.
8. Pins: `python3 packaging/repin.py --apply` updated 5 pins
   (`providers.py` x4 for the writer, the visual IO, the visual project
   backend; `check_2k5_mod_studio_runtime.py` for the facade). Claude:
   the cave reservation manifest does not change (no executable writer was
   touched), but the provider/runtime pins did, so regenerate whatever
   release-side manifest lists those hashes.

What the fix does not do: it does not change the executable. A 14-dword
`.rdata` flip of the context-first words at `0x004EEAF8 + row*8 + 4` for the
global rows would make every generic variant team-specific (and make the
Edit Player preview and the game agree per team), but it changes retail
rendering for untouched packages, conflicts with the hi-res pack's pinned
`(0x004EEAF8, 768)` consumer range, and needs BuildPlan wiring in the
protected `mod_build.py`. That is a feature decision for Noah, not a hotfix;
the offsets are recorded here if he wants it.

Costs, measured on the real packs: staging Style 1 shoes for one team creates
402 replacement entries (the same 26 KB canonical PNG each for flat art; a
photo-like shoe would be ~100 KB each, so up to ~40 MB per style in a
project); a build compiles 66 distinct spans and reuses them for the other
336 packages (238 s for the 402 groups in a standalone measurement, one of
them through the optimal parse).

## 5. Tests

All run from the worktree root with `PYTHONPATH=$PWD QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/<file>.py`
(the three older suites below add `:$PWD/tools`, as they always did).

Regression test (red before, section 1; green after):

```
$ python3 tests/mod_editor/test_nfl2k5_equipment_consumers.py
.................
----------------------------------------------------------------------
Ran 17 tests in 13.937s

OK
```

The 17 tests: retail-gated (`default.xbe`) pins of every evidence range,
row-by-row classification of the 96-row table against
`BINDING_TABLE_ROWS`/`GLOBAL_LOOKUP_NAMES`, the shoe style table, the
`TEST/JZ`, `XOR ECX,ECX`, head-insert and HOME/AWAY/`%sh0.iff` bytes;
catalog-only consumer resolution (402 = 317 away + 85 H0 for every global
name incl. `_mud`, 403 when an alternate home package is selected, 1 for every
context-first name); a synthetic four-package archive through the real
`StudioSession` + facade (fan-out, alternate home package, team-specific
variant, own-texture intent per copy, restore + revert + undo, repeat import
no-op, second style); the compile cache (hit/miss, identical bytes, per-package
envelope); retail-gated (pack index) shared-span reuse with reparse of every
output, the `17H0` tight-slot fallback with reparse and both loader guards, and
the straddling-package extent proof.

Suites touching the changed modules:

```
test_nfl2k5_equipment_import: OK            (11 tests)
test_nfl2k5_equipment_texture_chain: OK     (16 tests)
test_nfl2k5_equipment_import_wiring: OK     (6 tests)
test_player_assets: OK
test_uniform_sharing: OK
test_2k5_uniform_equipment_export: OK (skipped=4)
test_nfl2k5_extended_visuals: OK
test_studio_session: OK
test_team_kit_product_integration: OK
test_all_texture_lane: OK (skipped=13)
test_provider_integrity: OK
test_providers: OK
test_phase1_packaging: OK
test_stage_release: staged 2 files; 0 declared inputs absent
```

XBE gates `test_xbe_patch_memory_writes.py` / `test_xbe_patch_cave_references.py`:
not run; no executable writer or cave was touched (resource data only).

Real-session proof (scratch harness, retail index read-only, real catalogs):

```
asset: Shoes 01 — Tennessee Titans Home uniform_equipment_texture 256 256
stage: 34.1 s; changed=402 modified=True
message: Equipment recolour is ready to build. In a game every player wearing this style uses the away team's package copy, so it was staged into all 402 uniform packages (317 away, 85 home Current Uniform).
consumers: global {'away': 317, 'home_current': 85, 'selected_only': 0} 402
edits staged: 402
save: 0.7 s size=0.2 MB
load: 1.3 s edits=402
repeat: 5.3 s changed=0
revert: 1.7 s reverted=402 left=0
undo restores: 402
```

Real build of that 402-edit project with `tools/nfl2k5_visual_mod_project.py build`
(retail XISO as source, output in scratch, deleted afterwards):

```
NFL2K5_VISUAL_MOD_BUILD_PASS edits=402 changed=6422383 sha256=9c9e0677235c2af6b949bb4c3625d8d4e50c724481e29650bf1a57d85afc3d69 runtime=false
real 5m6.104s   user 4m21.481s   sys 0m28.810s
```

Manifest: 402 non-overlapping spans (22,204,032 selected bytes, 6,422,383
changed), every byte outside the spans identical, targets in packs `9` (2),
`A` (24), `B` (266) and `C` (110); 311 spans through the retail greedy
transport, 91 (the `17H0` family) through the optimal parse, all 402 at the
full 256-colour budget (34 palette entries). Spans re-read from the output
image and decoded: `24A10` (`4136:8`, pack B, 12-bit, 54,670/54,944), `17H0`
(`3753:8`, 13-bit, 55,263/55,776), `28H0` (`3850:8`, 12-bit, 54,453/54,688),
each matching its manifest hash. The first build attempt, before the
lossless fallback and the extent fix, refused with "cannot fit inside the
retail 55,776-byte TSET even with a two-colour palette" and "package crosses
pack extents and is read-only"; both are covered by the retail-gated tests
now.

## 6. What Noah must witness in xemu

1. Load the retail disc, pick any team, import a clearly different Style 1
   shoe (`Shoes 01`) for that team's home Current Uniform. The message must
   say 402 packages. Build.
2. Edit Player for that team: Right/Left Shoe Style 1 shows the design on the
   preview (as before). Edit Player for another team: the preview also shows
   it (that is the game reading the same league-wide row).
3. Play a game as that team at home and as the away team: every player on
   both sides with Style 1 shoes wears the design; Styles 3 and 6
   (`shoes09`/`shoes10`) stay stock. This is the claim the fix makes and
   nothing offline can show it.
4. Set a player to Style 2 (`shoes04`) and Style 4 (`shoes02`) without
   importing them: stock. Import a `Shoes 04`: same fan-out, same check.
5. Revert the shoe from any package in All Textures: the message says 401
   others were reverted; rebuild shows stock shoes.
6. Try a team whose away package has the tight `17H0`-family span (Tennessee
   current home is one; the receipt names `optimal_token_parse` for those
   91 packages) and confirm the shoes load and look right close up and at
   distance, since that transport is new for palette-only edits.
7. A muddy game (`_mud` rows follow the same rule): the dirty shoe stays
   stock unless `Shoes 01 — Mud` was imported too.

ASTRA_DONE
