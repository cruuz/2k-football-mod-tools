# Jev diff gate: 97d2bf9b2..HEAD (2026-09-19 21:54)

Repo `/home/noah/2k-worktrees/astra-b72-s10`, 97d2bf9b2f..73273e596a. 16 files changed; 11 hunk windows judged by Jev in 0.4 s (0 errors); skipped: docs/logs/other 2, windows over the per-file cap (data) 70, binary 1, reports/ (job evidence) 4.

**0 deterministic finding(s), 2 Jev-flagged window(s) at P >= 0.6.** Flags by kind: PINNED_VALUE 2.

Diff facts given to Jev: New files under mod_editor/ in this diff: none. Release allowlists edited in this diff: no. mod_editor/core/providers.py (module_pins) edited: yes. Pinned closure count test tests/mod_editor/test_provider_integrity.py edited: no. packaging/requirements-*.txt edited: no; third-party packages already declared there: capstone, numpy, pillow, pyqt5, unicorn (PIL is pillow), so importing them needs no inventory change.

## Jev flags, ranked (P >= 0.6)

| # | max P | flags | where | hunk | first matching + line | code note |
|---|---|---|---|---|---|---|
| 1 | 0.91 | PINNED_VALUE 0.91 | `tests/mod_editor/test_nfl2k5_scorebug_sprite.py:88-101` | `@@ -88,11 +88,14 @@ class LogoFitTests(unittest.TestCase):` | `-  for team,expect in (('KC',1.89),('DEN',2.09),('BUF',None)):` |  |
| 2 | 0.63 | PINNED_VALUE 0.63 | `data/nfl2k5_scorebug_sprite/layout.json:79-126` | `@@ -38,703 +38,703 @@` | `+    889,` |  |

## Notes (not flagged)

- mod_editor/core/providers.py:706-712: PINNED_VALUE 0.97 but every digest on its + lines matches the HEAD bytes (digests on + lines vs HEAD bytes: 1 match, 0 differ); not flagged
- packaging/check_2k5_mod_studio_release.py:301-307: PINNED_VALUE 0.98 but every digest on its + lines matches the HEAD bytes (digests on + lines vs HEAD bytes: 1 match, 0 differ); not flagged
- packaging/nfl2k5_scorebug_template_pngs.json:296-303: PINNED_VALUE 0.97 but every digest on its + lines matches the HEAD bytes (digests on + lines vs HEAD bytes: 1 match, 0 differ); not flagged
- packaging/scorebug_replication_pins.py:1-13: PINNED_VALUE 0.96 but every digest on its + lines matches the HEAD bytes (digests on + lines vs HEAD bytes: 2 match, 0 differ); not flagged
