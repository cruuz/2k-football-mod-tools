# Beta 71.1 U1: Linux tarball update and rollback

Implemented on `astra/b71-u1-linux-update`, based on
`02bbadd184e85498a441d3be71e70f8de94b9b0a`. The branch and all new Git objects live
in `.scratch/private.git`; the original worktree Git directory and HEAD were
not changed. Implementation commit: `9571ae83`. Delivery is the incremental
`.scratch/astra-b71-u1.bundle`, with the release-tree base as its prerequisite.
No push, network request, emulator, desktop display, or audio playback was used.
Qt execution was offscreen. All full extracted releases and test GUI processes
were cleaned up.

## Result and witness boundary

**PROVED:** the old tarball apply path loses an interpreter installed inside the
application folder. Running the shipped beta 70 updater against the shipped
beta 71 archive in a disposable install with `.venv/bin/python3` moves the runtime
into `.previous`, then raises `FileNotFoundError` trying its old path. With no
Python on `PATH`, reopening the launcher exits 1. The fixed updater passes a
real-payload, offscreen update/relaunch test and retains the local runtime.

**UNWITNESSED:** this is not an exact reconstruction of the reported SteamOS
desktop session. The untouched beta 70 archive unexpectedly contains an
allowlisted `tests/` directory, which its own detector treats as a source ZIP,
hiding Update now. The first reproduction exposed that refusal. The controlled
reproduction therefore explicitly supplies `InstallKind('tarball', ...)` to
exercise the shipped apply code without modifying that code or either archive.
The reported installation history, wrapper, runtime and actual clicked button
are unknown. Runtime loss is a demonstrated mechanism consistent with the
symptom, not proof of those unknown details. An ordinary system-Python install
did **not** brick in the same controlled update.

The report was: “Won't even open it anymore. If I entirely uninstall and go
through the whole reinstall process it works fine again.” A SteamOS desktop
confirmation is still needed after manual installation of this hotfix.

## Inputs and exact broken state

The hub alias supplied in the brief did not contain the tarballs. Both were
present under the read-only existing scratchpad at:

`/tmp/claude-1000/-home-noah-Desktop-2K5-8-Editors/7d06c350-f66f-4c4d-acf4-cdbdbedff1da/scratchpad/`

| Release | Relative asset path | Size | SHA-256, verified against local sidecar |
| --- | --- | ---: | --- |
| beta 70 | `b70/ship/assets70/2K5-Mod-Studio-v1.0-RC95-20260915.tar.gz` | 15,900,836 | `2f8e104f1c07769e5b93dda93b26c61bba1521985971e9d44225f56d265592ec` |
| beta 71 | `b71/ship/assets71/2K5-Mod-Studio-v1.0-RC96-20260916.tar.gz` | 16,067,243 | `aeb245db395605d62485e3b87700d0d10782b6c22bff9cc82ba6944f0e380b1a` |

These are local release copies, not a fresh independent download from GitHub.
Their `self_update.py` files are byte-identical to the base release tree.
They have a single top-level folder, 924/962 tar members, no symlinks, no Python
runtime, and no `__pycache__`. Packaging normalizes executable modes to 0755 and
regular files to 0644 (`packaging/build_archive.py:48`); the release gate rejects
runtime directories, compiled bytecode, links and undeclared payloads.

After the controlled legacy update, the sandbox contained:

```text
2K5-Mod-Studio-v1.0-RC95-20260915/              # beta 71 app, same shortcut path
    mod_editor/...                          # complete RC96 tree
    tools/launch_2k5_mod_studio.sh             # mode 0775 under this host's umask
    .venv/                                   # MISSING
2K5-Mod-Studio-v1.0-RC95-20260915.previous/     # intact beta 70 tree
    .venv/bin/python3                        # interpreter moved here
    mod_editor/__pycache__/sentinel.pyc       # old cache stays here
download/                                   # verified update and sidecar
state/                                      # sandbox launch diagnostics
```

There was no nested RC96 folder and no half-extracted replacement. The old app
cache was not copied into the new tree. The launcher remained executable, but
the old extraction code turned its shipped 0755 into 0775 on this umask; this
is a separate permission-preservation bug, not the observed missing interpreter.

## Root cause, with original release line numbers

- `mod_editor/core/self_update.py:136` rejects any `tests/` directory, including
  the one shipped in beta 70 and 71. This explains the raw archive's refusal.
- `detect_install`, lines 129 and 145, stores `sys.executable` in the tarball relaunch
  command. For a local venv this is `<install>/.venv/bin/python3`, not a system
  executable. Resolving that symlink to the base interpreter would also lose
  the venv's dependency environment.
- `unpack_tarball`, lines 320–352, extracts application files only. It has no
  runtime preservation or import/launch check. Line 345 adds execute bits to
  the umask-derived mode instead of applying the archived mode.
- `swap_install`, lines 355–365, deletes an older `.previous`, renames the live
  tree, and places the extracted tree at its path. Its rollback covers only
  the second rename, not subsequent startup failure.
- `apply_tarball`, line 397, switches before checking startup. Lines 412–416
  reuse the old interpreter path and call `Popen`. The venv was moved to
  `.previous`, and the incoming tarball carries no replacement: `Popen` raises
  `FileNotFoundError: [Errno 2] No such file or directory: '<install>/.venv/bin/python3'`.
  The reproduction child exits 1. The GUI's existing worker catches the error
  and keeps its current window open, but the on-disk installation is already
  switched and there is no automatic restore.
- Line 419 discards stdout/stderr and the updater never checks child exit status.
  If an interpreter starts but the new app fails during import, the updater
  can report success and close the old window with no traceback visible to the
  user. This second failure mode follows directly from the code; the historical
  SteamOS child traceback is **UNWITNESSED**.
- `tools/launch_2k5_mod_studio.sh:17–19` requires `python3` on `PATH` before
  resolving the app root. In the no-system-Python simulation after runtime
  loss, it exits 1 with “Python 3 is not installed. Install Python 3, PyQt5, and
  Pillow, then reopen 2K5 Mod Studio.” Terminal stderr was observed. A desktop
  launch would use zenity/kdialog if available, otherwise a terminal-less
  shortcut can show nothing. The actual SteamOS dialog behavior is unwitnessed.

The beta-57 ship/stack notes and RC81 changelog describe sibling extraction,
backup, relaunch and the Windows NSIS wait path. Their blanket claim that a
failure leaves the old copy untouched is not true for the demonstrated Linux
relaunch failure. The NSIS path has its own process wait and remains unchanged.

