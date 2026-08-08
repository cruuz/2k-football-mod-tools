# §6.1 editor bug fix-or-wall ledger (2026-08-07 marathon)

Living tracker. “Fixed” requires a test driving shipped entry points. “Wall”
requires an unblock path. Capability honesty: never mark Editable without
offline-writer-proved or better.

| # | Item | Status | Evidence / path |
| --- | --- | --- | --- |
| 1 | logo_l0/l1 PNG format 15 | **Fixed** (beta-27) + regression suite | `tools/apf_inner.py` format 15; `tests/apf_logo_patch_test.py`, `tests/mod_editor/test_apf_logo_patch.py`, `tests/mod_editor/test_apf_xenos_4444_png.py` |
| 2 | Blank previews forever | **Mitigated** | Cache rebuild; PORTME list; **45s preview watchdogs** on AssetBrowser, Uniform, Wordmark, digital_font, Team Logo crest, Field Art, stadium package + embedded. Residual races need asset_id repro. |
| 3 | Nameplate gibberish | **Fixed** (2026-08-07) | Root cause: APF `font_albedo`/`font_normal` are **base-only DXN** (`packed_mips=False`, `mip_max=0`, non-pow2 widths e.g. 1681×128). Helmet DXN path required `packed_mips=True`. Shipped `derive_base_only_layout` in `tools/apf_xenos_dxn_mip_layout.py`. Asset IDs: NameFont outers `114,283,504,538,609,640,937,956,963,1312,1383` (`font_albedo` inner0, `font_normal` inner1, `font_metric` NameFont). Tests: `test_apf_dxn_base_only_namefont.py` (22/22 real-dump previews). Note: DXN preview is dual-channel RG (B=0,A=255) — glyphs visible, not single-channel grayscale. |
| 4 | Auto-resize import | **Fixed** | `mod_editor/core/image_fit.py` contain/cover/stretch; 2K5 `_fit_for_slot` + APF `_prepare_slot_image` shared dialog/drop; `test_2k5_import_offers_resize`, `test_image_fit`, `test_apf_import_offers_resize` |
| 5 | Facemask per uniform set | **Fixed** (APF + 2K5) | APF Equipment Colors HOME/AWAY per team + Stage never silent-gray; 2K5 Unif per physical set + facemask/turtleneck/Apply never silent-gray; tests equipment GUI + unif ARGB |
| 6 | Titans arm/shoulder numbers missing in preview | **Mitigated / labeled** | **APF:** all 24×`number_0_color`…`number_9_color` decode 512×512 RGBA (outers with full digit sets; not under shoulder family — jersey numbers live as `number_N_color` TXTR). All Textures search tooltip teaches this explicitly. **2K5:** Titans 32×32 arm/shoulder digits already fixed RC era. Residual: if a specific team still blanks, capture `asset_id` + format. |
| 7–8 | Team kits / All Textures export errors | **Wall residual** | Repro with user asset_id; many writers already fail closed with message |
| 9 | ISO load any-rip | **Fixed class** | layout-tolerant extract; tests `test_apf_iso_extraction_is_layout_tolerant`, `test_xiso_layout_tolerance` |
| 8b | Field art stock NFL | **Wall + labeled** | `APF_FIELD_ART_STOCK_NFL_WALL.md`; inventory has stock; writer is 6 proved slots |
| 9b | Team color editor crash | **Mitigated** | 2K5 unif colour failures stay **inline** (no modal popup on set select); ARGB parse fail-closed (`_argb_to_qcolor`); empty filter disables colour buttons. APF equipment read errors also inline. Tests: `test_unif_color_argb_parse`, equipment GUI suite. |
| 10 | Gray model import | **Fixed** | APF player/helmet model panel + **APF Stadium mesh** Import/Export + wordmark Import/Export always clickable + disableReason; 2K5 Crib + Stadium Import/Export click-to-explain (never silent gray) |
| 11 | Windows path/installer | **Ongoing class** | `platform_compat`, beta-5..12 lessons; keep matrix tests green |
| 12 | PS3 ISO mis-ID | **Fixed class** | structural ID + clear refuse; keep probes |
| 13 | Helmet shell default path | **Mitigated** | Team Logos UI recommends Full-shell + Normal logo; opaque shell body α255 taught in blurb/tooltip (0x88 translucency defect named). Runtime Xenia witness still partial. |
| 14 | Eagles shell accuracy | **Partial** | v30 volume; close-up witness pending (handoff) |
| 15 | Remaining PORTME formats | **Improved** | PNG preview: 8, 1_5_5_5, 5_6_5, 8_8_8_8, 8_8, 4_4_4_4, DXT1/2_3/4_5, DXN (helmet + base-only namefont), **format-32 cubemap face-0**, **linear untiled uncompressed + linear DXT1/2_3/4_5**. Residual: other cubemap faces/mips raw-export; DXT3A if any; exotic Xenos formats. |
| 16–20 | 2K5 community discoverability | **Partial** | Equipment browse, menu logos labeled in README/changelog; continue polish |
| GH#2 | Stock playbooks | **Partial** | Browser + route copy + clone + **broken-play annotations** + community legend + empty-flagged teaching + G1 Dime→Nickel donor tip; freehand wall; G1/G2 runtime unproved |

Residual risks: G1/G2 **runtime** unproved (offline writers proved for bytes);
freehand inverse compiler not Editable; STFS resign external; monorepo pytest
order-dependent hang residual (use batched suites); hour gate multi-session;
no interactive Xenia in this run.

### Never-silent-gray expansion (continuation 2026-08-08)

Closed or substantially reduced silent-gray on:
- APF: text Apply/Revert, Text Sheet, ratings sheet, player rating/position Apply/Revert,
  bulk audio catalog/banks, Export matching, Export decoded rows, Custom Team Write-raw
- 2K5: Text & Rosters (string + current + historical), Audio Export matching, Load waveform,
  shortlist bulk, Gameplay Inspector exports

Residual intentional locks: cancel-in-flight, busy workers, pagination arrows without
page, some form field enables (inputs, not action buttons).

