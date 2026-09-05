# Local Windows CI runner: implementation and blocked acceptance

The runner, documentation and runner tests are implemented. **The requested
Windows acceptance is not complete.** This session's execution sandbox kills
Wine with SIGSYS before Python starts, and mounts the shared Git metadata
read-only. No native WinError 5, GREEN pass, successful Windows import proof,
Qt offscreen result, or full Windows matrix timing was obtained. These are
environment blockers, not evidence that Wine does or does not reproduce the
beta-60 handle-sharing failure.

The checkout is branch `astra/win-local-ci`, HEAD `b8d55f4`, with parent
`89938fa`. No product code, workflow, installer builder, pins, installer
`._pth`, release allowlist or existing tests were changed. `ASTRA_BRIEF.md`
remains as supplied and is excluded from the commit paths. Nothing was pushed.

## Implementation decisions

`packaging/windows/local_windows_ci.py` implements the requested CLI. Its
default is CI's entire sorted test-file loop, continuing after failures;
`--keep-going` is an explicit spelling of that default. `--only` accepts
multiple names/globs and repeated occurrences, rejects unmatched patterns,
and intersects with `--changed`. Changed selection uses the existing local
`origin/main` merge-base without fetching, includes dirty/untracked files and
deleted/renamed Python module stems, and searches test text literally. It is
a useful heuristic, not a dependency graph.

The runtime cache calls the unchanged installer `build_runtime`. A separate
`runner-runtime` copy changes only `python312._pth` and adds
`winci-bootstrap/sitecustomize.py`. This hook restores the script directory
and the current process's Windows `PYTHONPATH`, including in child Python
processes. No checkout is hardcoded into either file. The isolated installer
test runs with `PYTHONPATH` absent. The bootstrap replaces its own `-c`
working-directory entry with the test script's directory, so the isolated
parent does not inadvertently retain the repo on `sys.path`.

Every invocation checks Wine startup, Windows CPython 3.12.10 facts, the actual
Qt platform, and imports before starting the matrix. The normal import probe
uses the real checkout; the isolated child uses a small synthetic staged
`mod_editor` package. Both paths are printed and asserted. Setup failures exit
2 and produce no misleading all-passed summary. Test failures exit 1. The
runner writes full test outputs and setup diagnostics under `WORK/logs`.

The exact 12-file lean-checkout skip list and the isolated-file name are
tested against `.github/workflows/ci.yml`. Unlike the brief's expectation,
`reports/assets/nfl2k5_all_txtr_inventory_v2.json` is absent here; this is a
lean checkout. The current plan has 302 files (301 existing plus the new
runner test), of which those 12 would be skipped. No speculative Wine skips
were added. Since no Windows test executed, there are no observed per-test
Wine environment gaps to classify or skip precisely.

Each test writes its Windows PID before executing. On timeout, the runner
targets that PID with `wine taskkill /PID PID /T /F`, bounds cleanup at 30
seconds, and kills the Unix launcher's process group. It logs `TIMED OUT`
and returns 124. It never invokes `wineserver -k`. Ctrl-C cancels pending files
and signals active workers to use the same cleanup. Cache and prefix locks
prevent concurrent invocations from overwriting one another's state. Prefixes
must be empty or already owned by this runner; existing unrelated prefixes
are refused. DISPLAY/Wayland, Wine desktop integration, Wine audio drivers,
and optional Mono/Gecko setup are disabled in the child environment.

The default remains `-j 1`. This machine reports 32 logical CPUs and 31 GiB
RAM, but **no parallel Wine setting is verified safe**. `-j 2` is the first
conservative setting to validate once Wine execution is available.

## Runtime build and cache measurements

Only the supplied temporary installer-build inputs were read. They were
copied into this task's `/tmp/astra-winci/dl`; no network download occurred.

```bash
mkdir -p /tmp/astra-winci/dl
cp /tmp/claude-1000/-home-noah/1ab9b8ce-0080-4b80-854c-2054d84ff31f/scratchpad/win-work60e/dl/* /tmp/astra-winci/dl
PIP_NO_INDEX=1 PIP_FIND_LINKS=/tmp/astra-winci/dl python3 - <<'PY'
import importlib.util
from pathlib import Path
import time
spec = importlib.util.spec_from_file_location('installer', 'packaging/windows/build_windows_installer.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
start = time.monotonic()
module.build_runtime(Path('/tmp/astra-winci'), Path('/tmp/astra-winci/dl'))
print(f'BUILD_RUNTIME_SECONDS={time.monotonic() - start:.3f}')
PY
```