## Fix

- `self_update.py:333`: unique sibling staging, one stripped archive root,
  exact archived permission bits, bytecode excluded, and staging cleanup on
  failure. Special files and links in incoming archives are refused.
- `self_update.py:404`: copy the active in-folder Python runtime without moving
  the running environment. Internal absolute runtime links become relative;
  external base-Python links remain intact. A relative `.studio-python` selector
  makes the runtime usable both in staging and at the final path. An external
  active interpreter is recorded as an absolute path. Unsupported/conflicting
  runtime layouts are refused before switching.
- `self_update.py:449`: a fresh process imports the candidate app, CLI and GUI,
  verifies the app import comes from that candidate, prints its version and
  must exit 0. This runs before touching the current installation and again
  after switching, using the selected interpreter with isolated app paths and
  bytecode writes disabled.
- `self_update.py:381,522`: retain the previous tree using same-filesystem
  atomic renames. A pre-existing `.previous` is preserved and a unique backup
  name is used. A per-install sibling lock prevents overlapping transactions.
  Rename failure restores the original tree when the filesystem permits it.
- `self_update.py:474,487`: the new GUI acknowledges its first event loop after
  showing its window. An early exit, including exit 0 without acknowledgement,
  a spawn error, a post-switch check failure, or a 60-second startup timeout
  causes rollback. A timed-out child is stopped before restoring. The failed
  tree and `.update-launch.log` remain beside the restored app for inspection.
  Error messages name the failure, the old version's location and the next step.
  An unrecoverable filesystem rename refusal also names the retained backup.
- Both Linux launchers honor `.studio-python`, local `.venv`/`venv`/`runtime`
  interpreters, or `MOD_STUDIO_PYTHON`. `--update-check` imports the app and GUI,
  prints the version, and exits without a display. Runtime selection no longer
  requires modifying SteamOS's read-only system partition or finding a system
  Python. The tarball still does not manufacture a runtime where none exists.
- Two-line GUI acknowledgement hooks and updated banner wording are documented
  in `WIRING.md`. APF packaging contracts follow the selected interpreter. The
  2K5 GUI source seal was regenerated by `repin.py --apply`. No game writers,
  registry rows, cave reservations or Windows installer files changed. Both
  Windows handoff functions were compared byte-for-byte with the base.

There are two atomic renames, not a crash-atomic multi-directory transaction.
Power loss between them can require restoring `.previous` manually. A later
application crash after startup acknowledgement is outside this startup check.
Unknown custom runtime layouts safely refuse the update instead of guessing.
Projects stored inside the application folder remain in the retained old tree.

## Hotfix tag compatibility and rollout

Use **`beta-71.1`**. The beta 69 Git tag
`42a0e609c04a875cdf4142c2bf962756309b9019`, the shipped beta 70 archive and shipped
beta 71 archive all use the same numeric parser:
`^beta-(\d{1,6})(?:\.(\d{1,3}))?$`. They compare `(major, hotfix)` tuples, treating
an omitted hotfix as zero. All three implementations were executed against an
out-of-order mocked release list and selected `beta-71.1` as newer.

The generic tag filter additionally accepts 1–64 ASCII letters, digits, dots,
underscores and hyphens. Other spellings can pass that filter but do not get
numeric ordering; recognized numeric releases take precedence in selection.
`beta-71.1.1` is not recognized numerically. The parser grammar was already
correct and is unchanged. The fixed build's `BUILD_RELEASE_TAG` is now
`beta-71.1`, so it will not offer itself again. Product versions remain RC96
and alpha.92; no public release was created.

**Old code cannot retroactively receive the new transaction before applying
the hotfix.** Users with in-folder Python should manually extract the hotfix
to a separate folder and retain/copy their working runtime. Users already
affected can close the app, keep the failed new folder, and restore the intact
`.previous` folder to the original install path before proceeding. No system
partition write is needed. The old detector may offer only Get the update even
though its tag parser discovers the hotfix. The changelog explains the manual
migration without reporter names.

## Verification

**PROVED:** 146 tests passed across the following complete standalone files;
all final executions exited 0. Required suites and supplemental integration
checks are linked to full logs in the command receipts below.

| Suite | Tests |
| --- | ---: |
| `test_self_update.py` | 26 |
| `test_self_update_manual_layout.py` | 1 |
| `test_update_check.py` | 21 |
| `test_self_update_linux.py` | 14 |
| `test_provider_integrity.py` | 8 |
| `test_product_catalog.py` | 9 |
| `test_phase1_packaging.py` | 23 |
| `test_stage_release.py` | 10 |
| `test_apf_studio_installer.py` | 16 |
| `test_studio_shell_layout_qt.py` | 18 |

The new regression suite performs real temp-dir tarball-to-tarball updates,
retains a real venv-only dependency, executes the shipped shell launcher with
no Python on PATH, checks modes/layout/caches/backups, and exercises import,
rename, final-path check, spawn, child-exit and startup-timeout failures. A real
child acknowledges startup in the success case. Existing banner and NSIS tests
also pass.

The full-payload fixed replay uses beta 70's extracted tree and a beta 71 archive
overlaid with this patch's five 2K5 updater/launcher/GUI files. Its two checks
print `1.0.0rc96` and exit 0; the actual offscreen studio reaches its event loop.
The updated launcher prints `1.0.0rc96`, exits 0 with no Python on PATH, remains
0755, and leaves no app bytecode caches. The previous tree is retained. The
test then deliberately terminates its GUI (SIGTERM, -15), after successful
acknowledgement, and removes its sandbox. This termination is test cleanup,
not a startup failure. Final replay command: 17.575 seconds, exit 0.

Strict registry validation passed with **176 capabilities**, without skipping
file checks. Both clean allowlist stages passed release checks before and after
runtime execution: **2K5 917 files, 250 product modules + 35 tool modules**;
**APF 289 files, 161 modules**. The final combined release-gate command took
33.774 seconds, exit 0. Both launcher shell syntax checks passed. `repin.py
--apply` changed the one GUI source seal initially and subsequent runs reported
zero updates. The final `git diff --check` passed; the first report-generation
attempt left an extra blank line at EOF, which was corrected before delivery.

