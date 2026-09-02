# §6.1 editor bug fix-or-wall ledger (2026-08-07)

Living tracker. “Fixed” requires a test driving shipped entry points. “Wall”
requires an unblock path. Capability honesty: never mark Editable without
offline-writer-proved or better.

| # | Item | Status | Evidence / path |
| --- | --- | --- | --- |
| 1 | logo_l0/l1 PNG format 15 | **Fixed** (beta-27) + regression suite | `tools/apf_inner.py` format 15; `tests/apf_logo_patch_test.py`, `tests/mod_editor/test_apf_logo_patch.py`, `tests/mod_editor/test_apf_xenos_4444_png.py` |
| 2 | Blank previews forever | **Fixed fail-closed; decoder-specific wall** | **45s preview watchdogs** on AssetBrowser, Uniform, Wordmark, digital_font, Team Logo crest, Field Art, stadium package + embedded prevent a perpetual spinner. A decoder-specific blank now needs the exact `asset_id`, outer/inner index, format ID, workspace, and resulting message before another code path can be authorized. |
| 3 | Nameplate gibberish | **Fixed** (2026-08-07) | Root cause: APF `font_albedo`/`font_normal` are **base-only DXN** (`packed_mips=False`, `mip_max=0`, non-pow2 widths e.g. 1681×128). Helmet DXN path required `packed_mips=True`. Shipped `derive_base_only_layout` in `tools/apf_xenos_dxn_mip_layout.py`. Asset IDs: NameFont outers `114,283,504,538,609,640,937,956,963,1312,1383` (`font_albedo` inner0, `font_normal` inner1, `font_metric` NameFont). Tests: `test_apf_dxn_base_only_namefont.py` (22/22 real-dump previews). Note: DXN preview is dual-channel RG (B=0,A=255) — glyphs visible, not single-channel grayscale. |
| 4 | Auto-resize import | **Fixed** | `mod_editor/core/image_fit.py` contain/cover/stretch; 2K5 `_fit_for_slot` + APF `_prepare_slot_image` shared dialog/drop; `test_2k5_import_offers_resize`, `test_image_fit`, `test_apf_import_offers_resize` |
| 5 | Facemask per uniform set | **Fixed** (APF + 2K5) | APF Equipment Colors HOME/AWAY per team + Stage never silent-gray; 2K5 Unif per physical set + facemask/turtleneck/Apply never silent-gray; tests equipment GUI + unif ARGB |
| 6 | Titans arm/shoulder numbers missing in preview | **Fixed known catalog; unknown-asset wall** | **APF:** all 24×`number_0_color`…`number_9_color` decode 512×512 RGBA and All Textures teaches those names. **2K5:** Titans 32×32 arm/shoulder digits are covered by the live-number catalog. A remaining blank requires product/version, team, `asset_id`, outer/inner index, format ID, and screenshot/error text; without that target there is no safe byte span to patch. |
| 7–8 | Team kits / All Textures export errors | **Explicit repro wall** | No current asset ID reproduces the historical screenshots. Unblock with product/version, loaded-source type, workspace, selected `asset_id`, outer/inner index, requested export action, and full error/log text. The existing path must then gain a regression test that drives the shipped facade/asset I/O entry point; no generic writer expansion is authorized from a screenshot alone. |
| 9 | ISO load any-rip | **Fixed class (Beta 30)** | Layout-tolerant extraction remains covered by `test_apf_iso_extraction_is_layout_tolerant` and `test_xiso_layout_tolerance`. 2K5 RC57 also binds Stadium, visual, Crib, and audio-derived cache data to the independently validated game content rather than container padding/layout, and parses containment against the actual opened image size. |
| 8b | Field art stock NFL | **Wall + labeled** | `APF_FIELD_ART_STOCK_NFL_WALL.md`; inventory has stock; writer is 6 proved slots |
| 9b | Team color editor crash | **Fixed current path** | 2K5 unif colour failures stay **inline** (no modal popup on set select); ARGB parse fail-closed (`_argb_to_qcolor`); empty filter teaches instead of crashing. APF equipment read errors are also inline. Tests: `test_unif_color_argb_parse`, equipment GUI suite. |
| 10 | Gray model import | **Fixed** | APF player/helmet model panel + **APF Stadium mesh** Import/Export + wordmark Import/Export always clickable + disableReason; 2K5 Crib + Stadium Import/Export click-to-explain (never silent gray) |
| 11 | Windows path/installer | **Fixed current release; permanent CI gate** | `platform_compat`, layout-tolerant extraction, embeddable-CPython path handling, O_BINARY, and deterministic NSIS are covered by platform/installer tests. The per-file GitHub matrix on Windows/macOS/Linux is a release gate; a future regression is not an open RC57 feature. |
| 12 | PS3 ISO mis-ID | **Fixed class** | structural ID + clear refuse; keep probes |
| 13 | Helmet shell default path | **Fixed UI; runtime-material wall** | Team Logos recommends Full-shell + Normal logo and an opaque α255 body, explicitly naming the old `0x88` translucency defect. A broader runtime/material claim requires a matched stock-vs-built Xenia capture for the same team, camera, lighting, and source hash. |
| 14 | Eagles shell accuracy | **Explicit runtime wall** | The v30 whole-shell volume and static placement gates exist. Close only after a matched front-crown/side/rear Xenia witness identifies team, logo slot, shell mode, source hash, build hash, camera, and lighting; without that evidence another placement change would be guesswork. |
| 15 | Remaining PORTME formats | **Fixed for known community-critical catalog; unseen-format wall** | PNG preview covers 8, 1_5_5_5, 5_6_5, 8_8_8_8, 8_8, 4_4_4_4, DXT1/2_3/4_5, DXN (helmet + base-only namefont), format-32 cubemap face-0, and linear uncompressed/DXT. Non-face0 cubemap data and any unseen DXT3A/exotic Xenos format stay actionable raw-export refusals. Unblock requires a real catalog `asset_id`, header/format ID, dimensions/mips, and consumer; no current logo/nameplate/kit-number row depends on one. |
| 16 | Socks / equipment hard to find | **Fixed** | Team Kit **Browse 45 Equipment Textures** opens the canonical set-filtered All Textures rows; `test_2k5_uniform_equipment_export.py` pins the route and label. |
| 17 | Menu logos vs in-game logos | **Fixed** | Getting Started and catalog labels separate live helmet art, Team Select cards, and Team Presentation — Menu/UI resources; all reuse canonical asset IDs and handlers. |
| 18 | Nameplates / numbers-sheet workflow | **Fixed bounded workflow; cross-game split wall** | 634 1024×32 nameplate atlases and 19,020 digit targets use exact-size import with shared Contain/Cover/Stretch handling and writer verification. Automatic conversion of an arbitrary 2K27 sheet is blocked until its source manifest/UV mapping is supplied; repeated PNGs without that map cannot authorize a split. |
| 19 | ISO false rejects | **Fixed current class (Beta 30)** | Hash/size-independent XDVDFS recognition and layout-tolerant extraction are covered by `test_xiso_layout_tolerance` and any-rip probes. RC57 adds shared-cache regressions for alternate valid container identities, plus actual-size containment and build-result coverage. APF alpha.62 revalidates its normal read-only load path against a real USA ISO without publishing private source details. |
| 20 | Uniform colour read failures | **Fixed current path** | Bad/empty ARGB values fail closed inline without modal spam; `test_unif_color_argb_parse.py` and uniform-control tests cover the shipped GUI path. |
| GH#2 | Stock playbooks | **Shipped bounded editor incl. authorized create/link + explicit runtime/freehand wall** | Browser, route copy, clone, broken-play annotations, community legend, empty-state teaching, G1 multi-Dime and G2 multi-Ace offline packs ship. Freehand inverse compilation and runtime G1/G2 behavior remain unproved and are labeled; emulator evidence is required before a one-click gameplay-fix claim. |

