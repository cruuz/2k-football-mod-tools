# B75 u1: Windows "Update now" installs, and the relaunched studio still reports the old version

Job `b75-u1`. Worktree `~/2k-worktrees/b75-u1` (branch `job/b75-u1`, base 56b537342 = beta 74).
Reproduction with evidence, then the fix. One commit, not pushed.

## Verdict

**Reproduced, end to end, with the real published beta 73 and beta 74 Setup.exe files.**

Neither hypothesis in the brief is the cause. The studio does exit, `/WAITPID` does hold the
install, `/D=` does point at the right folder, and the installer does write the new release into
that folder. The new `app\mod_editor\core\update_check.py` on disk says `beta-74`.

The studio still reports `beta-73`, because it never reads that file. It loads
`app\mod_editor\core\__pycache__\update_check.cpython-312.pyc`, compiled from the previous
release, and CPython's timestamp check cannot tell the two releases apart:

* the installer stamps **every** staged file with one fixed mtime, `SOURCE_DATE_EPOCH = 1785110400`
  (`packaging/windows/build_windows_installer.py:234`, applied at `:249`, called at `:298`), and
  NSIS restores that stored mtime on extraction, so the new `.py` lands with exactly the mtime the
  old one had;
* `mod_editor/core/update_check.py` is **8334 bytes in every release from beta-68 to beta-74** -
  only the tag string inside `BUILD_RELEASE_TAG` changes, and `"beta-68"`, `"beta-73"` and
  `"beta-74"` are all the same length;
* a timestamp `.pyc` is validated on `(source mtime, source size)` alone. Both match. The cached
  bytecode is reused and the new source is never compiled.

`File /r` merges into the existing tree and removes nothing
(`packaging/windows/build_windows_installer.py:414-416`), so the stale `__pycache__` from the old
install survives the update forever.

## Reproduction

Wine 9.0, prefix `.scratch/wine-loop` (`WINEARCH=win64`, `WINEDEBUG=-all`, everything under
`xvfb-run`). Installers from `gh release download beta-73 / beta-74 -R cruuz/2k-football-mod-tools`.

| # | Step | Observed |
|---|------|----------|
| 0 | `7z e -so <Setup>.exe app/mod_editor/core/update_check.py` on both files | rc100 payload carries `beta-73`, rc101 payload carries `beta-74`. The published installers are correct. |
| 1 | `wine 2K5-Mod-Studio-1.0.0rc100-Setup.exe /S` | 11 s. Tree at `AppData/Local/Programs/2K5-Mod-Studio` with `app/`, `runtime/`, `Uninstall.exe`. 963 files in `app/`. On disk: `BUILD_RELEASE_TAG = "beta-73"`. |
| 2 | Open it once (`runtime/python.exe` importing `mod_editor.core.update_check`) | Reports **beta-73**, correct. Writes `app/mod_editor/core/__pycache__/update_check.cpython-312.pyc`. |
| 3 | Start a studio process, read its Windows pid (272), then run the updater's exact command line: `Setup74.exe /S /WAITPID=272 /RELAUNCH /D=C:\users\noah\AppData\Local\Programs\2K5-Mod-Studio` | Installer **waited** for the process (35.6 s wall against a 25 s holder, versus 11 s with no wait), then installed. `/D=` honoured, same folder. On disk afterwards: `BUILD_RELEASE_TAG = "beta-74"`, mtime 1785110400, size 8334. `/RELAUNCH` started `pythonw.exe` (it left fresh `__pycache__` folders behind). |
| 4 | Reopen the studio | **Reports `beta-73`.** This is nwostar's report exactly: the update ran, the studio came back, the banner offers beta 74 again. |
| 5 | Delete only `app/**/__pycache__`, change nothing else, reopen | **Reports `beta-74`.** |

Header of the surviving `.pyc` against the freshly installed source:

```
pyc header:     source_mtime=1785110400  source_size=8334
source on disk: mtime=1785110400         size=8334
VALIDATION: pyc considered VALID (no recompile)
```

A separate run in `.scratch/wine-update` confirmed the same happy path over an existing install:
4531 files before, 4537 after, nothing removed, `beta-74` on disk.

### lt9608 is the same bug one release earlier

"Everytime I download version 73 it goes through the process and when it finish I keep getting the
message to upgrade and that im running version 68." `update_check.py` is 8334 bytes in beta-68 and
in beta-73, with the same stamped mtime, so a beta-68 install that is upgraded in place to beta-73
keeps beta-68's bytecode and keeps saying beta-68. No self-update needed: running the beta 73
Setup.exe by hand over a beta 68 install does it.

