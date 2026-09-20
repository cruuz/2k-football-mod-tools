# Jev diff gate: 42579f4a5..HEAD (2026-09-19 18:04)

Repo `/home/noah/2k-worktrees/astra-b72-s9`, 42579f4a50..16536dca08. 13 files changed; 21 hunk windows judged by Jev in 0.5 s (0 errors); skipped: windows over the per-file cap (data) 77, binary 1.

**0 deterministic finding(s), 8 Jev-flagged window(s) at P >= 0.6.** Flags by kind: PINNED_VALUE 8, WEAKENS_SAFETY 1.

Diff facts given to Jev: New files under mod_editor/ in this diff: none. Release allowlists edited in this diff: no. mod_editor/core/providers.py (module_pins) edited: yes. Pinned closure count test tests/mod_editor/test_provider_integrity.py edited: no. packaging/requirements-*.txt edited: no; third-party packages already declared there: capstone, numpy, pillow, pyqt5, unicorn (PIL is pillow), so importing them needs no inventory change.

## Jev flags, ranked (P >= 0.6)

| # | max P | flags | where | hunk | first matching + line | code note |
|---|---|---|---|---|---|---|
| 1 | 0.96 | PINNED_VALUE 0.96 | `tests/mod_editor/test_nfl2k5_scorebug_sprite.py:185-191` | `@@ -158,7 +185,7 @@ class NativeTests(unittest.TestCase):` | `-   expected={'away_score':1,'home_score':1,'clock':4,'play_clock':1,'quarter':2,'down':5,'home_timeouts':3,'away_timeouts':3}` |  |
| 2 | 0.91 | PINNED_VALUE 0.91 WEAKENS_SAFETY 0.69 | `tests/mod_editor/test_nfl2k5_scorebug_sprite.py:154-170` | `@@ -137,7 +154,17 @@ class DisplayModelTests(unittest.TestCase):` | `+  self.assertEqual(mark.convert('RGB').getextrema(),((255,255),)*3)` |  |
| 3 | 0.90 | PINNED_VALUE 0.90 | `tests/mod_editor/test_nfl2k5_scorebug_sprite.py:87-94` | `@@ -81,8 +87,8 @@ class LogoFitTests(unittest.TestCase):` | `-  self.assertEqual(set(fit['by_team']),{'KC','DEN'})` |  |
| 4 | 0.80 | PINNED_VALUE 0.80 | `mod_editor/core/nfl2k5_scorebug_sprite_code.py:24-31` | `@@ -24,8 +24,8 @@ CODE = bytes.fromhex(` | `+    "040000a3ec5aa9005b5e5f5dc35557565381ec300100008b9c2444010000e84afcffff85c00f8404"` |  |
| 5 | 0.77 | PINNED_VALUE 0.77 | `tests/mod_editor/test_nfl2k5_scorebug_sprite.py:22-34` | `@@ -22,7 +22,13 @@ class ContractTests(unittest.TestCase):` | `+  for digit in '0123456789':self.assertEqual(scores[digit]['size'][1],53)` |  |
| 6 | 0.70 | PINNED_VALUE 0.70 | `data/nfl2k5_scorebug_sprite/layout.json:87-93` | `@@ -87,7 +87,7 @@` | `-    17` |  |
| 7 | 0.64 | PINNED_VALUE 0.64 | `mod_editor/core/nfl2k5_scorebug_sprite_code.py:38-69` | `@@ -38,32 +38,32 @@ CODE = bytes.fromhex(` | `+    "83fa0475dbe92fffffff8b9d8c400000836424180001eb8b4424183b85884000000f83d803000031"` |  |
| 8 | 0.61 | PINNED_VALUE 0.61 | `data/nfl2k5_scorebug_sprite/layout.json:134-182` | `@@ -134,569 +134,609 @@` | `+    1212,` |  |

## Notes (not flagged)

- mod_editor/core/providers.py:700-714: PINNED_VALUE 0.97 but every digest on its + lines matches the HEAD bytes (digests on + lines vs HEAD bytes: 3 match, 0 differ); not flagged
- packaging/check_2k5_mod_studio_release.py:301-307: PINNED_VALUE 0.98 but every digest on its + lines matches the HEAD bytes (digests on + lines vs HEAD bytes: 1 match, 0 differ); not flagged
- packaging/nfl2k5_scorebug_template_pngs.json:296-303: PINNED_VALUE 0.97 but every digest on its + lines matches the HEAD bytes (digests on + lines vs HEAD bytes: 1 match, 0 differ); not flagged
- packaging/scorebug_replication_pins.py:7-13: PINNED_VALUE 0.97 but every digest on its + lines matches the HEAD bytes (digests on + lines vs HEAD bytes: 1 match, 0 differ); not flagged