Failures retained in the evidence: the first raw-archive reproduction was
refused by the legacy detector; the controlled reproduction then proved the
runtime loss. The first supplemental APF run rejected its outdated literal
system-Python launcher contract, corrected in both gates. The next runs lacked
Capstone because those tests choose `python3` from PATH with user-site packages
disabled. A private offline test venv exposing the already installed Capstone,
Unicorn and NumPy, selected on PATH, passed all 16 tests. No dependency was
downloaded or installed into the system. These earlier failures are not hidden.
The first finalization attempt stopped at that report whitespace check before
committing or creating a bundle; its exact receipt is retained as
`reports/b71_u1/finalization-attempt1.json`.

**UNWITNESSED:** an actual SteamOS desktop update, that user's original layout,
live GitHub bytes, native Windows/macOS execution, later editing/building after
startup, and power-loss recovery. The no-system-Python test removes Python from
PATH, not from the host filesystem; its venv still has a working external base
interpreter. A wholly self-contained home runtime on a system lacking that
base is not a witnessed platform test. No emulator or in-game verification.

## Delivery

The implementation and evidence are explicit-path commits in
`.scratch/private.git`. The bundle exports only this branch's commits above
`02bbadd1`; it was verified against that base. The original worktree's `.git`
file still targets its original Git directory, whose HEAD remains `02bbadd1`.
`ASTRA_LAST_MESSAGE.md` ends with `ASTRA_DONE`. The command journal and report
include earlier failed attempts as well as final passing checks. Full output,
reproduction scripts, original shipped updater snapshots and all command
receipts are under `reports/b71_u1/`.

The final evidence commit/bundle operations are performed by
`python3 reports/b71_u1/finalize.py`. Their exact commands, UTC starts, durations,
exit codes, commit IDs and bundle SHA-256 are recorded in
[the finalization receipt](.scratch/delivery.json), outside the commits to avoid
a self-referential bundle hash. The report, test logs and reproduction scripts
are included in the bundle; the finalization receipt remains beside it.

<!-- U1 COMMAND LEDGER -->

## Command receipts

All shell commands after initial discovery run through `reports/b71_u1/run.py`. The JSONL ledger carries the exact command, UTC start, elapsed seconds, and exit status; each linked log contains the complete captured output. Reproduction and release-gate logs also record their child commands and statuses. Tool file edits are represented by the explicit-path commits. Initial read-only discovery receipts are transcribed from tool results below; one truncated timing is honestly unavailable.

| Command / output | UTC start | Seconds | Exit |
| --- | --- | ---: | ---: |
| [private-git](reports/b71_u1/private-git.log) | 2026-09-16T23:24:16.794358+00:00 | 2.747 | 0 |
| [packaging-read](reports/b71_u1/packaging-read.log) | 2026-09-16T23:24:38.980962+00:00 | 0.016 | 0 |
| [archives-inspect](reports/b71_u1/archives-inspect.log) | 2026-09-16T23:24:38.994329+00:00 | 0.978 | 0 |
| [install-read](reports/b71_u1/install-read.log) | 2026-09-16T23:24:46.399582+00:00 | 0.18 | 0 |
| [shipped-reproduction](reports/b71_u1/shipped-reproduction.log) | 2026-09-16T23:26:32.541618+00:00 | 6.29 | 1 |
| [readiness-read](reports/b71_u1/readiness-read.log) | 2026-09-16T23:26:49.785900+00:00 | 0.015 | 0 |
| [layout-detection](reports/b71_u1/layout-detection.log) | 2026-09-16T23:26:59.918330+00:00 | 0.269 | 0 |
| [shipped-reproduction-controlled](reports/b71_u1/shipped-reproduction-controlled.log) | 2026-09-16T23:27:26.246533+00:00 | 9.31 | 0 |
| [launcher-edit](reports/b71_u1/launcher-edit.log) | 2026-09-16T23:30:37.911158+00:00 | 0.023 | 0 |
| [manual-update-tests](reports/b71_u1/manual-update-tests.log) | 2026-09-16T23:34:01.062322+00:00 | 0.159 | 0 |
| [update-check-tests](reports/b71_u1/update-check-tests.log) | 2026-09-16T23:34:01.049383+00:00 | 0.207 | 0 |
| [linux-update-tests](reports/b71_u1/linux-update-tests.log) | 2026-09-16T23:34:01.020686+00:00 | 1.324 | 0 |
| [self-update-tests](reports/b71_u1/self-update-tests.log) | 2026-09-16T23:34:01.040169+00:00 | 1.79 | 0 |
| [review-diff](reports/b71_u1/review-diff.log) | 2026-09-16T23:34:13.890119+00:00 | 0.081 | 0 |
| [launcher-test-discovery](reports/b71_u1/launcher-test-discovery.log) | 2026-09-16T23:35:01.720486+00:00 | 0.073 | 0 |
| [strict-validator](reports/b71_u1/strict-validator.log) | 2026-09-16T23:35:01.721773+00:00 | 0.125 | 0 |
| [product-catalog](reports/b71_u1/product-catalog.log) | 2026-09-16T23:35:01.684464+00:00 | 0.194 | 0 |
| [phase1-packaging](reports/b71_u1/phase1-packaging.log) | 2026-09-16T23:35:01.699745+00:00 | 2.192 | 0 |
| [provider-integrity](reports/b71_u1/provider-integrity.log) | 2026-09-16T23:35:01.667121+00:00 | 10.749 | 0 |
| [repin-first](reports/b71_u1/repin-first.log) | 2026-09-16T23:35:29.036640+00:00 | 21.945 | 0 |
| [apf-installer-tests](reports/b71_u1/apf-installer-tests.log) | 2026-09-16T23:36:38.591030+00:00 | 0.608 | 1 |
| [launcher-contracts](reports/b71_u1/launcher-contracts.log) | 2026-09-16T23:36:49.599253+00:00 | 0.053 | 0 |
| [fixed-release-replay](reports/b71_u1/fixed-release-replay.log) | 2026-09-16T23:36:38.578354+00:00 | 17.57 | 0 |
| [tag-compatibility](reports/b71_u1/tag-compatibility.log) | 2026-09-16T23:37:19.730876+00:00 | 0.15 | 0 |
| [apf-installer-tests-fixed](reports/b71_u1/apf-installer-tests-fixed.log) | 2026-09-16T23:37:19.711060+00:00 | 9.58 | 1 |
| [validation-environment](reports/b71_u1/validation-environment.log) | 2026-09-16T23:37:53.795354+00:00 | 0.612 | 0 |
| [offline-test-runtime](reports/b71_u1/offline-test-runtime.log) | 2026-09-16T23:38:36.276584+00:00 | 0.25 | 0 |
| [apf-installer-runtime-complete](reports/b71_u1/apf-installer-runtime-complete.log) | 2026-09-16T23:38:36.800343+00:00 | 10.059 | 1 |
| [staged-release-gates](reports/b71_u1/staged-release-gates.log) | 2026-09-16T23:38:36.791573+00:00 | 35.515 | 0 |
| [final-test-discovery](reports/b71_u1/final-test-discovery.log) | 2026-09-16T23:39:19.149936+00:00 | 0.037 | 0 |
| [repin-before-code-commit](reports/b71_u1/repin-before-code-commit.log) | 2026-09-16T23:39:08.445197+00:00 | 11.485 | 0 |
| [apf-runtime-selection](reports/b71_u1/apf-runtime-selection.log) | 2026-09-16T23:39:33.147092+00:00 | 0.024 | 0 |
| [preserve-inherited-wiring](reports/b71_u1/preserve-inherited-wiring.log) | 2026-09-16T23:40:00.583572+00:00 | 0.032 | 0 |
| [stage-release-tests](reports/b71_u1/stage-release-tests.log) | 2026-09-16T23:40:00.771456+00:00 | 0.142 | 0 |
| [apf-installer-final](reports/b71_u1/apf-installer-final.log) | 2026-09-16T23:40:00.735090+00:00 | 15.019 | 0 |
| [studio-shell-tests](reports/b71_u1/studio-shell-tests.log) | 2026-09-16T23:40:00.756942+00:00 | 45.978 | 0 |
| [linux-update-final](reports/b71_u1/linux-update-final.log) | 2026-09-16T23:41:03.777051+00:00 | 1.338 | 0 |
| [self-update-final](reports/b71_u1/self-update-final.log) | 2026-09-16T23:41:03.790534+00:00 | 1.735 | 0 |
| [hotfix-marker-scope](reports/b71_u1/hotfix-marker-scope.log) | 2026-09-16T23:41:46.308904+00:00 | 0.008 | 0 |
| [update-check-final](reports/b71_u1/update-check-final.log) | 2026-09-16T23:42:09.116982+00:00 | 0.168 | 0 |
| [repin-code-final](reports/b71_u1/repin-code-final.log) | 2026-09-16T23:42:09.135492+00:00 | 11.136 | 0 |
| [code-commit](reports/b71_u1/code-commit.log) | 2026-09-16T23:43:18.837358+00:00 | 0.153 | 0 |
| [code-evidence](reports/b71_u1/code-evidence.log) | 2026-09-16T23:43:52.127932+00:00 | 0.085 | 0 |
| [fixed-release-final](reports/b71_u1/fixed-release-final.log) | 2026-09-16T23:43:52.119992+00:00 | 17.575 | 0 |
| [staged-release-final](reports/b71_u1/staged-release-final.log) | 2026-09-16T23:43:52.103646+00:00 | 33.774 | 0 |
| [report-line-audit](reports/b71_u1/report-line-audit.log) | 2026-09-16T23:48:10.867834+00:00 | 0.02 | 0 |
| [evidence-review](reports/b71_u1/evidence-review.log) | 2026-09-16T23:49:39.143464+00:00 | 0.048 | 0 |
| [retain-finalization-attempt](reports/b71_u1/retain-finalization-attempt.log) | 2026-09-16T23:50:34.013945+00:00 | 0.003 | 0 |