Their later "I uninstalled completely and installed new, still says Update Available beta 74" is
consistent and is not a second bug. Uninstall does `RMDir /r "$INSTDIR\app"` (`:448`), which clears
the bytecode, but what they reinstalled was beta 73, and beta 73 correctly reports that beta 74 is
available.

## The two hypotheses in the brief

**"The studio process does not exit, so /WAITPID holds the install for ten minutes."**
Not the cause, but a real second defect, proven separately with
`.scratch/exit_probe.py` (the real `StudioMainWindow`, the real `UpdateBanner`, the real
`run_update`; only `detect_install`, the HTTP opener and `self_update`'s `subprocess.Popen` are
faked):

* clean workspace: installer command spawned, `app.exec_()` returned **1.24 s** after the hand-off,
  process exit code 0. This is the normal case and it is fine.
* dirty workspace (`_workspace_dirty = True`, which is true for any user who has edited anything):
  installer command spawned, banner says "The studio closes now; the installer runs on its own and
  reopens it when it is done", and **the process never exits**. Killed at the 120 s timeout.

Cause: `update_ui.py:382` schedules `_request_quit`, `:388` calls `app.closeAllWindows()`, the main
window's `closeEvent` reaches `studio_qt.py:8654` `self._prompt_unsaved_decision("Closing Mod
Studio")`, and that modal dialog runs a nested event loop inside `closeAllWindows()`. The banner is
already showing text that promises the studio is closing. `closeEvent` has five paths that call
`event.ignore()` (`studio_qt.py:8620-8668`: a project check in flight, a music operation, an
embedded-busy refusal, `_blocking`, and unsaved-work cancel or save), and the first of those shows
no dialog at all, only a status line. In every one of them the installer sits in `.onInit` waiting,
for up to ten minutes, while the studio stays open.

**"A copy launched from a folder other than the /D= target."**
Not the cause, and the design is self-correcting. `detect_install` derives the root from
`self_update.py`'s own path (`self_update.py:43`, `:149-150`), so `/D=` always follows the running
copy, and `apply_windows_installer` (`:300-312`) installs into exactly the folder the running copy
lives in. A studio launched from anywhere gets updated in place. The shortcuts are rewritten on
every install (`build_windows_installer.py:419-424`), so they cannot point at a stale folder either.

## Cause

`packaging/windows/build_windows_installer.py:234` with `:249`, `:298` and `:414-416`.

One fixed `SOURCE_DATE_EPOCH` for every release, restored by NSIS on extraction, plus an in-place
`File /r` merge that never removes the old `__pycache__`, plus a shipped file whose byte size does
not change, equals bytecode that CPython considers valid forever. `mod_editor/core/update_check.py:41`
(`BUILD_RELEASE_TAG`) is the line the user sees, but it is not the only casualty.

### Blast radius

Every `.py` that changed between two releases while keeping its byte size runs the previous
release's bytecode after an in-place Windows update. Between beta 73 and beta 74, inside the shipped
app tree:

* `mod_editor/core/update_check.py` (8334 B) - the version the studio reports
* `mod_editor/__init__.py` (206 B) - `__version__`, `1.0.0rc100` and `1.0.0rc101` are the same length
* `mod_editor/apf_studio/__init__.py` (1459 B)
* `mod_editor/core/providers.py` (129708 B) - the runtime integrity checker, so beta 73's hashing
  code runs against beta 74's sources

Between beta 68 and beta 73 the same list includes `update_check.py`, `apf_studio/__init__.py`,
`tools/apf_field_art_patch.py` (87639 B), `tools/setup_reviewed_helpers.py` and
`tools/validate_apf_logocache_product.py`.

Only the Windows installer is affected. The tarball path builds a fresh sibling folder and
explicitly drops bytecode (`self_update.py:327`, `:425`), which is why every report is from an
installer install.

## Fix as applied

Both candidates were taken, because each closes a different half and neither closes both.
`-B` or `PYTHONDONTWRITEBYTECODE` on the launch commands was rejected: it leaves the existing stale
`.pyc` in place, so a stuck machine stays stuck.

**1. The installer replaces the installed trees instead of merging into them.**
`packaging/windows/build_windows_installer.py`, in the generated `Section "Install"` ahead of both
`File /r` lines:

```nsis
  RMDir /r "$INSTDIR\app"
  RMDir /r "$INSTDIR\runtime"
```

