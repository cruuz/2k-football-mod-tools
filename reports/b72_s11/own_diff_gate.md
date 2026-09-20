# Jev diff gate: c3b3b53a2..HEAD (2026-09-19 22:29)

Repo `/home/noah/2k-worktrees/astra-b72-s11`, c3b3b53a27..eafd053dbe. 10 files changed; 7 hunk windows judged by Jev in 0.3 s (0 errors); skipped: windows over the per-file cap (data) 34, docs/logs/other 1, reports/ (job evidence) 4.

**0 deterministic finding(s), 1 Jev-flagged window(s) at P >= 0.6.** Flags by kind: PINNED_VALUE 1.

Diff facts given to Jev: New files under mod_editor/ in this diff: none. Release allowlists edited in this diff: no. mod_editor/core/providers.py (module_pins) edited: no. Pinned closure count test tests/mod_editor/test_provider_integrity.py edited: no. packaging/requirements-*.txt edited: no; third-party packages already declared there: capstone, numpy, pillow, pyqt5, unicorn (PIL is pillow), so importing them needs no inventory change.

## Jev flags, ranked (P >= 0.6)

| # | max P | flags | where | hunk | first matching + line | code note |
|---|---|---|---|---|---|---|
| 1 | 0.92 | PINNED_VALUE 0.92 | `tests/mod_editor/test_nfl2k5_scorebug_sprite.py:84-101` | `@@ -84,18 +84,18 @@ class ContractTests(unittest.TestCase):` | `- def test_marks_are_drawn_as_the_broadcast_draws_them(self):` |  |

## Notes (not flagged)

- packaging/scorebug_replication_pins.py:7-13: PINNED_VALUE 0.97 but every digest on its + lines matches the HEAD bytes (digests on + lines vs HEAD bytes: 1 match, 0 differ); not flagged