### Exact commands

<details><summary>private-git: exit 0, 2.747 seconds</summary>

```bash
git init --bare .scratch/private.git && git --git-dir=.scratch/private.git config core.bare false && git --git-dir=.scratch/private.git config core.worktree /home/noah/2k-worktrees/astra-b71-u1 && python3 -c 'from pathlib import Path; Path(".scratch/private.git/objects/info/alternates").write_text("/home/noah/2k-football-mod-tools/.git/objects\n")' && git --git-dir=.scratch/private.git update-ref refs/heads/astra/b71-u1-linux-update 02bbadd184e85498a441d3be71e70f8de94b9b0a && git --git-dir=.scratch/private.git symbolic-ref HEAD refs/heads/astra/b71-u1-linux-update && git --git-dir=.scratch/private.git read-tree HEAD && git --git-dir=.scratch/private.git status --short
```

</details>

<details><summary>packaging-read: exit 0, 0.016 seconds</summary>

```bash
sed -n '1,190p' packaging/stage_release.py && sed -n '168,280p' packaging/check_2k5_mod_studio_release.py && cat tools/launch_apf2k8_mod_studio.sh && rg -n 'strict|argparse' mod_editor/capabilities/validate_registry.py packaging/repin.py && rg --files packaging | sort
```

</details>

<details><summary>archives-inspect: exit 0, 0.978 seconds</summary>

```bash
python3 - <<'PY'
from pathlib import Path
import tarfile, sys, hashlib
base=Path('/tmp/claude-1000/-home-noah-Desktop-2K5-8-Editors/7d06c350-f66f-4c4d-acf4-cdbdbedff1da/scratchpad')
print('interpreter',sys.executable)
for tag in ('b70','b71'):
 p=next((base/tag/'ship'/('assets'+tag[1:])).glob('2K5*.tar.gz'))
 print(p, p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest())
 with tarfile.open(p) as a:
  m=a.getmembers();print('members',len(m),'bytes',sum(x.size for x in m),'tops',set(x.name.split('/')[0] for x in m))
  print('caches/venv/runtime/links',[(x.name,x.linkname) for x in m if '__pycache__' in x.name or '/.venv/' in x.name or '/runtime/' in x.name or x.issym()])
  for name in ('mod_editor/core/self_update.py','mod_editor/core/update_check.py','tools/launch_2k5_mod_studio.sh'):
   member=next(x for x in m if x.name.endswith('/'+name));payload=a.extractfile(member).read()
   out=Path('reports/b71_u1')/(tag+'-'+Path(name).name+'.txt');out.write_bytes(payload)
   print(name,oct(member.mode), 'same as HEAD',payload==Path(name).read_bytes())
PY
```

</details>

<details><summary>install-read: exit 0, 0.18 seconds</summary>

```bash
cat install.sh && cat packaging/build_archive.py && sed -n '1,160p' packaging/README.md && rg -n 'beta|hotfix|TAG' tests/mod_editor/test_update_check.py && git tag -l 'beta-69' && python3 -c 'from PyQt5 import QtWidgets; import PIL; import numpy; print("dependencies available")'
```

</details>

<details><summary>shipped-reproduction: exit 1, 6.29 seconds</summary>

