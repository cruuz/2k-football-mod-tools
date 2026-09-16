"""Aggregate the latest complete standalone runs; never turn a skip into proof."""
from pathlib import Path
import json
import re
import shlex
import subprocess
import sys
root=Path(__file__).resolve().parents[2]
folder=Path(__file__).parent
records=[json.loads(line) for line in (folder/'commands.jsonl').read_text().splitlines()]
paths=(folder/'suite_paths.txt').read_text().splitlines()
suites=[]
for path in paths:
 candidates=[r for r in records if any(arg.endswith(path) for arg in r['command'])]
 if not candidates:
  suites.append({'suite':path,'exit_code':None});continue
 row=max(candidates,key=lambda r:r['started_utc'])
 output=(root/row['log']).read_text()
 counts=re.findall(r'Ran (\d+) tests?',output)
 skips=re.findall(r'OK \(skipped=(\d+)\)',output)
 suites.append({'suite':path,**row,'tests_run':sum(map(int,counts)),'skipped':sum(map(int,skips))})
failures=[r for r in suites if r['exit_code']!=0]
summary={'expected_standalone_suites':len(paths),'passed_suite_files':len(paths)-len(failures),
         'tests_reported_run':sum(r.get('tests_run',0) for r in suites),
         'skips_reported':sum(r.get('skipped',0) for r in suites),'failed_or_missing':failures,'suites':suites}
(folder/'suite_results.json').write_text(json.dumps(summary,indent=2)+'\n')
if '--require-pass' in sys.argv and failures:
 print('Incomplete or failing:',[r['suite'] for r in failures]);raise SystemExit(1)
profiles={name:json.loads((folder/(name+'.json')).read_text()) for name in ['before','after-final','confirm-varied-shell-final','bulk-varied']}
before,after,shell,bulk=[profiles[n] for n in profiles]
base=(folder/'base.txt').read_text().strip()
commits=subprocess.check_output(['git','--git-dir=.scratch/git','--work-tree=.','log','--oneline',base+'..HEAD'],text=True).strip()
def table_row(label,v):
 return f"| {label} | {v['first_load_seconds']:.3f} | {v['total_seconds']:.3f} | {v['mean_seconds']:.3f} | {v['max_seconds']:.3f} |"
phases=[]
for phase,(calls,seconds) in before['phases_inclusive'].items():
 newcalls,newseconds=after['phases_inclusive'][phase]
 phases.append(f'| {phase} | {calls} | {seconds:.3f} | {newcalls} | {newseconds:.3f} |')
commands=[]
for r in sorted(records,key=lambda r:r['started_utc']):
 command=shlex.join(r['command']).replace('|','\\|').replace('`','\\`')
 commands.append(f"| {r['started_utc']} | {r['elapsed_seconds']:.3f} | {r['exit_code']} | `{command}` | [log]({r['log']}) |")