`runtime\` is cleared as well as `app\`, on the coordinator's two conditions, both of which hold.
It is fully re-extracted on every install: `build_runtime` rebuilds it from the pinned embeddable
CPython and the pinned wheels every time (`:125-166`), and `File /r "...runtime"` ships the whole
tree. Nothing user-owned lives in it: the `._pth` is generated by the build, site-packages comes
only from the pinned wheels, and projects, working sessions and workspace state are under
`%LOCALAPPDATA%` by `mod_editor/studio/session.py:99-110`. Clearing it also means a wheel that is
ever repinned or dropped cannot leave importable files on `sys.path`. The cost is that an install
interrupted after the delete leaves no interpreter, the same way it already left a half-overwritten
tree; re-running Setup.exe repairs either, and `/WAITPID` has already waited for the studio to exit
by the time the section runs. The Uninstall section is unchanged and still removes only what it
created.

**2. Each release stamps its files with its own time.**
`source_date_epoch(version)` replaces the fixed `SOURCE_DATE_EPOCH`: a SHA-256 of the version
string, taken as an offset back from the old constant (now `SOURCE_DATE_EPOCH_ANCHOR`,
2026-07-27T00:00:00Z) inside a twenty-year window. It is a pure function of the build inputs, so a
given version still rebuilds byte for byte, and every stamp stays in the past. `normalise_mtimes`
takes the stamp as an argument. Measured: `1.0.0rc101` gives 1545831101 and `1.0.0rc102` gives
1467755826.

**3. Unsaved work is settled before the hand-off, not after it.**
`mod_editor/gui/update_ui.py` gains `prepare_to_close`, called between the confirmation and the
download. It asks the parent window through a `prepare_for_update_quit(proceed)` hook, and the
update starts only when the window calls `proceed`. `_request_quit` now closes the windows and ends
the event loop unconditionally: the fallback text that used to say the update would install "as
soon as you close the studio" is gone, because the banner's promise is now kept.
`StudioMainWindow.prepare_for_update_quit` (and the same hook on the APF window) refuses the update
outright while a build or an audio operation owns the shell, then runs the existing
`_continue_after_unsaved` and sets `_allow_close`, which `closeEvent` already reads ahead of the
unsaved-work prompt. A parent with no hook, which is every test that builds a bare banner, is
treated as free to close.

The `closeEvent` order in `studio_qt.py` is deliberately **not** changed. Hoisting `_allow_close`
above the three earlier checks was tried and reverted: it broke
`test_clean_close_is_refused_without_auto_close_until_audio_drains` and
`test_close_during_open_requests_cancel_without_blocking_dialog`, which encode a real contract that
an in-flight audio operation or project check defers a close so it can reach a safe boundary. Those
are deferrals, not prompts; they finish on their own. The only close-time prompt that `_allow_close`
does not already skip is `_refuse_while_embedded_busy`, and that is what the new up-front refusal
prevents ever being reached with an installer waiting.

### Evidence that the fix works

The rendered script compiles (`makensis`, clean). Two minimal installers built through the changed
builder, installed in a fresh Wine prefix in the user's own order:

```
install rc100          on disk beta-73, mtime 1179000320
plant stale bytecode   app/mod_editor/core/__pycache__/update_check.cpython-312.pyc
plant a dropped file   app/mod_editor/core/removed_module.py
install rc101 /D=...   on disk beta-74, mtime 1545831100
                       stale __pycache__: cleared
                       dropped module:    cleared
                       runtime:           re-extracted
