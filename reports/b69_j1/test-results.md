# J1 standalone test results

Each command runs its entire test file. `returncode=1` is retained as a failure, not called a pass. Times are process wall time except where the JSON marks unittest reported time.

| File | Cases | Exit | Seconds | Output |
|---|---:|---:|---:|---|
| test_2k5_uniform_equipment_export.py | 13 | 1 | 3.078 | [log](tests/test_2k5_uniform_equipment_export.py.log) |
| test_b661_kit_build.py | 2 | 0 | 4.784 | [log](tests/test_b661_kit_build.py.log) |
| test_b68_a1_audit.py | 10 | 0 | 10.848 | [log](tests/test_b68_a1_audit.py.log) |
| test_b68_t1_build.py | 6 | 0 | 8.896 | [log](tests/test_b68_t1_build.py.log) |
| test_b69_j1_build.py | 5 | 0 | 4.232 | [log](tests/test_b69_j1_build.py.log) |
| test_b69_j1_fit.py | 5 | 0 | 8.295 | [log](tests/test_b69_j1_fit.py.log) |
| test_b69_j1_native.py | 1 | 0 | 2.475 | [log](tests/test_b69_j1_native.py.log) |
| test_b69_j1_wiring.py | 3 | 0 | 4.206 | [log](tests/test_b69_j1_wiring.py.log) |
| test_beta66_d1_panels.py | 4 | 0 | 2.823 | [log](tests/test_beta66_d1_panels.py.log) |
| test_nfl2k5_build_service.py | 28 | 0 | 0.466 | [log](tests/test_nfl2k5_build_service.py.log) |
| test_nfl2k5_equipment_consumers.py | 19 | 0 | 50.659 | [log](tests/test_nfl2k5_equipment_consumers.py.log) |
| test_nfl2k5_equipment_import.py | 13 | 0 | 4.028 | [log](tests/test_nfl2k5_equipment_import.py.log) |
| test_nfl2k5_equipment_import_wiring.py | 6 | 0 | 1.72 | [log](tests/test_nfl2k5_equipment_import_wiring.py.log) |
| test_nfl2k5_equipment_retail_roundtrip.py | 2 | 0 | 25.767 | [log](tests/test_nfl2k5_equipment_retail_roundtrip.py.log) |
| test_nfl2k5_equipment_scope_wiring.py | 3 | 0 | 4.479 | [log](tests/test_nfl2k5_equipment_scope_wiring.py.log) |
| test_nfl2k5_equipment_texture_chain.py | 19 | 0 | 4.581 | [log](tests/test_nfl2k5_equipment_texture_chain.py.log) |
| test_nfl2k5_equipment_texture_native.py | 7 | 0 | 0.517 | [log](tests/test_nfl2k5_equipment_texture_native.py.log) |
| test_nfl2k5_extended_visuals.py | 9 | 0 | 0.618 | [log](tests/test_nfl2k5_extended_visuals.py.log) |
| test_nfl2k5_shoe_relief.py | 5 | 0 | 9.754 | [log](tests/test_nfl2k5_shoe_relief.py.log) |
| test_provider_integrity.py | 7 | 0 | 16.32 | [log](tests/test_provider_integrity.py.log) |
| test_providers.py | 33 | 0 | 5.389 | [log](tests/test_providers.py.log) |

Common prefix: `PYTHONPATH=. QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 python3` followed by `tests/mod_editor/<file>`.

Exact commands and tails: [test-results.json](test-results.json). All new native cases ran; no emulator or display was used.
