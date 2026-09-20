# Jev diff gate: origin/main..HEAD (2026-09-19 18:04)

Repo `/home/noah/2k-worktrees/astra-b72-s9`, 6944f5626b..16536dca08. 697 files changed; 123 hunk windows judged by Jev in 2.5 s (0 errors); skipped: docs/logs/other 5, windows over the per-file cap (data) 516, binary 40, reports/ (job evidence) 602.

**1 deterministic finding(s), 12 Jev-flagged window(s) at P >= 0.6.** Flags by kind: PINNED_VALUE 10, WEAKENS_SAFETY 2, SLOW_TEST 1.

Diff facts given to Jev: New files under mod_editor/ in this diff: mod_editor/core/nfl2k5_scorebug_teams.py (release allowlist: yes, module_pins: yes). Release allowlists edited in this diff: yes. mod_editor/core/providers.py (module_pins) edited: yes. Pinned closure count test tests/mod_editor/test_provider_integrity.py edited: yes. packaging/requirements-*.txt edited: no; third-party packages already declared there: capstone, numpy, pillow, pyqt5, unicorn (PIL is pillow), so importing them needs no inventory change.

## Deterministic findings (certain)

| check | where | detail |
|---|---|---|
| UNDECLARED_IMPORT | `tools/scorebug_sprite/jev/session.py:64` | `import typesafe_sdk` (shipped file): `typesafe_sdk` is in no packaging/requirements-*.txt |

## Jev flags, ranked (P >= 0.6)

| # | max P | flags | where | hunk | first matching + line | code note |
|---|---|---|---|---|---|---|
| 1 | 0.97 | PINNED_VALUE 0.97 | `data/nfl2k5_cave_reservations.json:166-172` | `@@ -166,7 +166,7 @@` | `+  "stack_xbe_sha256": "aa8c404c8aabce064d2fae36f88777ae15c2503e95c4a1b09f1b85912f2aeed0",` |  |
| 2 | 0.97 | PINNED_VALUE 0.97 | `tests/mod_editor/test_provider_integrity.py:215-221` | `@@ -215,7 +215,7 @@ class ProviderIntegrityTests(unittest.TestCase):` | `+            [301, 10, 8, 9, 8, 9]  # s5: + official team accents and the xemu reference fragment model.` |  |
| 3 | 0.96 | PINNED_VALUE 0.96 | `data/nfl2k5_cave_reservations.json:2336-2349` | `@@ -2336,13 +2336,14 @@` | `+    "mod_editor/core/nfl2k5_scorebug_exact.py": "84dd25c9bbee8eada8d41b861122a7ab405edd4b30951718bfe87c6192b1cad9",` | digests on + lines vs HEAD bytes: 4 match, 3 differ |
| 4 | 0.95 | PINNED_VALUE 0.95 | `tests/mod_editor/test_nfl2k5_scorebug_sprite.py:185-191` | `@@ -158,7 +185,7 @@ class NativeTests(unittest.TestCase):` | `-   expected={'away_score':1,'home_score':1,'clock':4,'play_clock':1,'quarter':2,'down':5,'home_timeouts':3,'away_timeouts':3}` |  |
| 5 | 0.91 | PINNED_VALUE 0.91 WEAKENS_SAFETY 0.73 | `tests/mod_editor/test_nfl2k5_scorebug_sprite.py:154-170` | `@@ -137,7 +154,17 @@ class DisplayModelTests(unittest.TestCase):` | `+  self.assertEqual(mark.convert('RGB').getextrema(),((255,255),)*3)` |  |
| 6 | 0.90 | PINNED_VALUE 0.90 | `tests/mod_editor/test_nfl2k5_scorebug_sprite.py:87-94` | `@@ -81,8 +87,8 @@ class LogoFitTests(unittest.TestCase):` | `-  self.assertEqual(set(fit['by_team']),{'KC','DEN'})` |  |
| 7 | 0.86 | PINNED_VALUE 0.86 | `mod_editor/core/nfl2k5_scorebug_sprite_code.py:61-89` | `@@ -7,74 +7,83 @@ CODE = bytes.fromhex(` | `+    "7c241c99f77c240401f88b7c240c894424248b4424100346080fafc78b7c241c99f77c240431d201"` |  |
| 8 | 0.80 | PINNED_VALUE 0.80 | `tests/mod_editor/test_nfl2k5_scorebug_sprite.py:22-34` | `@@ -22,7 +22,13 @@ class ContractTests(unittest.TestCase):` | `+  for digit in '0123456789':self.assertEqual(scores[digit]['size'][1],53)` |  |
| 9 | 0.69 | WEAKENS_SAFETY 0.69 | `tools/scorebug_sprite/runtime.c:61-96` | `@@ -59,16 +61,36 @@ static u32 logo(u32 context) {` | `+static void accents(u8 *b,u32 context,u32 *wing,u32 *rim,u32 *plate) {` |  |
| 10 | 0.65 | PINNED_VALUE 0.65 | `data/nfl2k5_scorebug_sprite/layout.json:87-93` | `@@ -87,7 +87,7 @@` | `-    17` |  |
| 11 | 0.63 | SLOW_TEST 0.63 | `tests/mod_editor/test_scorebug_gpu.py:105-159` | `@@ -0,0 +1,159 @@` | `+        for wide in (False,True):` |  |
| 12 | 0.62 | PINNED_VALUE 0.62 | `data/nfl2k5_scorebug_sprite/layout.json:134-182` | `@@ -134,569 +134,609 @@` | `+    1212,` |  |

## Notes (not flagged)

- mod_editor/core/providers.py:699-720: PINNED_VALUE 0.96 but every digest on its + lines matches the HEAD bytes (digests on + lines vs HEAD bytes: 10 match, 0 differ); not flagged
- mod_editor/core/providers.py:747-753: PINNED_VALUE 0.97 but every digest on its + lines matches the HEAD bytes (digests on + lines vs HEAD bytes: 1 match, 0 differ); not flagged
- mod_editor/core/providers.py:802-808: PINNED_VALUE 0.97 but every digest on its + lines matches the HEAD bytes (digests on + lines vs HEAD bytes: 1 match, 0 differ); not flagged
- mod_editor/core/providers.py:1337-1343: PINNED_VALUE 0.97 but every digest on its + lines matches the HEAD bytes (digests on + lines vs HEAD bytes: 1 match, 0 differ); not flagged
- packaging/check_2k5_mod_studio_release.py:301-307: PINNED_VALUE 0.98 but every digest on its + lines matches the HEAD bytes (digests on + lines vs HEAD bytes: 1 match, 0 differ); not flagged
- packaging/nfl2k5_scorebug_template_pngs.json:296-303: PINNED_VALUE 0.97 but every digest on its + lines matches the HEAD bytes (digests on + lines vs HEAD bytes: 1 match, 0 differ); not flagged