```

The two mtimes differ, so even a tree that somehow kept its bytecode would recompile. (NSIS stores
the stamp with two-second granularity, hence 1545831100 for 1545831101; the window is twenty years,
so that rounding cannot collide two releases.)

### What to tell nwostar and lt9608 now

Delete the `__pycache__` folders under `%LOCALAPPDATA%\Programs\2K5-Mod-Studio\app`, or uninstall
from Settings and run the newest Setup.exe. From beta 74.1 on, Update now clears them itself.

## Tests

Nothing in `tests/mod_editor/test_self_update.py` (46 tests) asserted any of this. The two Windows
tests, `test_the_installer_is_started_silently_with_wait_and_relaunch` and
`test_the_installer_template_implements_both_switches`, checked the command string and that the
template mentions both switches. Nothing asserted that the running studio exits after spawning the
installer, and nothing asserted what version an installed tree reports after a silent update over
an existing install. Both untested behaviours are the ones that failed.

Twelve tests were added to the same file, in four groups:

* `InstallerReplacesTheTreeTests`: the rendered Install section clears both trees before the first
  `File /r`, for both products, and the Uninstall section still removes only what it created.
* `SourceDateEpochTests`: every version gets a different instant, one version always rebuilds to
  the same instant, no stamp is in the future, and the whole staged tree is flattened to it.
* `StaleBytecodeTests`: pure Python, no Windows and no Wine. A same-size, same-stamp overwrite of a
  module is **not** recompiled, which documents the failure and passes before and after the fix; a
  per-release stamp lets the new source win, which fails before it; and the release tag line can
  never change `update_check.py`'s byte size, which is why that module was the guaranteed casualty.
* Qt, offscreen: the parent window is asked about unsaved work before anything is spawned and in
  that order; cancelling the question spawns nothing; the real `StudioMainWindow` with a dirty
  workspace is asked exactly once and its following close asks nothing even with `_blocking` set;
  a busy studio refuses the update instead of starting one it cannot finish, and the
  banner's `self.window()` really does resolve to the studio that carries the hook.

`tests/mod_editor/test_self_update.py`: **41 passed**. Reverting only the three changed source
files fails ten of them (every new test except the one that documents the old behaviour), so they
are coupled to the fix rather than to its shape.

Regression run, offscreen, over the nineteen test files that touch `update_ui`, `closeEvent`,
`_allow_close` or packaging: **241 passed, 2 skipped, 0 failed** in 7 minutes 1 second
(`test_self_update`, `test_update_check`, `test_project_document_workflow`,
`test_workspace_recovery`, `test_beta69_feedback_qt`, `test_apf_workspace_recovery`,
`test_apf_project_document_workflow`, `test_b71_t5_project_open`, `test_discord_bugs_1`,
`test_2k5_audio_operation_integration`, `test_nfl2k5_music_fresh_rip_gui`,
`test_apf_audio_import_idle_barrier`, `test_team_kit_product_integration`,
`test_2k5_uniform_equipment_export`, `test_2k5_import_offers_resize`,
`test_apf_b711_overlay_books_qt`, `test_apf_theme_layout_qt`, `test_beta69_studios_offscreen`,
`test_phase1_packaging`). `packaging/repin.py` re-synced one pin, `mod_editor/gui/studio_qt.py`
in `packaging/check_2k5_mod_studio_runtime.py`, and then reported nothing further to apply.

## Limits of this evidence

Reproduced and fix-checked under Wine 9.0, not on real Windows. The mechanism is pure CPython
bytecode caching plus NSIS mtime restoration, neither of which is Wine specific, and the decisive
artefacts are the `.pyc` header and the on-disk source that disagree with each other. Windows
Defender, SmartScreen and Windows file locking were not exercised. The fix check used minimal
installers built through the changed builder rather than a full 75 MB release build, so the pinned
runtime assembly path was compiled but not re-downloaded. The `event.ignore()` paths other than
unsaved work and `_blocking` were read and reasoned about, then covered by refusing the update up
front rather than by driving each one.

A real Windows run of Update now from beta 74 to the first build carrying this change is still the
test that closes it, and Noah has not run one.

## Files changed

* `packaging/windows/build_windows_installer.py`: `RMDir /r` on both trees in the Install section;
  `SOURCE_DATE_EPOCH` becomes `SOURCE_DATE_EPOCH_ANCHOR` plus `source_date_epoch(version)`;
  `normalise_mtimes` takes the stamp.
* `mod_editor/gui/update_ui.py`: `prepare_to_close` and `_begin_update`; `_request_quit` closes and
  ends the event loop unconditionally; the confirmation text says when the unsaved question comes.
* `mod_editor/gui/studio_qt.py` and `mod_editor/apf_studio/gui.py`: `prepare_for_update_quit`.
* `tests/mod_editor/test_self_update.py`: twelve new tests.
* `docs/mod_editor/2k5_mod_studio_changelog.md`: the beta 74.1 entry.
* `STATUS.md`: the reproducibility note now says the stamp is per release.
* `packaging/check_2k5_mod_studio_runtime.py`: one pin re-synced by `packaging/repin.py --apply`.

No version constant was touched: `mod_editor/__init__.py` and `update_check.py` are unchanged.

## Files

* Report: `B75_U1_REPORT.md`
* Exit probe: `.scratch/exit_probe.py`
* Installers and logs: `.scratch/dl`, `.scratch/loop-*.log`, `.scratch/install7*.log`,
  `.scratch/probe-clean`, `.scratch/probe-dirty`
* The two Wine prefixes (`wine-loop`, `wine-update`) were 3.4 GB of scratch and have been removed.
  The table above is the exact command sequence to rebuild either one in about two minutes.
