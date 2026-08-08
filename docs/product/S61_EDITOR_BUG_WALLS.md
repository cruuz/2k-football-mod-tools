# §6.1 editor bug fix-or-wall ledger (2026-08-07 marathon)

Living tracker. “Fixed” requires a test driving shipped entry points. “Wall”
requires an unblock path. Capability honesty: never mark Editable without
offline-writer-proved or better.

| # | Item | Status | Evidence / path |
| --- | --- | --- | --- |
| 1 | logo_l0/l1 PNG format 15 | **Fixed** (beta-27) + regression suite | `tools/apf_inner.py` format 15; `tests/apf_logo_patch_test.py`, `tests/mod_editor/test_apf_logo_patch.py`, `tests/mod_editor/test_apf_xenos_4444_png.py` |
| 2 | Blank previews forever | **Mitigated / wall residual** | Cache rebuild on corrupt PNG in `asset_io.preview_texture`; remaining races need repro fixture — unblock: capture hung asset_id + format |
| 3 | Nameplate gibberish | **Partial / wall** | 2K5 linear P8 nameplate fix path exists (`ce3f44e` era); APF nameplates use fonts/digital_font — confirm format IDs with disc slice; PORTME message names format |
| 4 | Auto-resize import | **Fixed** | `mod_editor/core/image_fit.py` contain/cover/stretch; 2K5 `_fit_for_slot` + APF `_prepare_slot_image` shared dialog/drop; `test_2k5_import_offers_resize`, `test_image_fit`, `test_apf_import_offers_resize` |
| 5 | Facemask per uniform set | **Fixed** (APF + 2K5) | APF Equipment Colors HOME/AWAY per team; 2K5 Unif per physical set; tests `test_apf_uniform_equipment_colors*`, `test_nfl_uniform_colour_records` |
| 6 | Titans arm/shoulder numbers missing in preview | **Wall** | Need asset catalog IDs for Titans kit numbers + format; unblock: preview decode for that format or fail with format ID |
| 7–8 | Team kits / All Textures export errors | **Wall residual** | Repro with user asset_id; many writers already fail closed with message |
| 9 | ISO load any-rip | **Fixed class** | layout-tolerant extract; tests `test_apf_iso_extraction_is_layout_tolerant`, `test_xiso_layout_tolerance` |
| 8b | Field art stock NFL | **Wall + labeled** | `APF_FIELD_ART_STOCK_NFL_WALL.md`; inventory has stock; writer is 6 proved slots |
| 9b | Team color editor crash | **Wall** | Need stack trace from 2026-08-05 report; APF equipment panel has focused tests |
| 10 | Gray model import | **Fixed** | APF model panel tooltips when disabled; 2K5 stadium import tooltips with reason |
| 11 | Windows path/installer | **Ongoing class** | `platform_compat`, beta-5..12 lessons; keep matrix tests green |
| 12 | PS3 ISO mis-ID | **Fixed class** | structural ID + clear refuse; keep probes |
| 13 | Helmet shell default path | **Partial** | v25 opaque + v30 native-material; recommend path in shell UI; runtime witness partial |
| 14 | Eagles shell accuracy | **Partial** | v30 volume; close-up witness pending (handoff) |
| 15 | Remaining PORTME formats | **Ongoing** | PORTME message includes format id/name in `apf_inner` |
| 16–20 | 2K5 community discoverability | **Partial** | Equipment browse, menu logos labeled in README/changelog; continue polish |
| GH#2 | Stock playbooks | **Partial** | Browser + route copy + clone + **broken-play annotations**; freehand wall |

Residual risks: G-series offline package writers unproved; freehand inverse
compiler not Editable; STFS resign external; no interactive Xenia in this run.
