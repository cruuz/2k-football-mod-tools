# Beta 60 Windows path hotfix

Implemented in the existing `astra/hotfix-winpath` worktree, based on shipped
beta 60 / RC84 commit `37380d8`. No feature work, GUI, emulator, push, or changes
to the main working tree were performed. The supplied `ASTRA_BRIEF.md` remains
untouched and is excluded from the commit.

## Decisions and behavior

`mod_editor/core/platform_compat.py` now provides:

- `temporary_sibling(path, suffix=".tmp")`: a sibling named `.` + 12 random UUID
  hex characters + suffix. The default and `.png` forms are 17 characters. The
  helper does not reserve a file; each caller retains its existing creation,
  flush, publication, and cleanup logic. A candidate equal to the target itself
  is regenerated. The target's name never contributes to the generated name.
- `long_path(path)`: on Windows, fully absolute drive paths use `\\?\` and UNC
  paths use `\\?\UNC\`. Separators and dot segments are normalized before
  prefixing. Already prefixed paths, device paths, ordinary relative paths,
  drive-relative paths, and root-relative paths are left alone. POSIX returns
  the original path string. This helper performs no filesystem access.

Both session atomic byte writers use extended paths for parent creation,
`os.open`, publication (`publish_no_replace` or `os.replace`), and temporary-file
cleanup. Every other `os.replace` in the session store also converts both
operands, including batch commit, audio undo/restore, and project import.
Persistence uses extended paths for saving, loading, validation, directory
creation, replacement, and cleanup. Save return paths retain their ordinary
logical spelling. This is scoped to the requested session/persistence I/O; it is
not a conversion of every filesystem operation throughout the application.

Session byte writes and transaction swaps catch `OSError` through
`_explain_write_failure`. On Windows, when the destination or an OS-reported
source/destination filename is at least 260 characters, they raise a
`ValidationError` with the requested length and recovery instructions. Extended
prefix characters are excluded from the reported length. Other failures retain
their original exception. The original exception remains chained for diagnosis.
The existing `studio_qt.py` "Couldn't finish that" handler still appends
"Your original game disc was not changed."; that GUI file was not modified.

The exact guidance is:

> Windows limits file paths to 260 characters and this one is N. Enable long paths in Windows (Settings or HKLM\SYSTEM\CurrentControlSet\Control\FileSystem LongPathsEnabled=1, then restart) or move your sessions folder.

## Every staging site changed

Line references below identify the original beta-60 sites; function names identify
the resulting code. There are 21 file staging sites and one directory staging site.

| File | Original site(s) / function(s) | Change |
| --- | --- | --- |
| `mod_editor/studio/session.py` | 114 `_write_new_atomic`; 136 `_replace_atomic` | Short siblings, extended-path I/O, actionable failures |
| `mod_editor/core/persistence.py` | 22 `save_project` | Short sibling and extended-path persistence |
| `mod_editor/core/texture_master.py` | 647 `save_texture_master_bundle` | Short sibling |
| `mod_editor/studio/workspace_state.py` | 322 `WorkspaceStateStore._write` | Short sibling |
| `mod_editor/core/nfl2k5_universal_asset_index.py` | 359 `export_raw`; 422 `_build_database` | Short siblings |
| `mod_editor/studio/project_archive.py` | 609 `save_project_archive` | Short sibling |
| `mod_editor/core/nfl2k5_stadium_studio.py` | 702 `export_texture`; 1112 `_write_new_file` | Short siblings; second occurrence found during audit |
| `mod_editor/core/nfl2k5_asset_io.py` | 65 `_atomic_write`; 322 `copy_user_asset_atomic` | Short siblings |
| `mod_editor/core/nfl2k5_audio_catalog.py` | 1504 `_atomic_write`; 1569 `_stream_entry_to_new_file` | Short siblings |
| `mod_editor/core/nfl2k5_extended_visual_io.py` | 80 `_atomic_write` | Short sibling |
| `mod_editor/core/nfl2k5_crib.py` | 852 `_atomic_write` | Short sibling |
| `mod_editor/core/nfl2k5_source_cache.py` | 497 `_atomic_write_json` | Short sibling |
| `mod_editor/gui/audio_panel_qt.py` | 513 `_copy_atomic`; 576 `_replace_atomic_bytes` | Short siblings; first occurrence found during audit |
| `mod_editor/core/nfl2k5_scorebug_source_art.py` | 300 `_cache_write`; 515 `preview_mockup` | Short siblings; preview keeps `.png` for format selection |
| `mod_editor/studio/uniform_bundle.py` | 541 `TeamKitBundleService.export` | `mkdtemp(prefix=".team-kit-", dir=requested.parent)`; requested name and extra UUID removed |

## Length arithmetic

The reported replacements directory is **112** characters, excluding its trailing
separator. The Team Kit target basename is **111**, not the approximate 108 in
the brief: `.team-kit-` (10) + transaction (32) + `-` (1) + asset hash (64) +
`.png` (4).

| Path | Arithmetic | Characters |
| --- | --- | ---: |
| Final transaction PNG, unchanged | 112 + separator 1 + basename 111 | 224 |
| Original temporary path | 224 + extra dot 1 + PID separator 1 + PID 5 + UUID separator 1 + UUID 32 + `.tmp` 4 | 268 |
| New temporary path | 112 + separator 1 + dot 1 + random hex 12 + `.tmp` 4 | 130 |

The change removes **138 characters** from the reported temporary path.
With a 120-character sessions root plus a 36-character session identifier and
`replacements`, the temporary path is `120 + 37 + 13 + 18 = 188` characters.
The corresponding final transaction PNG is 282 characters, which is why the
Windows extended-path support is also included.

## Validation

Executed on Linux with Python 3.12. The new standalone unittest module runs on
Linux, macOS, and Windows. Native Windows execution was unavailable here; the two
tests that actually write beneath a parent exceeding 260 characters are explicitly
Windows-only. Pure Windows path cases and naming assertions run on every OS.

| Command / check | Result |
| --- | --- |
| `python3 tests/mod_editor/test_platform_compat_paths.py` | 15 tests, OK; 2 native Windows cases skipped |
| `python3 tests/mod_editor/test_modpack.py` | 36 tests, OK |
| `python3 -m unittest tests.mod_editor.test_studio_session tests.mod_editor.test_core` | 29 tests, OK; 1 existing development-evidence skip |
| `python3 -m unittest discover -s tests/mod_editor -p 'test_uniform*.py'` | 8 tests; 7 errors from missing pinned audit reports |
| `python3 -m unittest tests.mod_editor.test_platform_compat_paths tests.mod_editor.test_platform_compat tests.mod_editor.test_platform_compat_durability tests.mod_editor.test_platform_compat_ownership` | 89 tests, OK; 2 Windows skips (before adding the subsequently passing ten-digit regression) |
| `python3 -m unittest tests.mod_editor.test_team_kit_bundle tests.mod_editor.test_texture_master tests.mod_editor.test_nfl2k5_universal_asset_index tests.mod_editor.test_nfl2k5_stadium_studio tests.mod_editor.test_nfl2k5_crib` | 31 tests; 2 missing-report errors, including Team Kit `setUpClass` |
| `python3 -m unittest tests.mod_editor.test_workspace_recovery tests.mod_editor.test_audio_annotation_project_archive tests.mod_editor.test_nfl2k5_source_cache_privacy` | 20 tests, OK; headless tests only |
| `python3 -m unittest tests.mod_editor.test_nfl2k5_audio_catalog tests.mod_editor.test_audio_replacement_pack` | 54 tests; 1 missing-report error; the transaction/rollback tests pass |
| `python3 -m unittest tests.mod_editor.test_nfl2k5_scorebug_source_art.AvailabilityTests` | 5 tests; 1 failure and 1 error due to the absent presentation audit |
| Original-writer reproduction | The ten-digit regression fails with simulated MAX_PATH when the two unmodified atomic writer functions from `37380d8` are substituted; it passes with this fix |
| `python3 packaging/repin.py --apply` | Exit 0; refreshed pins in `providers.py` and `check_2k5_mod_studio_runtime.py`; final application has zero pending updates |
| Compilation / scope / binary-flags audit | Changed modules compile; all `os.open` flag expressions match the base revision, including every existing `O_BINARY` flag |
| `git diff --check` | Pass |

The new tests cover uniqueness, same-directory placement, maximum basename size,
avoiding the target itself, the `.png` suffix, the exact reported arithmetic,
drive/UNC/device/relative path cases, binary round trips, atomic no-overwrite,
fsync/replace failure cleanup, persistence round trips, Windows error wording and
the 259/260 boundary, and unchanged POSIX exceptions. The synthetic ten-digit
batch exercises `StudioSession.replace_batch` under a simulated MAX_PATH ceiling,
verifies all ten replacements, then undoes them and verifies the original source
bytes are unchanged.

The missing reports are absent from this worktree and from tracked `HEAD` files:
`uniform_texture_sharing.v2.json`, `apf_pants_family_layout.json`,
`apf_helmet_family_layout.json`, `apf_shoulder_family_layout.json`,
`nfl2k5_team_select_card_inventory.json`,
`nfl2k5_player_portrait_compatibility.json`, `nfl2k5_audo_import_capacity.json`,
and `scorebug_presentation_audit.json`, all under `reports/assets`. No report was
fabricated, pins relaxed, existing tests edited, or files borrowed from the main
working tree to conceal those unavailable fixtures. Full Team Kit catalog tests
and native Windows filesystem validation remain environment-limited.

## Integrity and scope

Repinning updates 13 existing pin entries across
`mod_editor/core/providers.py` and `packaging/check_2k5_mod_studio_runtime.py`.
No pin was removed or widened. An additional repin refreshed the five
`platform_compat.py` entries after its helper docstring was clarified.

Protected files remain unchanged: `mod_build.py`, `nfl2k5_throw_tuning.py`,
`update_check.py`, release-tag tests, `packaging/release-allowlist.txt`, and CI
workflows. No new production module or release-allowlist entry was needed.
The commit uses explicit paths for the 16 implementation files, two repinned
files, new regression test, and this report. Nothing is pushed.
