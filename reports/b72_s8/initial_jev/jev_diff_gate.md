# Jev diff gate: c5134e232..HEAD (2026-09-19 15:48)

Repo `/home/noah/2k-worktrees/astra-b72-s8`, c5134e232d..2a8471845b. 4 files changed; 10 hunk windows judged by Jev in 0.3 s (0 errors); skipped: none.

**0 deterministic finding(s), 2 Jev-flagged window(s) at P >= 0.6.** Flags by kind: PINNED_VALUE 2.

Diff facts given to Jev: New files under mod_editor/ in this diff: none. Release allowlists edited in this diff: no. mod_editor/core/providers.py (module_pins) edited: yes. Pinned closure count test tests/mod_editor/test_provider_integrity.py edited: no. packaging/requirements-*.txt edited: no; third-party packages already declared there: capstone, numpy, pillow, pyqt5, unicorn (PIL is pillow), so importing them needs no inventory change.

## Jev flags, ranked (P >= 0.6)

| # | max P | flags | where | hunk | first matching + line | code note |
|---|---|---|---|---|---|---|
| 1 | 0.88 | PINNED_VALUE 0.88 | `mod_editor/core/nfl2k5_scorebug_sprite_code.py:54-90` | `@@ -7,82 +7,84 @@ CODE = bytes.fromhex(` | `+    "6685c0741366837c247400750b66894424706683642472008d54247031f68324240066833a007473"` |  |
| 2 | 0.60 | PINNED_VALUE 0.60 | `mod_editor/core/nfl2k5_scorebug_sprite_code.py:10-61` | `@@ -7,82 +7,84 @@ CODE = bytes.fromhex(` | `+    "0054ffd383c4105bc38b515831c085d2740fd9413cd9412c31c0dff1ddd80f92c0c383b884400000"` |  |

## Notes (not flagged)

- mod_editor/core/providers.py:708-714: PINNED_VALUE 0.97 but every digest on its + lines matches the HEAD bytes (digests on + lines vs HEAD bytes: 1 match, 0 differ); not flagged