Residual risks: G1/G2 **runtime** unproved (offline writers proved for bytes);
freehand inverse compiler not Editable; STFS resign external; monorepo pytest
order-dependent hang residual (use batched suites); interactive Xenia validation
remains pending.

### Never-silent-gray expansion (continuation 2026-08-08)

Closed or substantially reduced silent-gray on:
- APF: text Apply/Revert, Text Sheet, ratings sheet, player rating/position Apply/Revert,
  bulk audio catalog/banks, Export matching, Export decoded rows, Custom Team Write-raw
- 2K5: Text & Rosters (string + current + historical), Audio Export matching, Load waveform,
  shortlist bulk, Gameplay Inspector exports

Residual intentional locks: cancel-in-flight, busy workers, pagination arrows without
page, some form field enables (inputs, not action buttons).

### Never-silent-gray expansion wave (2026-08-08 continuation, late)

Additional product surfaces closed (construction + runtime disableReason + teach):

**APF:** text Apply/Revert (incl. construction), Text Sheet, ratings sheet, player
rating/position, roster identity Replace/Revert, bulk audio catalog/banks, Export
matching, Export decoded rows, Play, PCM/XMA replace+revert, Soundtrack album,
Stadium Reset View + Export scene, Team Logo master, Custom Team Write-raw,
uniform/wordmark/All Textures Revert, reserve Assign/Clear construction.

**2K5:** Text & Rosters (string + current + historical, construction), Audio Export
matching, Load waveform (full selection path), shortlist bulk+toggle+clear+move,
replacement template Export/Import, row Play/Export/Replace/Revert, Gameplay
Inspector exports, visual master construction.

Residual intentional locks: cancel-in-flight, busy workers, pagination, form
fields (inputs), ratings-sheet import dialog Apply until conflicts cleared.

### Never-silent-gray expansion wave (2026-08-08 late continuation)

- **2K5 Menus Export JSON/CSV** — never silent-gray when named map fails
- **2K5 Export Number** (current + historical roster) — never silent-gray
- **2K5 Stadium texture** Export/Replace/Revert — never silent-gray at construction
- **APF Place on helmet** — retail coverage teaches Full-shell-only (no silent gray)
- **APF helmet placement Save** — out-of-canvas stays clickable; accept re-validates

### Wall evidence contract

“Wall” is not shorthand for “later.” For a user-specific texture/export report,
the minimum unblock bundle is product/version, legal-source structure, workspace,
canonical `asset_id`, outer/inner index where applicable, format/dimensions/mips,
the exact action, and full error/log text. Runtime visual walls additionally need
matched source/build hashes and controlled captures. Retail payload bytes never
belong in the repository or issue attachment.

### Never-silent-gray expansion (2026-08-08 late-2)

- 2K5 Menus Export; Export Number; Stadium boot; Audio/All Resources pagination
- APF Field Art Stock NFL endzones button; Place/Save; All Textures pagination
- APF Complete audio pagination + export_rows disableReason clear
- Playbooks **G1: Use Nickel donor** helper
- XMA1 wizard Save/Test never silent-gray
