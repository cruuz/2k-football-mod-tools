"""Assemble the offline handoff from recorded receipts, without game payloads."""
import json
from pathlib import Path
import re
import statistics

root = Path(__file__).resolve().parents[2]
report = root/'reports/b72-a2'
rows = json.loads((report/'test-results.json').read_text())
assert all(row['exit_code'] == 0 for row in rows), 'Do not publish a green report with failing files'
total = sum(row['tests'] for row in rows)
skipped = sum(int(n) for row in rows for n in re.findall(r'OK \(skipped=(\d+)\)', (report/'tests'/f"{Path(row['file']).stem}.log").read_text()))
before = json.loads((report/'timing-before.json').read_text())['timings']
after = json.loads((report/'timing-after.json').read_text())['timings']
ten = json.loads((report/'timing-ten-edits.json').read_text())
qt_log = (report/'tests/test_b72_a2_editor_blockers.log').read_text()
qt = json.loads(re.search(r'B72_QT_REFRESH_MS=(.*)', qt_log)[1])

def loc(path, needle):
    lines = (root/path).read_text().splitlines()
    return f'`{path}:{next(i for i, line in enumerate(lines, 1) if needle in line)}`'

session = 'mod_editor/apf_studio/session.py'
gui = 'mod_editor/apf_studio/gui.py'
qtfile = 'mod_editor/apf_studio/playcalling_editor_qt.py'
newtest = 'tests/mod_editor/test_b72_a2_editor_blockers.py'
text = f'''# b72-a2: APF72-B offline handoff

Base: `088e3f41`, APF `0.1.0-alpha.93`. Scope is exactly the five APF72-B editor blockers. Gameplay remains UNWITNESSED. No emulator, audio playback, disc image, runtime patch, version constant, or core writer changed.

## Changes and dossier citations

| Item | Reporter cite and dossier location | Original cause | Implemented path and regression |
| --- | --- | --- | --- |
| U20/U11, slow tabs | Urianus DM, 2026-09-17 4:49 PM #4, "still re-reads and reloads the entire thing after every edit"; 2026-09-15 10:52 PM, "3-20 seconds". `BETA72_APF_DOSSIER.md:22`, `:31`, `:65`, `:81`. | `session.py:2762-2773`, `:2394-2412`, `playbook_membership_qt.py:1600-1607` at base. | Source books and compiled MASTER/SPLB results are session-owned and keyed by source byte SHA-256 plus normalized staged requests. Successful compiled results alone are reused; changed requests, Undo and a new source session select a new key. {loc(session, 'def compiled_splb_book')}, {loc(session, 'def _compile_master_play')}. Fine-tune, map and route panels offer optional pending edits and bulk confirmation with one Undo action. {loc(newtest, 'def test_all_three_warm_qt')}. |
| U18, Shovel/relay | Urianus DM, 2026-09-17 4:49 PM #2, "after using a relay play once ... on the next slot". `BETA72_APF_DOSSIER.md:29`, `:66`, `:81`. | Original MASTER body at `session.py:2314-2322`, relay checks at `:2624-2642`; writer chain-set guard at `core/apf2k8_playbook_route_writer.py:396-407`. | Relay multiplicities use the same compiled staged view as validation, and a relay carries the target's currently staged route using a stable stock selector. {loc(session, 'def relay_play_assignment_route_candidates')}, {loc(session, 'def copy_play_assignment_route_via_relay')}. Exact local H Shovel Strong/H Lead Shovel OL regression: {loc(newtest, 'def test_shovel_ol')}. The base fails the consumed-relay assertion; the fix preserves every original chain start. |
| U19, sorting | Urianus DM, 2026-09-17 4:49 PM #3, "Sorting doesn't work for any of the tables under CPU Play Calling". `BETA72_APF_DOSSIER.md:30`, `:64`, `:81`. | Shared `playcalling_editor_qt.py:60-78` had no sorting. | All nine tables enable sorting with numeric comparison and a stable original-row key. Refill disables sorting while populating complete rows, restores selection and preserves the sort indicator. Category, candidate and pending buttons resolve model rows after sorting. {loc(qtfile, 'class SortableItem')}, {loc(qtfile, 'def fill')}, {loc(newtest, 'def test_all_nine')}. |
| U17, recent projects | Urianus DM, 2026-09-17 4:49 PM #1, "listed ones aren't clickable". `BETA72_APF_DOSSIER.md:28`, `:63`, `:81`. | `gui.py:20372-20376` required `source_ready`. | Recent projects stay enabled on a cold start and remember the source in private workspace metadata. Loading is source first, project second, through existing recognition and fingerprint validation. Missing sources report a next step. {loc(gui, 'def _load_project_with_source')}, {loc('mod_editor/apf_studio/project.py', 'def record_project')}, {loc(newtest, 'def test_recent_project_cold')}. |
| U12, empty destination | Urianus DM, 2026-09-17 2:00 PM, "Error when building a game folder into an empty folder". `BETA72_APF_DOSSIER.md:23`, `:62`, `:81`. | GUI `gui.py:21788` only prompted for non-empty folders, but `build.py:815-820` rejected every existing folder. | Existing empty directories are valid without a replacement flag or prompt. Non-empty destinations require confirmation; the source-root guard is unchanged. Publication refuses if an unconfirmed empty target gained files during the build. {loc('mod_editor/apf_studio/build.py', 'if not replace_existing and any(output_game.iterdir())')}, {loc(newtest, 'def test_empty_build_folder')}, {loc(newtest, 'def test_writer_accepts_empty')}. |

## Timing proof

Local fixture: O-ManBlock, outer 130; retail MASTER has 586 plays. Measurements use `time.perf_counter`, five warm repetitions after first load, offscreen Qt on this Linux host. They do not describe in-game performance or native Windows/macOS timings.

| Repeated validation/query path | Base median ms | Changed median ms | Changed maximum ms |
| --- | ---: | ---: | ---: |
'''
for name in before:
    text += f"| {name} | {before[name]['median_ms']:.3f} | {after[name]['median_ms']:.3f} | {after[name]['max_ms']:.3f} |\n"