```bash
python3 reports/b71_u1/reproduce.py
```

</details>

<details><summary>readiness-read: exit 0, 0.015 seconds</summary>

```bash
rg -n 'def launch_studio|\.show\(|exec_\(' mod_editor/gui/studio_qt.py mod_editor/apf_studio/gui.py && sed -n '1,130p' tests/mod_editor/test_self_update_manual_layout.py && sed -n '310,365p' mod_editor/capabilities/validate_registry.py && sed -n '1,110p' tests/mod_editor/test_phase1_packaging.py && git show beta-69:mod_editor/core/update_check.py | head -80
```

</details>

<details><summary>layout-detection: exit 0, 0.269 seconds</summary>

```bash
python3 - <<'PY'
from pathlib import Path
import tarfile
p=next(Path('/tmp/claude-1000/-home-noah-Desktop-2K5-8-Editors/7d06c350-f66f-4c4d-acf4-cdbdbedff1da/scratchpad/b70/ship/assets70').glob('2K5*.tar.gz'))
with tarfile.open(p) as a:
 for m in a.getmembers():
  if '/tests' in m.name or '/.github' in m.name: print(m.name)
PY
rg -n '^tests|.github' packaging/release-allowlist.txt && sed -n '9831,9875p' mod_editor/gui/studio_qt.py && sed -n '22123,22163p' mod_editor/apf_studio/gui.py
```

</details>

<details><summary>shipped-reproduction-controlled: exit 0, 9.31 seconds</summary>

```bash
python3 reports/b71_u1/reproduce.py
```

</details>

<details><summary>launcher-edit: exit 0, 0.023 seconds</summary>

```bash
python3 - <<'PY'
from pathlib import Path
for product, name in (('2k5','launch_2k5_mod_studio.sh'), ('apf','launch_apf2k8_mod_studio.sh')):
 p=Path('tools')/name
 text=p.read_text()
 start=text.index('if ! command -v python3')
 end=text.index('\nfi',start)+len('\nfi\n')
 text=text[:start]+text[end:]
 pos=text.index('\n',text.index('portable_root=$(dirname'))
 selector='''

# An in-app update records the interpreter that already runs this install.
# A local runtime travels with the app, so SteamOS needs no system changes.
studio_python=${MOD_STUDIO_PYTHON:-}
if [[ -z "$studio_python" && -f "$portable_root/.studio-python" ]]; then
    IFS= read -r studio_python < "$portable_root/.studio-python" || true
    if [[ -n "$studio_python" && "$studio_python" != /* ]]; then
        studio_python="$portable_root/$studio_python"
    fi
fi
if [[ -z "$studio_python" ]]; then
    for candidate in "$portable_root/.venv/bin/python3" "$portable_root/venv/bin/python3" "$portable_root/runtime/bin/python3"; do
        if [[ -x "$candidate" ]]; then
            studio_python=$candidate
            break
        fi
    done
fi
if [[ -z "$studio_python" ]]; then
    studio_python=$(command -v python3 || true)
fi
if [[ -z "$studio_python" || ! -x "$studio_python" ]]; then
    show_studio_error "The Python runtime for this copy is missing. Restore the previous application folder or select your installed Python with MOD_STUDIO_PYTHON, then reopen the studio."
    exit 1
fi
'''
 text=text[:pos]+selector+text[pos:]
 text=text.replace('if ! python3 ', 'if ! "$studio_python" ').replace('if python3 ', 'if "$studio_python" ').replace('exec python3 ', 'exec "$studio_python" ')
 text=text.replace('Install Python 3, PyQt5, and Pillow, then reopen 2K5 Mod Studio.', 'Restore the Python runtime and its PyQt5 and Pillow packages, then reopen 2K5 Mod Studio.')
 text=text.replace("'PyQt5 is missing from the system Python installation. On Linux Mint/Ubuntu, run: sudo apt install python3-pyqt5'", "'PyQt5 is missing from the selected Python runtime. Restore that runtime or install PyQt5 into it.'")
 text=text.replace("'Pillow is missing from the system Python installation. On Linux Mint/Ubuntu, run: sudo apt install python3-pil'", "'Pillow is missing from the selected Python runtime. Restore that runtime or install Pillow into it.'")
 module='mod_editor' if product=='2k5' else 'mod_editor.apf_studio'
 gui='mod_editor.gui.studio_qt' if product=='2k5' else 'mod_editor.apf_studio.gui'
 idx=text.index('\nif ! "$studio_python" -c')
 check=f'''\n# Headless launch check: imports the app and its GUI, prints the version, exits.\nif [[ "${{1:-}}" == "--update-check" ]]; then\n    exec "$studio_python" -B -s -c 'import {module}; import {module}.__main__; import {gui}; print({module}.__version__)'\nfi\n'''
 text=text[:idx]+check+text[idx:]
 if product=='2k5':
  text=text.replace('if command -v zenity', 'if [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]] && command -v zenity').replace('elif command -v kdialog','elif [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]] && command -v kdialog')
  text=text.replace('export PYTHONNOUSERSITE=1','export PYTHONNOUSERSITE=1\nexport PYTHONPATH="$portable_root"')
 p.write_text(text)
PY
```

</details>

<details><summary>manual-update-tests: exit 0, 0.159 seconds</summary>

```bash
QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONPATH=. python3 tests/mod_editor/test_self_update_manual_layout.py
```

</details>

<details><summary>update-check-tests: exit 0, 0.207 seconds</summary>

```bash
QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONPATH=. python3 tests/mod_editor/test_update_check.py
```

</details>

<details><summary>linux-update-tests: exit 0, 1.324 seconds</summary>

```bash
QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONPATH=. python3 tests/mod_editor/test_self_update_linux.py
```

</details>

<details><summary>self-update-tests: exit 0, 1.79 seconds</summary>

```bash
QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONPATH=. python3 tests/mod_editor/test_self_update.py
```

</details>

<details><summary>review-diff: exit 0, 0.081 seconds</summary>

```bash
git --git-dir=.scratch/private.git diff --stat && git --git-dir=.scratch/private.git diff --check && rg -n "except _RestoreError|_start_tarball|STARTUP_TIMEOUT" mod_editor/core/self_update.py && head -20 docs/mod_editor/2k5_mod_studio_changelog.md && rg --files tests/mod_editor -g "*launch*" -g "*installer*" -g "*shell*" && sed -n "156,205p" packaging/README.md && cat packaging/repin.py
```

</details>

