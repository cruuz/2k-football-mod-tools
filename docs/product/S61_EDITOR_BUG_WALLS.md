# §6.1 editor bug fix-or-wall ledger (2026-08-07 marathon)

Living tracker. “Fixed” requires a test driving shipped entry points. “Wall”
requires an unblock path. Capability honesty: never mark Editable without
offline-writer-proved or better.

| # | Item | Status | Evidence / path |
| --- | --- | --- | --- |
| 1 | logo_l0/l1 PNG format 15 | **Fixed** (beta-27) + regression suite | `tools/apf_inner.py` format 15; `tests/apf_logo_patch_test.py`, `tests/mod_editor/test_apf_logo_patch.py`, `tests/mod_editor/test_apf_xenos_4444_png.py` |
| 2 | Blank previews forever | **Mitigated / wall residual** | Cache rebuild on corrupt PNG in `asset_io.preview_texture`; remaining races need repro fixture — unblock: capture hung asset_id + format |
| 3 | Nameplate gibberish | **Fixed** (2026-08-07) | Root cause: APF `font_albedo`/`font_normal` are **base-only DXN** (`packed_mips=False`, `mip_max=0`, non-pow2 widths e.g. 1681×128). Helmet DXN path required `packed_mips=True`. Shipped `derive_base_only_layout` in `tools/apf_xenos_dxn_mip_layout.py`. Asset IDs: NameFont outers `114,283,504,538,609,640,937,956,963,1312,1383` (`font_albedo` inner0, `font_normal` inner1, `font_metric` NameFont). Tests: `test_apf_dxn_base_only_namefont.py` (22/22 real-dump previews). Note: DXN preview is dual-channel RG (B=0,A=255) — glyphs visible, not single-channel grayscale. |
| 4 | Auto-resize import | **Fixed** | `mod_editor/core/image_fit.py` contain/cover/stretch; 2K5 `_fit_for_slot` + APF `_prepare_slot_image` shared dialog/drop; `test_2k5_import_offers_resize`, `test_image_fit`, `test_apf_import_offers_resize` |
| 5 | Facemask per uniform set | **Fixed** (APF + 2K5) | APF Equipment Colors HOME/AWAY per team; 2K5 Unif per physical set; tests `test_apf_uniform_equipment_colors*`, `test_nfl_uniform_colour_records` |
| 6 | Titans arm/shoulder numbers missing in preview | **Mitigated / labeled** | **APF:** all 24×`number_0_color`…`number_9_color` decode 512×512 RGBA (outers with full digit sets; not under shoulder family — jersey numbers live as `number_N_color` TXTR). **2K5:** Titans 32×32 arm/shoulder digits already fixed RC era (`2k5_mod_studio_changelog`). Residual: UI discoverability — numbers appear under All Textures / kit number slots, not shoulder material. Unblock if a specific team still blanks: capture `asset_id` + format. |
| 7–8 | Team kits / All Textures export errors | **Wall residual** | Repro with user asset_id; many writers already fail closed with message |
| 9 | ISO load any-rip | **Fixed class** | layout-tolerant extract; tests `test_apf_iso_extraction_is_layout_tolerant`, `test_xiso_layout_tolerance` |
| 8b | Field art stock NFL | **Wall + labeled** | `APF_FIELD_ART_STOCK_NFL_WALL.md`; inventory has stock; writer is 6 proved slots |
| 9b | Team color editor crash | **Wall** | Need stack trace from 2026-08-05 report; APF equipment panel has focused tests |
| 10 | Gray model import | **Fixed** | APF model panel tooltips when disabled; 2K5 stadium import tooltips with reason |
| 11 | Windows path/installer | **Ongoing class** | `platform_compat`, beta-5..12 lessons; keep matrix tests green |
| 12 | PS3 ISO mis-ID | **Fixed class** | structural ID + clear refuse; keep probes |
| 13 | Helmet shell default path | **Partial** | v25 opaque + v30 native-material; recommend path in shell UI; runtime witness partial |
| 14 | Eagles shell accuracy | **Partial** | v30 volume; close-up witness pending (handoff) |
| 15 | Remaining PORTME formats | **Improved** | PNG preview: 8, 1_5_5_5, 5_6_5, 8_8_8_8, 8_8, 4_4_4_4, DXT1/2_3/4_5, DXN (helmet + **base-only namefont**). Format **32** = cubemap lightmaps (`SpecularLightBox` etc., dimension=3, ~48 B/texel=6×8) — honest cubemap PORTME msg; face preview still wall. Some DXT5A digital_font tiled-allocation edges remain. |
| 16–20 | 2K5 community discoverability | **Partial** | Equipment browse, menu logos labeled in README/changelog; continue polish |
| GH#2 | Stock playbooks | **Partial** | Browser + route copy + clone + **broken-play annotations**; freehand wall |

Residual risks: G-series offline package writers unproved; freehand inverse
compiler not Editable; STFS resign external; no interactive Xenia in this run.