text += '\nActual Qt refreshes with membership, package-map and route edits staged, including processing the event queue after the first-load layout:\n\n| Tab | Median ms | Maximum ms |\n| --- | ---: | ---: |\n'
for name, values in qt.items():
    text += f'| {name} | {statistics.median(values):.3f} | {max(values):.3f} |\n'
text += f'''
All three refresh maxima are below 100 ms. The ten-edit Fine-tune panel benchmark measured {ten['before']['total_edit_ms']:.1f} ms at the base versus {ten['after']['total_edit_ms']:.1f} ms for pending edits plus {ten['after']['confirm_ms']:.1f} ms for confirmation. The output SHA-256 matches exactly: `{ten['after']['replacement_sha256']}`. The H7A encoder was replaced with an assertion during the edit loop. Pending-mode regressions also replace compilers with assertions, then confirm through the real writers. Full checks remain at confirmation and build.

Receipts: `reports/b72-a2/timing-before.json`, `timing-after.json`, `timing-ten-edits.json`, `tests/test_b72_a2_editor_blockers.log`, and `shovel-before.log`. No retail payload is included.

## Verification

Standalone CI-style run: **{len(rows)} files, {total} tests, {skipped} explicit skips, zero file failures**. Skips remain visible in each log. The existing playcalling suites pass. The focused pytest run also passed 64 tests before the standalone sweep. The sweep caught a Coverage Geometry source/defaults regression, which was fixed by retaining the source accessor and adding an explicit staged accessor. Its complete integration suite passes after the correction. Installer isolation initially hid the host's user-site Capstone; the unchanged installer tests pass with Capstone 5.0.7 available in a local test virtual environment. Initial and final receipts are retained separately.

Commands run from the worktree root:

```sh
python3 reports/b72-a2/run_tests.py
python3 reports/b72-a2/benchmark.py --baseline
python3 reports/b72-a2/benchmark.py
QT_QPA_PLATFORM=offscreen python3 reports/b72-a2/benchmark_edits.py
QT_QPA_PLATFORM=offscreen python3 reports/b72-a2/prove_shovel_baseline.py
```

Selected final reruns use `reports/b72-a2/rerun_tests.py` with `.scratch/test-venv/bin/python3` and that environment's `bin` directory first on `PATH`, so the installer subprocess uses the same installed dependencies. `final-rerun.log` lists the exact rerun files and interpreter. `repin-check.log` reports zero pin updates.

The runner invokes each file as `QT_QPA_PLATFORM=offscreen PYTHONPATH=<repo> python3 <file>`, two independent files at a time, with the timing test last and alone. `test-results.json` records each file's latest exit code and duration. `test-results-initial.json` and `tests-initial/` retain the initial sweep and superseded rerun receipts. `test-files.txt` records the exact selection, and `tests/` holds complete output. The Shovel baseline command succeeds only when the original consumed-relay assertion fails as expected.

| Test file | Tests | Exit |
| --- | ---: | ---: |
'''
for row in rows:
    text += f"| `{row['file']}` | {row['tests']} | {row['exit_code']} |\n"