<details><summary>launcher-test-discovery: exit 0, 0.073 seconds</summary>

```bash
rg -n 'launch_2k5_mod_studio|launch_apf2k8_mod_studio|notify_update_ready' tests/mod_editor && git --git-dir=.scratch/private.git diff --check
```

</details>

<details><summary>strict-validator: exit 0, 0.125 seconds</summary>

```bash
PYTHONPATH=. python3 mod_editor/capabilities/validate_registry.py
```

</details>

<details><summary>product-catalog: exit 0, 0.194 seconds</summary>

```bash
QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONPATH=. python3 tests/mod_editor/test_product_catalog.py
```

</details>

<details><summary>phase1-packaging: exit 0, 2.192 seconds</summary>

```bash
QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONPATH=. python3 tests/mod_editor/test_phase1_packaging.py
```

</details>

<details><summary>provider-integrity: exit 0, 10.749 seconds</summary>

```bash
QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONPATH=. python3 tests/mod_editor/test_provider_integrity.py
```

</details>

<details><summary>repin-first: exit 0, 21.945 seconds</summary>

```bash
python3 packaging/repin.py --apply
```

</details>

<details><summary>apf-installer-tests: exit 1, 0.608 seconds</summary>

```bash
QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONPATH=. python3 tests/mod_editor/test_apf_studio_installer.py
```

</details>

<details><summary>launcher-contracts: exit 0, 0.053 seconds</summary>

```bash
rg -n -C 7 'python3 -m mod_editor|launch_apf2k8_mod_studio.sh' packaging/check_apf2k8_mod_studio_release.py packaging/check_apf2k8_mod_studio_runtime.py packaging/check_2k5_mod_studio_runtime.py && sed -n '270,295p' tests/mod_editor/test_phase1_packaging.py && git --git-dir=.scratch/private.git diff --numstat && ls -ld reports/assets
```

</details>

<details><summary>fixed-release-replay: exit 0, 17.57 seconds</summary>

```bash
QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONPATH=. python3 reports/b71_u1/fixed_replay.py
```

</details>

<details><summary>tag-compatibility: exit 0, 0.15 seconds</summary>

```bash
python3 - <<'PY'
from pathlib import Path
from unittest.mock import patch
import subprocess, types, sys, hashlib
sources={'beta-69 git tag':subprocess.check_output(['git','show','beta-69:mod_editor/core/update_check.py'], text=True), 'beta-70 shipped tarball':Path('reports/b71_u1/b70-update_check.py.txt').read_text(), 'beta-71 shipped tarball':Path('reports/b71_u1/b71-update_check.py.txt').read_text()}
for n,(label,source) in enumerate(sources.items()):
 name=f'mod_editor.core._compat{n}'
 m=types.ModuleType(name);m.__package__='mod_editor.core';sys.modules[name]=m;exec(compile(source,label,'exec'),m.__dict__)
 print(label,hashlib.sha256(source.encode()).hexdigest(),'BUILD',m.BUILD_RELEASE_TAG,'_BETA',m._BETA.pattern,'_TAG',m._TAG.pattern)
 with patch.object(m,'_read',return_value=[{'tag_name':'beta-71'},{'tag_name':'beta-71.1'},{'tag_name':'beta-70'}]):
  r=m.check(m.BUILD_RELEASE_TAG);print(r);assert r.available and r.latest_tag=='beta-71.1'
 print('beta-71.1.1:',m._beta_number('beta-71.1.1'))
PY
bash -n tools/launch_2k5_mod_studio.sh tools/launch_apf2k8_mod_studio.sh
```

</details>

<details><summary>apf-installer-tests-fixed: exit 1, 9.58 seconds</summary>

```bash
QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONPATH=. python3 tests/mod_editor/test_apf_studio_installer.py
```

</details>

<details><summary>validation-environment: exit 0, 0.612 seconds</summary>

```bash
python3 - <<'PY'
import importlib.util, site
for n in ('capstone','unicorn','numpy','PyQt5'):
 s=importlib.util.find_spec(n);print(n,s.origin if s else None)
print(site.getsitepackages());print(site.getusersitepackages())
PY
rg -n 'strict|add_argument' tools/validate_all_mod_editor_capabilities.py && rg -n 'PYTHONNOUSERSITE|site|isolated|capstone' tests/mod_editor/test_apf_studio_installer.py packaging/check_apf2k8_mod_studio_runtime.py && rg --files /home/noah/.cache /tmp -g '*capstone*.whl' -g '*unicorn*.whl' 2>/dev/null | head -20
```

</details>

<details><summary>offline-test-runtime: exit 0, 0.25 seconds</summary>

```bash
python3 -m venv --without-pip --system-site-packages .scratch/test-env && python3 - <<'PY'
from pathlib import Path
import site, subprocess
runtime=Path('.scratch/test-env/bin/python3').resolve()
dest=Path(subprocess.check_output(['.scratch/test-env/bin/python3','-c','import sysconfig; print(sysconfig.get_path("purelib"))'],text=True).strip())
source=Path(site.getusersitepackages())
for pattern in ('capstone*','unicorn*','numpy*'):
 for p in source.glob(pattern):
  target=dest/p.name
  if not target.exists(): target.symlink_to(p,target_is_directory=p.is_dir())
print('offline test runtime uses pre-existing packages:', sorted(p.name for p in dest.iterdir()))
PY
PYTHONNOUSERSITE=1 .scratch/test-env/bin/python3 -c 'import capstone, unicorn, numpy; print(capstone.__version__, unicorn.__version__, numpy.__version__)'
```

</details>

<details><summary>apf-installer-runtime-complete: exit 1, 10.059 seconds</summary>

```bash
QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONPATH=. .scratch/test-env/bin/python3 tests/mod_editor/test_apf_studio_installer.py
```

</details>

<details><summary>staged-release-gates: exit 0, 35.515 seconds</summary>

```bash
.scratch/test-env/bin/python3 reports/b71_u1/release_gates.py
```

</details>

<details><summary>final-test-discovery: exit 0, 0.037 seconds</summary>

```bash
rg --files tests/mod_editor -g "*studio*" -g "*release*" -g "*update*" && git --git-dir=.scratch/private.git status --short
```

</details>

<details><summary>repin-before-code-commit: exit 0, 11.485 seconds</summary>

```bash
python3 packaging/repin.py --apply && git --git-dir=.scratch/private.git diff --check
```

</details>

<details><summary>apf-runtime-selection: exit 0, 0.024 seconds</summary>