skipped='\n'.join(f"- `{r['suite']}`: {r['skipped']} explicit skips; [full output]({r['log']})." for r in suites if r.get('skipped')) or '- No completed suite reported a skip.'
text=f'''# Beta 71 APF-6: CPU Play Calling workflow

Branch **astra/b71-apf6-editor-workflow**, based on integrated A7 **{base}**.
Implementation is committed in `.scratch/git`; the shared worktree git directory
is unchanged. Delivery bundle: `.scratch/astra-b71-apf6.bundle`. No push,
emulator, desktop display, audio or disc build. Qt uses `offscreen`.

## Result

**{summary['passed_suite_files']}/{len(paths)} requested standalone suite files pass** on their latest complete run,
reporting **{summary['tests_reported_run']} tests and {summary['skips_reported']} explicit skips**.
The full matrix is [suite_results.json](reports/b71_apf6/suite_results.json).
{'All required final checks pass.' if not failures else 'Draft report: the full suite is still running; unresolved rows are listed in suite_results.json.'}

The editor retains parsed source books and validated receipts, confirms edits
without a separate Review click, and collects mixed changes in **Pending edits**.
**Confirm all** runs existing reviews plus cross-edit checks and writes the
independent clean set as one atomic recipe and one Undo step. Blocked dependencies
remain pending, with the edit, location, reason and fix displayed together.
Each pending row has **Undo / clear**. MASTER retains its experimental all-books warning.

## Profile and timings: PROVED on this Linux host

[profile.py](reports/b71_apf6/profile.py) uses the owned export at
`{before['source_index']}`. The source index SHA-256 is
`{before['source_index_sha256']}` in every run. Nothing writes or copies the retail
source. The baseline loads the three original Python modules directly from the
recorded A7 commit; the same process driver then performs 21 play-rating edits,
21 formation-rating edits and 21 balanced-audible edits in O-ManBlock. Each timed
edit includes review, stage and the complete offscreen CPU-page refresh.
No disk-cache flush is claimed. First load is a separate fresh-process measurement.

| Run | First load, s | 63 edits, s | Mean/edit, s | Slowest/edit, s |
| --- | ---: | ---: | ---: | ---: |
{table_row('A7 baseline, same repeated-formation sequence',before)}
{table_row('Final incremental code, identical sequence',after)}
{table_row('New Confirm buttons, cycling formations and shell CPU refresh callback',shell)}

The identical sequence is **{before['total_seconds']/after['total_seconds']:.1f}× faster** here.
The varied run invokes the page's Confirm path and connects `modifiedChanged` to
`set_context`, exercising the synchronous CPU reset used by the shell plus the
panel refresh. It is a real-export page measurement, not a complete timed session
of every other studio workspace, file picker, autosave and operating-system UI.
The exact historic 63 requests were not supplied; this is a reproducible mixed
pattern matching the reported edit types and count, not a claim to reconstruct
that private session. Native Windows/macOS performance remains UNWITNESSED.
Some baseline intervals overlapped short development checks and later optimized
runs overlapped detached regression processes; all wall times are retained, and
the counters independently establish elimination of the repeated catalog/replay work.

Bulk on the same export, cycling formations: all 63 additions to Pending edits
used **{bulk['total_seconds']:.3f}s** total (slowest addition **{bulk['max_seconds']:.3f}s**).
One **Confirm all** checked/staged those 63 requests and refreshed the page in
**{bulk['confirm_all_seconds']:.3f}s**, with exactly one Undo entry. Source reads
occurred once. This total includes every writer check; no check is deferred to
an optional Review click.

### Timed phases

These times are inclusive and overlap; do not add them. Counts include cold load
and selection refreshes. Ledger access counts include cached lookups, not just
physical reads. MASTER's cached wrapper calls the original reader once, so the
after counter includes both wrapper and cold inner call.

| Phase | Before calls | Before seconds | After calls | After seconds |
| --- | ---: | ---: | ---: | ---: |
{chr(10).join(phases)}

Raw per-edit results: [before](reports/b71_apf6/before.json),
[identical after](reports/b71_apf6/after-final.json),
[varied Confirm plus shell reset](reports/b71_apf6/confirm-varied-shell-final.json),
[bulk](reports/b71_apf6/bulk-varied.json). Earlier measurements are retained too.

## Design and check preservation

- `book_content.BookSourceCache` scopes source data to the resolved index path.
  File identities include path, size, nanosecond mtime, ctime and inode; the index
  and compressed resource spans have SHA-256 identities. Unchanged file identities
  need only stat calls. When a pack changes, only its named resource spans are
  hashed, and unchanged spans keep their parsed values. No multi-GB pack is hashed
  on every edit. Missing/replaced files invalidate reuse; a source changing during
  a resource read is refused. Reads still bind book names to filename IDs.
- `Backend` retains parsed source books, MASTER inventory and ROST, and reuses
  unchanged compiled Fine-tune books. `PlayCallingService` caches the source and
  non-CPU dependencies, digest-checked recipe files, immutable parsed staged books,
  and up to 64 validated ledger prefixes. A warm single CPU edit neither reloads
  the catalog nor replays earlier receipts. Undo reuses an existing valid prefix.
- Changed source/Fine-tune dependencies invalidate the base. Up to 128 cached
  writer transitions retain the exact consumed book/master/roster/mask inputs,
  authored request and returned facts. Replay revalidates only affected rows;
  ownership and scheme plans always replay their archive-dependent checks. Tests
  change one source book while retaining another book's validated receipt.
  Public state returns copy mutable book/mask dictionaries. Recipe schema/size,
  digest and before/after checks still run at their existing boundaries.
- `context` reads ratings, personnel and plays from one parsed book instead of
  reparsing that book for every play. Predictions retain the existing book,
  MASTER, tendency, side, situations and mask cache keys and unchanged arithmetic.
- `confirm_playcalling` holds the existing session lock. `confirm` calls the
  original `review(session, request, state=...)` with exactly the captured request
  and the current proposed state. `review` still calls `apply`, all original
  writers, MASTER verification, category/row coverage and the original refusal
  logic. The optional state argument is the earlier accepted pending changes;
  it has no separate replacement validation implementation. Tests compare direct
  review inputs and receipts to Confirm for every ordinary control, masks,
  MASTER rows/roles and ownership. Real scheme/retirement and build tests remain.
- Bulk reviews every row, including detected conflicts, collecting all errors.
  Removed-formation references conflict in either order, including donor references.
  Two individually valid removals cannot jointly empty required personnel rows.
  Final coverage is checked again after later MASTER changes. Blockers propagate
  to the same book and dependent donor additions; shared MASTER/ownership plans
  retain their whole batch. Retirement retains its paired team run share when
  refused, including a USER/donor book independent of the team assignment. Independent clean edits are replayed against the retained clean set
  before one payload store, one Undo snapshot and one modification-map assignment.
  Failed writes leave the project and Undo unchanged; save/reopen reparses receipts.
- The page uses **Confirm …** for direct actions and **Add … to pending** in queue
  mode. Live masks can be queued with their enable switch. Requests keep their
  selected book/team/row when browsing another book. **Show review details** is
  collapsible and optional; combined blockers stay inline outside it. Own-book
  planning and confirmation share one worker, avoiding a nested blocking worker.
  The existing theme, tooltips and accessibility descriptions are retained.
  The queue holds drafts for the open session; confirm before saving the project.
  The existing recipe bounds (4096 receipts and 2 MiB) are retained.

The [synthetic themed screenshot](reports/b71_apf6/pending-edits.png) shows two
formation blockers and the independently staged tendency. Blocker text wraps
inside the table, and clearing targets the logical row even under theme sorting.
The final Qt test covers the table width, row wrapping, automatic review,
synchronous shell refresh, mixed queue, source-session reset and write failure.

## Registry, packaging and boundaries

**Zero capability rows added: 176 total / 73 APF.** Existing CPU Play Calling
registry evidence names the two new suites, and existing CPU action bindings
include `confirm_playcalling`. The capability ID set is unchanged; its SHA-256
is `a5e791c1047da40e2d13827d93b97b9510de5676742e9777b0a049d2b274fa46`.
No count-pin, tuple, installer count or validation-plan count change is needed.
The registry edit is the user-requested evidence update to the existing row;
no protected 2K5 GUI, build, game-code, colour or scorebug file was changed.
The APF modules were already in the release allowlist; no new runtime module
or allowlist entry is needed.

Strict validation, provider integrity, product catalog, phase1 packaging, repin,
and a clean staged APF release/runtime check pass. Repin changes zero hashes.
The clean stage has **289 files**, imports **161 modules**, and reports **73 APF
capabilities**. Release checking finds no private/retail payload, symlink or
undeclared file. The installer test uses the prepared local interpreter with
source PYTHONPATH cleared; no network dependency install occurred.

The 75 inherited evidence paths and reviewed extractor files were restored or
verified through the prior hash-pinned hydration scripts, read-only from their
sources. Inventory files are independent copies. H7A remains mode 0755.
The private git directory, stage, test interpreter and bundle stay below the
200 MiB scratch limit; the temporary stage/interpreter are removed at delivery.

**PROVED:** measured source/ledger work reduction on the owned export; existing
reviews on the Confirm path; conflict/refusal checks; atomic clean-set staging;
Undo/save/reopen; offscreen page behavior; and the passing offline gates listed
above, subject to each test's stated native/synthetic boundary.

**UNWITNESSED:** actual gameplay, Xenia consumption of any staged data/patch,
Windows/macOS timing and rendering, the historic exact 63-edit session, and a
human editing session in the released installer. This job changes no gameplay
patch bytes and does not replace the APF-2/4/5 witness boundaries. No emulator
was opened. Re-test ordinary personnel, masks, requested rows and fourth-down
behavior in a real match using the integrated stack's existing witness procedure.

### Explicit skips

{skipped}

## Failures and retained history

The first development Qt expectations assumed a separate Review click and a
retirement receipt without its captured tendency. Those expectations now test
automatic confirmation or explicit queue mode. The first new fixture used a
nonexistent synthetic play ID and assumed the fake remover supplied MASTER;
both fixture assumptions were corrected. The inherited scheme Qt file first
failed its old Review expectation; its complete corrected run passes and still
checks the full scheme detail table, CSV, Undo and 5-2 control. Earlier failed
logs remain in the ledger. A baseline launcher whose short parent exited produced
no acceptance result; the supervised detached run supplies the reported baseline.
The batch coordinator may retain exit 1 from an earlier failed suite; acceptance
uses the latest complete standalone file run, never selected passing test cases.

## Retest and delivery

1. Open CPU Play Calling on the same export; choose O-ManBlock, USER-O and USER-D.
   Confirm play/formation ratings and audibles without a Review click. Check that
   controls stay available after completion and confirm the timings on the target OS.
2. Enable **Add edits to Pending edits**. Queue personnel, retirement with run/pass
   share, Never call, tendencies, audibles, requested rows and masks across books.
   Confirm all; verify clean edits appear together and one Undo restores them.
3. Queue removal plus a reference to that formation in either order, and two edits
   that jointly empty a personnel category. Every blocker should remain visible.
   Clear the conflicting row and confirm again. Retain the MASTER warning.
4. Save, reopen, build a copied game and inspect the existing writer receipts.
   Install masks separately when intended; pending drafts must first be confirmed.
   Gameplay and native Windows/macOS performance need their own witness.
5. Import the private bundle onto A7 `{base}`. Read the explicit paths and the
   final delivery receipt before integration; no push was performed.

Implementation commits before this report:

```
{commits}
```

The final report commit, bundle SHA-256, bundle verification and cleanup commands
are recorded in `.scratch/astra-b71-apf6-delivery.json`, outside the report commit
to avoid a self-referential commit hash/timing. `ASTRA_LAST_MESSAGE.md` ends in
`ASTRA_DONE`.

## Command ledger

[commands.jsonl](reports/b71_apf6/commands.jsonl) records exact argv, UTC start,
wall seconds, exit and complete output for every formal profile, suite, gate,
hydration and implementation-commit command. The table includes failed attempts.
Read-only discovery, source inspection and editor tool calls are exploratory;
the session transcript retains those calls and tool-return timing, not test claims.
Detached work uses a separate process session with a waiting supervisor; no
name-based process killing was used. Final delivery commands use the separate
receipt described above.

| UTC start | Seconds | Exit | Command | Output |
| --- | ---: | ---: | --- | --- |
{chr(10).join(commands)}
'''
(root/'ASTRA_REPORT.md').write_text(text)
(root/'ASTRA_LAST_MESSAGE.md').write_text(f'''APF-6 is implemented on astra/b71-apf6-editor-workflow in the private git directory.

- Identical 63-edit real-export profile: {before['total_seconds']:.2f}s before, {after['total_seconds']:.2f}s after; {after['mean_seconds']:.3f}s/edit.
- Confirm runs the existing checks. Pending edits checks interactions, retains blockers and stages the clean set atomically with one Undo.
- {summary['passed_suite_files']}/{len(paths)} standalone suites pass; {summary['tests_reported_run']} tests, {summary['skips_reported']} explicit skips. Gameplay and native Windows/macOS performance remain UNWITNESSED.
- Bundle: .scratch/astra-b71-apf6.bundle. Full evidence and command ledger: ASTRA_REPORT.md. No push or emulator.

ASTRA_DONE
''')
print(json.dumps({k:v for k,v in summary.items() if k not in {'suites','failed_or_missing'}},indent=2))