text += '''
## Boundaries and delivery

- Pending mode is optional and starts off, matching the existing CPU Play Calling workflow. Pending edits require confirmation before the main Build action. Fine-tune and route confirmation are atomic; failures retain pending edits and restore the session.
- Older recent-project records contain no project-to-source binding. They remain clickable and explain that the source must be loaded once. New saves and opens record the binding locally; project archives still contain no machine-specific source paths.
- Paths use `Path`/`os.fspath`, temporary locations use `tempfile`, and offscreen tests include paths with spaces. Native Windows/macOS execution was not performed.
- `tools/apf_h7a_optimal` is mode 0755. No helper rebuild or umask-induced mode change is shipped. No pinned core writer changed, so no repin or registry count change is required.
- The checkout's shared `.git` is read-only in this sandbox. Commits and branch `b72-a2` are assembled in `.scratch/b72-a2.git`, using read-only access to the base objects. Product edits remain in this worktree. The portable delivery is `.scratch/astra-b72-a2.bundle`; its prerequisite is `088e3f41`. No shared checkout, other worktree, or remote was changed.
- `WIRING.md` records zero new capability rows and no protected-file changes. All five fixes are offline-proved editor behavior. Gameplay remains UNWITNESSED; no in-game acceptance claim is made.
'''
(root/'ASTRA_REPORT.md').write_text(text)
summary = [
'b72-a2 completes exactly the five APF72-B editor blockers.',
'Base is 088e3f41, APF 0.1.0-alpha.93.',
'SPLB and MASTER caches use source byte hashes plus staged edit sets.',
'Changed edits and source reloads cannot reuse a mismatched compiled view.',
'Fine-tune Plays supports pending edits and bulk confirmation.',
'Who lines up supports pending maps and bulk confirmation.',
'Assignment Routes supports pending copies/swaps and bulk confirmation.',
'Failed bulk confirmation restores the session and preserves pending edits.',
f"Ten O-ManBlock edits: {ten['before']['total_edit_ms']:.1f} ms before; {ten['after']['total_edit_ms']:.1f} ms plus {ten['after']['confirm_ms']:.1f} ms confirm after.",
'Compiled output hashes match; staging did not invoke the H7A encoder.',
'All three warmed Qt tab refreshes measured below 100 ms.',
'The reported two-Shovel OL sequence passes and preserves every chain start.',
'Consumed relay slots disappear from the staged candidate list.',
'All nine CPU Play Calling tables sort numerically and preserve model mapping.',
'Cold recent-project actions load their recorded source before the project.',
'Missing source paths produce a clear error and next step.',
'Empty build targets work without prompting; non-empty targets still require confirmation.',
f'{len(rows)} standalone APF test files ran: {total} tests, {skipped} explicit skips, zero file failures.',
'ASTRA_REPORT.md contains every citation, file:line, command, test file, and timing receipt.',
'Delivery: .scratch/astra-b72-a2.bundle, branch b72-a2. Offline proof only; gameplay UNWITNESSED.'
]
assert len(summary) == 20
(root/'ASTRA_LAST_MESSAGE.md').write_text('\n'.join(summary)+'\nASTRA_DONE\n')