```bash
sed -n '30,85p' tests/mod_editor/test_apf_studio_installer.py && sed -n '286,324p' tests/mod_editor/test_apf_studio_installer.py && sed -n '450,494p' tests/mod_editor/test_apf_studio_installer.py && git --git-dir=.scratch/private.git show HEAD:WIRING.md | head -25 && rg -n 'launch_studio|QApplication' tests/mod_editor/test_studio_shell_layout_qt.py tests/mod_editor/test_beta69_studios_offscreen.py && git --git-dir=.scratch/private.git ls-files ASTRA_REPORT.md ASTRA_LAST_MESSAGE.md
```

</details>

<details><summary>preserve-inherited-wiring: exit 0, 0.032 seconds</summary>

```bash
python3 - <<'PY'
from pathlib import Path
import subprocess
p=Path('WIRING.md');new=p.read_text();old=subprocess.check_output(['git','--git-dir=.scratch/private.git','show','HEAD:WIRING.md'],text=True);p.write_text(old+'\n'+new)
PY
```

</details>

<details><summary>stage-release-tests: exit 0, 0.142 seconds</summary>

```bash
QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONPATH=. python3 tests/mod_editor/test_stage_release.py
```

</details>

<details><summary>apf-installer-final: exit 0, 15.019 seconds</summary>

```bash
PATH="$PWD/.scratch/test-env/bin:$PATH" QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONPATH=. python3 tests/mod_editor/test_apf_studio_installer.py
```

</details>

<details><summary>studio-shell-tests: exit 0, 45.978 seconds</summary>

```bash
QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONPATH=. python3 tests/mod_editor/test_studio_shell_layout_qt.py
```

</details>

<details><summary>linux-update-final: exit 0, 1.338 seconds</summary>

```bash
QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONPATH=. python3 tests/mod_editor/test_self_update_linux.py
```

</details>

<details><summary>self-update-final: exit 0, 1.735 seconds</summary>

```bash
QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONPATH=. python3 tests/mod_editor/test_self_update.py
```

</details>

<details><summary>hotfix-marker-scope: exit 0, 0.008 seconds</summary>

```bash
rg -n 'BUILD_RELEASE_TAG|beta-71' tests/mod_editor/test_*update* packaging/check_*.py packaging/windows/build_windows_installer.py mod_editor/gui/update_ui.py mod_editor/gui/studio_qt.py mod_editor/apf_studio/gui.py | head -65
```

</details>

<details><summary>update-check-final: exit 0, 0.168 seconds</summary>

```bash
QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONPATH=. python3 tests/mod_editor/test_update_check.py
```

</details>

<details><summary>repin-code-final: exit 0, 11.136 seconds</summary>

```bash
python3 packaging/repin.py --apply && git --git-dir=.scratch/private.git diff --check
```

</details>

<details><summary>code-commit: exit 0, 0.153 seconds</summary>

```bash
git --git-dir=.scratch/private.git add -- 'mod_editor/core/self_update.py' 'mod_editor/core/update_check.py' 'mod_editor/gui/studio_qt.py' 'mod_editor/gui/update_ui.py' 'mod_editor/apf_studio/gui.py' 'tools/launch_2k5_mod_studio.sh' 'tools/launch_apf2k8_mod_studio.sh' 'packaging/README.md' 'packaging/check_2k5_mod_studio_runtime.py' 'packaging/check_apf2k8_mod_studio_release.py' 'packaging/check_apf2k8_mod_studio_runtime.py' 'tests/mod_editor/test_self_update.py' 'tests/mod_editor/test_self_update_linux.py' 'tests/mod_editor/test_update_check.py' 'docs/mod_editor/2k5_mod_studio_changelog.md' 'WIRING.md' && git --git-dir=.scratch/private.git commit -m 'Fix Linux tarball updates with checked staging and automatic rollback' -- 'mod_editor/core/self_update.py' 'mod_editor/core/update_check.py' 'mod_editor/gui/studio_qt.py' 'mod_editor/gui/update_ui.py' 'mod_editor/apf_studio/gui.py' 'tools/launch_2k5_mod_studio.sh' 'tools/launch_apf2k8_mod_studio.sh' 'packaging/README.md' 'packaging/check_2k5_mod_studio_runtime.py' 'packaging/check_apf2k8_mod_studio_release.py' 'packaging/check_apf2k8_mod_studio_runtime.py' 'tests/mod_editor/test_self_update.py' 'tests/mod_editor/test_self_update_linux.py' 'tests/mod_editor/test_update_check.py' 'docs/mod_editor/2k5_mod_studio_changelog.md' 'WIRING.md' && git --git-dir=.scratch/private.git log -1 --oneline
```

</details>

<details><summary>code-evidence: exit 0, 0.085 seconds</summary>

```bash
python3 - <<'PY'
import ast, subprocess
from pathlib import Path
old=subprocess.check_output(['git','show','02bbadd1:mod_editor/core/self_update.py'],text=True)
new=Path('mod_editor/core/self_update.py').read_text()
for function in ('windows_install_command','apply_windows_installer'):
 def body(src):
  return ast.get_source_segment(src, next(n for n in ast.parse(src).body if isinstance(n,ast.FunctionDef) and n.name==function))
 assert body(old)==body(new)
 print(function,'BYTE-FOR-BYTE UNCHANGED')
print('beta-69 tag', subprocess.check_output(['git','rev-parse','beta-69^{}'],text=True).strip())
PY
rg -n 'tests|relaunch|target.chmod|os.rename|subprocess.Popen|DEVNULL|swap_install' reports/b71_u1/b70-self_update.py.txt && rg -n 'python3|show_studio_error|exit 1' reports/b71_u1/b70-launch_2k5_mod_studio.sh.txt && rg -n '^def (_safe_members|unpack_tarball|swap_install|_stage_python|check_tarball_launch|notify_update_ready|_start_tarball|apply_tarball|run_update)|BUILD_RELEASE_TAG|_BETA =' mod_editor/core/self_update.py mod_editor/core/update_check.py && git diff 02bbadd1 -- packaging/windows/build_windows_installer.py && git --git-dir=.scratch/private.git diff --check && git rev-parse HEAD
```

</details>

<details><summary>fixed-release-final: exit 0, 17.575 seconds</summary>

```bash
QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONPATH=. python3 reports/b71_u1/fixed_replay.py
```

</details>

<details><summary>staged-release-final: exit 0, 33.774 seconds</summary>

