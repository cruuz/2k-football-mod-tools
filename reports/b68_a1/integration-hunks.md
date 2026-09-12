# Integrator-only hunk inventory

T1: bundle tip `7d139852` → integration `a8676133`. T2: automatic merge tree of `a8676133` and bundle tip `d50b1abf` → `925c5da6`; conflict markers in the reconstructed tree expose the two actual conflict resolutions. Full raw T2-vs-bundle diff is retained separately so inherited T1 changes are not misattributed.

| Hunk | File / applied location | Verdict | Judgment / fix |
|---|---|---|---|
| T1-01 | `ASTRA_B68_T1_REPORT.md` | clean | Report renamed byte-for-byte; no claims changed. |
| T1-02 | `WIRING_B68_T1.md` | clean | Wiring renamed byte-for-byte. |
| T1-03 | `mod_editor/core/providers.py:557` | clean | Exact WIRING compile-cache SHA entry added to the unified provider. Runtime-list omission is D2 below. |
| T1-04 | `packaging/check_2k5_mod_studio_release.py:604` | clean | Exact path-specific helper/C-source exception from WIRING; size, SHA, ELF and 0755 checked; generic refusals retained. |
| T1-05 | `packaging/release-allowlist.txt:839` | clean | Exact three allowlist paths from WIRING; no benchmark/private cache added. |
| T1-06 | `tests/mod_editor/test_phase1_packaging.py:160` | clean | Seven helper acceptance/refusal/pin-agreement tests added. Full class already skips POSIX permission assertions on Windows; no weakening. |
| T1-07 | `tools/setup_reviewed_helpers.py:1` | clean | Setup helper docstring updated for two reviewed files. |
| T1-08 | `tools/setup_reviewed_helpers.py:22` | clean | Reviewed map adds the exact equipment helper size/hash; APF constants retained. |
| T1-09 | `tools/setup_reviewed_helpers.py:41` | clean | normalize accepts only a map key; original default APF call preserved. |
| T1-10 | `tools/setup_reviewed_helpers.py:72` | clean | Descriptor-bound size/hash check parameterized by the reviewed map. |
| T1-11 | `tools/setup_reviewed_helpers.py:90` | clean | Re-read length parameterized; still compares the same bytes on the same descriptor. |
| T1-12 | `tools/setup_reviewed_helpers.py:99` | clean | Receipt names the selected helper; normalize_all and CLI call both in stable order. Source umask 0775 required the documented explicit normalization; staged binary is 0755. |
| T2-01 | `ASTRA_B68_T2_REPORT.md` | clean | Report renamed byte-for-byte. |
| T2-02 | `WIRING_B68_T2.md` | clean | Wiring renamed byte-for-byte. |
| T2-03 | `docs/mod_editor/2k5_mod_studio_changelog.md:4` | clean | Only conflict markers removed; both jobs’ changelog bullets retained. |
| T2-04 | `mod_editor/capabilities/registry.v1.json:10681` | clean | All Textures evidence appends the two tests and renamed report exactly. |
| T2-05 | `mod_editor/capabilities/registry.v1.json:10699` | clean | All Textures own-artwork paragraph matches WIRING exactly. The preceding promise that the original shared indices survive remains true when a private chain is appended. |
| T2-06 | `mod_editor/capabilities/registry.v1.json:10870` | clean | All Visual evidence appends the two tests and renamed report exactly. |
| T2-07 | `mod_editor/capabilities/registry.v1.json:10890` | clean | All Visual equipment paragraph matches WIRING exactly. |
| T2-08 | `mod_editor/capabilities/registry.v1.json:10939` | clean | Bump capability row equals WIRING after report rename and canonical module-form validation_command. Sorted insertion and canonical JSON proved; counts/required runtime lists were missed (D1/D2). |
| T2-09 | `mod_editor/core/providers.py:576` | clean | Conflict keeps T2 import-intent digest and T1 LZ digest. Both match the corresponding merge-result sources at 925c5da6. |
| T2-10 | `mod_editor/gui/bump_panel_qt.py:46` | clean | Exact SHOE_BUMP_NAMES/SHOE_BUMP_SCOPE import. |
| T2-11 | `mod_editor/gui/bump_panel_qt.py:175` | clean | Exact title and scope subtitle from WIRING. |
| T2-12 | `mod_editor/gui/bump_panel_qt.py:228` | clean | Exact Package table heading from WIRING. |
| T2-13 | `mod_editor/gui/bump_panel_qt.py:624` | clean | Exact per-slot scope/distance-image status from WIRING. |
| T2-14 | `mod_editor/gui/bump_panel_qt.py:688` | clean | Exact preflight status including returned scope from WIRING. |
| T2-15 | `mod_editor/gui/bump_panel_qt.py:717` | clean | Exact selected-package/global write confirmation from WIRING. |
| T2-16 | `mod_editor/gui/equipment_texture_import_dialog.py:10` | clean | Dialog imports shared scope resolver and local-shoe help exactly. |
| T2-17 | `mod_editor/gui/equipment_texture_import_dialog.py:24` | clean | Dialog scope controls, global explanation and sock default exactly match WIRING. |
| T2-18 | `mod_editor/gui/equipment_texture_import_dialog.py:76` | clean | Dialog scope property exactly matches WIRING. |
| T2-19 | `mod_editor/gui/studio_qt.py:386` | clean | Facade protocol adds nullable independent and scope arguments exactly. |
| T2-20 | `mod_editor/gui/studio_qt.py:5587` | clean | Dialog result carries independent/scale/scope exactly. |
| T2-21 | `mod_editor/gui/studio_qt.py:5665` | clean | Replacement worker forwards all three arguments exactly. |
| T2-22 | `packaging/check_2k5_mod_studio_runtime.py:99` | clean | Generated studio_qt.py digest matches integrated source; other merged facade pin retained. |
| T2-23 | `tests/mod_editor/test_2k5_uniform_equipment_export.py:255` | clean | Export/resize test facade accepts new scope keyword, keeping its palette writer assertion. |
| T2-24 | `tests/mod_editor/test_2k5_uniform_equipment_export.py:268` | clean | Explicit palette-only dialog stub gains scope; test still exercises the selected palette-only path. |
| T2-25 | `tests/mod_editor/test_nfl2k5_equipment_import.py:231` | clean | Shoe selector moved from invented outer 0 to real catalog 3613; assertions and real dialog preserved. |
| T2-26 | `tests/mod_editor/test_nfl2k5_equipment_import.py:251` | clean | Elbow-pad selector/dimensions corrected to catalog row 3613, 128x64; unsupported own-artwork assertion preserved. |
| T2-27 | `tests/mod_editor/test_nfl2k5_equipment_scope_wiring.py:17` | clean | Scope test imports actual shipped dialog; removes dependency/skip on old WIRING.md, increasing coverage. |
| T2-28 | `tests/mod_editor/test_nfl2k5_equipment_scope_wiring.py:54` | clean | Schema test validates the actual single registered bump row instead of a proposal. |
| T2-29 | `tests/mod_editor/test_product_catalog.py:74` | clean | Expected product IDs adds exactly the new bump capability. |
| T2-30 | `tests/mod_editor/test_product_catalog.py:156` | clean | Unique/stable product count 90 to 91 matches actual registered set. |
| T2-31 | `tests/mod_editor/test_product_catalog.py:190` | clean | Uniform category 5 to 6, editable 4 to 5 matches new writer row. |
| T2-32 | `tests/mod_editor/test_product_catalog.py:228` | clean | Global product count 90 to 91, editable 70 to 71 matches new writer row. |
| T2-33 | `tests/mod_editor/test_product_catalog.py:281` | clean | Inspection loader count 90 to 91 matches actual product iteration. |
| T2-34 | `tests/mod_editor/test_provider_integrity.py:201` | clean | Unified closure 270 to 271 matches AST-import closure with compile cache; remaining five closures untouched. |