Result (pip also noted its unwritable host cache and disabled it):

```text
      verified 4 pinned wheels + the interpreter
BUILD_RUNTIME_SECONDS=1.557
```

Calling the runner's `ensure_runtime` twice with those same offline settings
measured:

```text
      verified 4 pinned wheels + the interpreter
FIRST_ENSURE_RUNTIME_SECONDS=2.188
CACHED_ENSURE_RUNTIME_SECONDS=0.000
INSTALLER_RUNTIME_FILES 2674 BYTE_IDENTICAL_EXCLUDING_EXISTING_BYTECODE True
PRIVATE_RUNTIME_DIFFERENCES ['python312._pth', 'winci-bootstrap/sitecustomize.py']
PLAN_FILES 302
LEAN_SKIPS 12
CHANGED_PLAN_FILES 178
```

The source runtime contained one extra generated
`Lib/site-packages/PyQt5/__pycache__/__init__.cpython-312.pyc`. All 2,674 actual
runtime build files matched by relative path and SHA-256. The installer
builder itself is unchanged. This verifies runtime content preservation;
it is not a fresh NSIS installer rebuild/hash proof. Download cost, prefix
initialization cost, and warm Wine startup remain unmeasured. The cached
runtime check timing alone does not establish an end-to-end speedup.

## Offscreen oddity

The pinned wheel contains `qoffscreen.dll`, alongside `qminimal.dll`,
`qwebgl.dll`, and `qwindows.dll`; the plugin is not missing from these inputs.
Local import-table inspection with:

```bash
objdump -p /tmp/astra-winci/runtime/Lib/site-packages/PyQt5/Qt5/bin/Qt5Core.dll | rg -i 'DLL Name|putenv|getenv'
```

shows Qt imports `_putenv_s`, `getenv_s` and `_wgetenv_s` through
`api-ms-win-crt-environment-l1-1-0.dll`. Separate CRT environment tables are
therefore worth checking, but **the cause of the earlier `windows` platform
result is not established**. Wine cannot start in this session to repeat it.

The private startup hook records the incoming `os.environ`, `msvcrt` and
`ucrtbase` QPA values and sets all three to `offscreen` before importing Qt.
The OS probe prints those incoming values and creates `QApplication` without
a `-platform` override, then requires `platformName() == 'offscreen'`.
This is an implemented mitigation and a diagnostic for the next live run,
not a claim that the oddity has been resolved experimentally.

## Exact RED/GREEN attempts

The requested commands were attempted first:

```text
$ git worktree add /tmp/winci-red 89938fa
Preparing worktree (detached HEAD 89938fa)
fatal: could not create directory of '/home/noah/2k-football-mod-tools/.git/worktrees/winci-red': Read-only file system

$ git worktree add /tmp/winci-green b8d55f4
Preparing worktree (detached HEAD b8d55f4)
fatal: could not create directory of '/home/noah/2k-football-mod-tools/.git/worktrees/winci-green': Read-only file system
```

As a read-only alternative for obtaining the exact source revisions, archive
snapshots were extracted into the otherwise absent `/tmp` targets. These were
**snapshots, not registered Git worktrees**; no shared Git metadata or other
working tree was changed:

```bash
mkdir /tmp/winci-red /tmp/winci-green
git archive 89938fa | tar -x -C /tmp/winci-red
git archive b8d55f4 | tar -x -C /tmp/winci-green
chmod 0755 /tmp/winci-red/tools/apf_h7a_optimal /tmp/winci-green/tools/apf_h7a_optimal
```

The runner then produced these exact combined stdout/stderr outputs. Exit
codes and wall times were measured by an enclosing Python subprocess caller:

```text
$ python3 /home/noah/2k-worktrees/astra-win-local-ci/packaging/windows/local_windows_ci.py --repo /tmp/winci-red --work /tmp/astra-winci --only test_modpack.py
SETUP FAILED: wine failed (rc=-31) (SIGSYS: execution sandbox denied a system call); log: /tmp/astra-winci/logs/wine-version.log

EXIT_CODE=2
WALL_CLOCK_SECONDS=0.228

$ python3 /home/noah/2k-worktrees/astra-win-local-ci/packaging/windows/local_windows_ci.py --repo /tmp/winci-green --work /tmp/astra-winci --only test_modpack.py
SETUP FAILED: wine failed (rc=-31) (SIGSYS: execution sandbox denied a system call); log: /tmp/astra-winci/logs/wine-version.log

EXIT_CODE=2
WALL_CLOCK_SECONDS=0.224
```

No test body, including `GrowingSpecialPackTests.test_special_round_trip_and_raw_partition`,
ran. There is no observed `os.replace` result to report, and no basis to
conclude that Wine fails to emulate sharing violations. No file-handle shim
or fabricated Windows failure was added. The snapshots were removed after
these attempts; transcripts remain under `/tmp/astra-winci/`.

## Exact full-matrix attempt

```text
$ python3 /home/noah/2k-worktrees/astra-win-local-ci/packaging/windows/local_windows_ci.py --repo /home/noah/2k-worktrees/astra-win-local-ci --work /tmp/astra-winci
SETUP FAILED: wine failed (rc=-31) (SIGSYS: execution sandbox denied a system call); log: /tmp/astra-winci/logs/wine-version.log

EXIT_CODE=2
WALL_CLOCK_SECONDS=0.175
```

**SUMMARY: not produced; zero Windows test files executed.** The 0.175 seconds
is setup-failure latency, not matrix runtime. No comparison against GitHub's
approximately 20–30 minutes is valid yet. There is one observed cause for
this attempt's failure: Wine startup receives SIGSYS in the execution
sandbox. The lean evidence gap would apply after setup, independently.

## Validation and remaining work

The plain unittest file exercises arguments, plans, a real temporary Git
merge-base/dirty-file selection, CI skip/isolation parity, counts and summary
accounting, log tails, environment clearing, cache invalidation and installer
preservation, actual native CPython `._pth` startup and isolated child imports,
prefix ownership/locking, process-group timeout cleanup, and bounded Windows
taskkill orchestration. Native subprocess tests do not impersonate Windows.
The Wine availability test uses `skipTest` when Wine is absent or startup is
denied by this sandbox; pure tests still run on supported hosts.

Final validation commands and results:

```text
$ python3 tests/mod_editor/test_local_windows_ci.py
.......................s
----------------------------------------------------------------------
Ran 24 tests in 1.251s

OK (skipped=1)
```

`python3 -m py_compile packaging/windows/local_windows_ci.py
tests/mod_editor/test_local_windows_ci.py` and `git diff --check` both exited
0. The one skip is the Wine availability check reporting SIGSYS.

Required follow-up outside this sandbox: execute `--os-check`, repeat the
actual RED/GREEN worktree proof, validate Wine child-tree timeout cleanup,
restore the locally expected evidence inputs, run the full matrix, classify
every failure, and only then benchmark `-j 2`. Native Windows CI remains
necessary for filesystem, desktop, installer, driver and dependency-version
differences, and for Python 3.11. This task does not claim that acceptance
has been met.

## Commit attempt

Both requested explicit-path operations were attempted. Staging failed
because this worktree's index lives in the read-only shared Git directory;
the subsequent commit could not include the untracked deliverables:

```text
$ git add packaging/windows/local_windows_ci.py tests/mod_editor/test_local_windows_ci.py packaging/README.md ASTRA_WIN_LOCAL_CI_REPORT.md
fatal: Unable to create '/home/noah/2k-football-mod-tools/.git/worktrees/astra-win-local-ci/index.lock': Read-only file system

$ git commit -m 'Add local Windows CI runner using the pinned installer runtime' -- packaging/windows/local_windows_ci.py tests/mod_editor/test_local_windows_ci.py packaging/README.md ASTRA_WIN_LOCAL_CI_REPORT.md
error: pathspec 'packaging/windows/local_windows_ci.py' did not match any file(s) known to git
error: pathspec 'tests/mod_editor/test_local_windows_ci.py' did not match any file(s) known to git
error: pathspec 'ASTRA_WIN_LOCAL_CI_REPORT.md' did not match any file(s) known to git
```

No commit was created. The four deliverables remain in this worktree for
review and an explicit-path commit when Git metadata is writable. No
permission escalation, sandbox bypass or push was attempted.
