# Jev diff gate: ebed4b99..HEAD (2026-09-19 14:59)

Repo `/home/noah/2k-worktrees/astra-b72-s6`, ebed4b998b..edef5c97ff. 7 files changed; 13 hunk windows judged by Jev in 0.3 s (0 errors); skipped: none.

**0 deterministic finding(s), 2 Jev-flagged window(s) at P >= 0.6.** Flags by kind: WEAKENS_SAFETY 2.

Diff facts given to Jev: New files under mod_editor/ in this diff: none. Release allowlists edited in this diff: yes. mod_editor/core/providers.py (module_pins) edited: yes. Pinned closure count test tests/mod_editor/test_provider_integrity.py edited: no. packaging/requirements-*.txt edited: no; third-party packages already declared there: capstone, numpy, pillow, pyqt5, unicorn (PIL is pillow), so importing them needs no inventory change.

## Jev flags, ranked (P >= 0.6)

| # | max P | flags | where | hunk | first matching + line | code note |
|---|---|---|---|---|---|---|
| 1 | 0.69 | WEAKENS_SAFETY 0.69 | `tools/scorebug_sprite/xemu_model.py:93-102` | `@@ -82,12 +93,10 @@ def texture(span):` | `-    video = memoryview(body)[chunk.system_bytes:]` |  |
| 2 | 0.67 | WEAKENS_SAFETY 0.67 | `tools/scorebug_sprite/xemu_model.py:113-119` | `@@ -104,7 +113,7 @@ class Pipeline:` | `-                    0x1b0c:0x4003ffc0,0x1b14:0x02062000,0x1e70:1,` |  |

## Notes (not flagged)

- mod_editor/core/providers.py:707-713: PINNED_VALUE 0.97 but every digest on its + lines matches the HEAD bytes (digests on + lines vs HEAD bytes: 1 match, 0 differ); not flagged
- packaging/scorebug_replication_pins.py:1-9: PINNED_VALUE 0.96 but every digest on its + lines matches the HEAD bytes (digests on + lines vs HEAD bytes: 2 match, 0 differ); not flagged