```bash
.scratch/test-env/bin/python3 reports/b71_u1/release_gates.py
```

</details>

<details><summary>report-line-audit: exit 0, 0.02 seconds</summary>

```bash
nl -ba reports/b71_u1/b70-self_update.py.txt | sed -n '126,154p;320,367p;390,421p' && nl -ba packaging/build_archive.py | sed -n '42,63p' && rg -n 'def _on_done|except Exception|_update_failure|return InstallKind' mod_editor/gui/update_ui.py reports/b71_u1/b70-self_update.py.txt && du -sh .scratch && git --git-dir=.scratch/private.git diff --check
```

</details>

<details><summary>evidence-review: exit 0, 0.048 seconds</summary>

```bash
python3 - <<'PY'
from pathlib import Path
import json
rows=[json.loads(line) for line in Path('reports/b71_u1/commands.jsonl').read_text().splitlines()]
print('journal',len(rows),'commands; failed labels',[(r['label'],r['exit_code']) for r in rows if r['exit_code']])
assert Path('ASTRA_LAST_MESSAGE.md').read_text().rstrip().endswith('ASTRA_DONE')
for name in ('run.py','reproduce.py','fixed_replay.py','release_gates.py','render_command_report.py','finalize.py'):
 p=Path('reports/b71_u1')/name;compile(p.read_text(),str(p),'exec')
print('evidence scripts compile; completion marker present')
PY
git --git-dir=.scratch/private.git diff --stat && git --git-dir=.scratch/private.git diff --check
```

</details>

<details><summary>retain-finalization-attempt: exit 0, 0.003 seconds</summary>

```bash
cp .scratch/delivery.json reports/b71_u1/finalization-attempt1.json
```

</details>

### Initial discovery (before the journal)

<details><summary>Exit 0; 3.557e-06 seconds</summary>

```bash
pwd && rg --files -g 'AGENTS.md' -g 'ASTRA_CONTEXT.md' -g 'BETA71_TRIAGE.md' -g '*beta*57*' -g '*release*check*' -g 'repin.py' -g '*update*' -g '*validat*' -g '*phase1*' -g '*product*catalog*' -g '*provider*integrity*'
```



</details>

<details><summary>Exit 2; 0.549948276 seconds</summary>

```bash
git status --short && git rev-parse HEAD && git log -3 --oneline && ls -la .git .scratch
```

.scratch did not exist yet

</details>

<details><summary>Exit 0; 3.136e-06 seconds</summary>

```bash
cat ASTRA_CONTEXT.md BETA71_TRIAGE.md && cat mod_editor/core/self_update.py mod_editor/core/update_check.py
```



</details>

<details><summary>Exit 0; 0.110436398 seconds</summary>

```bash
rg --files -g AGENTS.md -g '*57*' -g '*release*' packaging .github && ls /home/noah && cat .git && rg -n 'WAITPID|RELAUNCH|beta.57|Beta 57' CHANGELOG* docs packaging mod_editor tests/mod_editor/test*update*
```



</details>

<details><summary>Exit 0; 3.527e-06 seconds</summary>

```bash
cat /home/noah/AGENTS.md && cat ASTRA_BRIEF.md && sed -n '/## Beta 71 release issues/,$p' BETA71_TRIAGE.md && cat mod_editor/core/self_update.py
```



</details>

<details><summary>Exit 2; time UNWITNESSED</summary>

```bash
ls packaging && sed -n '1710,1765p' docs/mod_editor/2k5_mod_studio_changelog.md && cat mod_editor/gui/update_ui.py && ls -lh '/home/noah/Desktop/2K5-8 Editors/session_scripts_2026-09-15/b70/ship/assets70/' && rg --files '/home/noah/Desktop/2K5-8 Editors' -g '*RC96*tar.gz' -g '*RC95*tar.gz' -g '*beta57*' -g '*BETA57*'
```

hub archive directory absent; timing was not retained from the truncated tool output (UNWITNESSED)

</details>

<details><summary>Exit 0; 3.146e-06 seconds</summary>

```bash
sed -n '130,470p' mod_editor/core/self_update.py
```



</details>

<details><summary>Exit 0; 4.087e-06 seconds</summary>

```bash
cat tools/launch_2k5_mod_studio.sh && rg -n 'tar|venv|python|runtime|chmod|launch' packaging/stage_release.py packaging/check_2k5_mod_studio_release.py .github/workflows/* && sed -n '1713,1765p' docs/mod_editor/2k5_mod_studio_changelog.md && ls '/home/noah/Desktop/2K5-8 Editors' && cat /home/noah/PROJECTS.md /home/noah/projects.json
```



</details>

<details><summary>Exit 0; 2.981270912 seconds</summary>

```bash
python3 - <<'PY'
from pathlib import Path
p=Path('/home/noah/Desktop/2K5-8 Editors')
print('hub',p.exists(),p.resolve())
for root in (p,Path('/home/noah/Downloads'),Path('/tmp')):
 for pat in ('*RC95*.tar.gz','*RC96*.tar.gz','*BETA57*','*beta57*'):
  for f in root.rglob(pat): print(f, f.stat().st_size)
PY
```



</details>

<details><summary>Exit 0; 4.458e-06 seconds</summary>

```bash
sed -n '1716,1755p' docs/mod_editor/2k5_mod_studio_changelog.md && cat tests/mod_editor/test_self_update.py
```



</details>

<details><summary>Exit 2; 2.855e-06 seconds</summary>

```bash
mkdir -p .scratch reports/b71_u1 && git rev-parse --git-common-dir && df -h . /tmp && rg -n 'Python|venv|Steam|pip' docs/mod_editor/*install* tools/install* tools/launch_apf2k8_mod_studio.sh && sed -n '1,200p' packaging/stage_release.py && sed -n '168,280p' packaging/check_2k5_mod_studio_release.py
```

nonexistent discovery globs; subsequent packaging reads were rerun and journalled

</details>

<details><summary>Exit 0; 3.115e-06 seconds</summary>

```bash
cat '/home/noah/Desktop/2K5-8 Editors/BETA57_SHIP_2026-09-03.md' && rg -n -i 'updat|tarball|python' '/home/noah/Desktop/2K5-8 Editors/BETA57_STACK_2026-09-03.md' && cat mod_editor/__init__.py && sed -n '1,100p' mod_editor/__main__.py && cat mod_editor/apf_studio/__main__.py && sed -n '1,85p' mod_editor/apf_studio/__init__.py
```



</details>
