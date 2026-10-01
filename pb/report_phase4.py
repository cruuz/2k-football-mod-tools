#!/usr/bin/env python3
"""PROVED OFFLINE: render the phase 4 handoff from completed build evidence."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'pb/receipts/phase4'


def read(path):return json.loads(path.read_text())


def main():
    build=read(OUT/'full-build.json');summary=read(OUT/'full-summary.json')
    assert not (Path(build['session'])/'final.xiso.iso').exists(), 'Delete the disc after status checks first'
    assert not summary['skipped_pending']
    contracts=read(OUT/'contracts.json')
    composition=read(ROOT/'pb/receipts/defense/composition.json')
    lines=[
        '# PROVED OFFLINE: phase 4, team books in the full final-draft build', '',
        f"PROVED OFFLINE: The full Ultimate build completed in {build['seconds']} seconds after preflight, "
        'using this worktree and the real final-draft recipe with only `playbook_packs`, `playbook_pair` and '
        '`read_option_runtime` changed. QB Spy and screen timing retain production values (`true` and `D`). '
        'The display-list fix remains enabled. No pending option was dropped. '
        '[Build log](receipts/phase4/full-build.log), [merged recipe](receipts/phase4/full-recipe.json), '
        '[full owner inspection](receipts/phase4/full-build.json), [builder summary](receipts/phase4/full-summary.json).', '',
        f"PROVED OFFLINE: All {contracts['compiler_receipts']} compiler receipts carry versioned Spy records. "
        'The complete-offense compiler emits empty Spy and option records plus its resolved play indices. '
        'The final-intent resolver accepts that explicit empty contract and rejects any nonempty intent claimed '
        'by a complete-offense report. The normal defense compiler retains responsibility for real Spy validation. '
        '[Contract receipt](receipts/phase4/contracts.json).', '',
        'DESIGN: KC gets one situational call, `PB Two Spy 21`, through the existing Spy authoring API, native MLB '
        'slot 5 and a four-yard centered fallback. The enabled runtime supplies QB tracking. '
        '[Cited tendency and limitations](research/SPY.md). The other 31 defenses and all 32 offenses have empty '
        'Spy records. One menu call is a design choice, not an invented season rate or a quarterback-aware CPU policy. '
        'The final runtime table uses one of 31 available records, recompiled against the installed PLAY after '
        'personnel-pool and depth-role changes.', '',
        f"PROVED OFFLINE: All {contracts['screens']} authored RB screens declare D's 0.8-second finite hold, "
        'seven-yard QB drop and 0.6-second explicit pass delay. Their menu names include `RB Screen`, making them '
        'visible to the screen owner. The owner recognizes their exact whole-screen signatures alongside its '
        'retail pins; it does not accept arbitrary custom screens, missing screens or different-level assignments. '
        'The screens are already at D when compiled, so this consumes no extra timing-pass nodes. Retail utility '
        'books still receive their normal D pass. A/B/C requests on these pre-timed authored books refuse.', '',
        'PROVED OFFLINE: The new tests exercise all 64 receipts, stale/missing/forged intent, final Spy re-resolution '
        'after both personnel writers, every screen timing value, different-level and changed-byte refusal, and '
        'the transactional 37-book archive including retail utilities. [Composition tests](receipts/phase4/composition-tests.txt), '
        '[owner regression](receipts/phase4/owner-regression.txt), [native Spy regression](receipts/phase4/spy-native-regression.txt). '
        'The native regression skips two generic opt-in disc tests; this job separately runs the requested full production build.', '',
        'PROVED OFFLINE: Current native menu, assignment, selector and preservation evidence is in '
        '[the defense appendix](DEFENSE_APPENDIX.md), [composition](receipts/defense/composition.json), '
        '[offense menu replay](receipts/league-offline.json) and [preservation](receipts/defense/preservation.json). '
        'The phase 3 source fingerprints were regenerated for the changed offenses. '
        '[Phase 3 historical report](PB_REPORT_PHASE3.md) retains its earlier scope; its disabled-owner guidance '
        'is superseded by this report.', '',
        'PROVED OFFLINE: The initial book regression retained obsolete assertions for zero screen delay and the '
        'isolated 32-pack recipe. Updated tests require D delay, the 64-pack fragment and enabled production owners. '
        '[Updated expectations](receipts/phase4/updated-league-expectations.txt), '
        '[book regression log](receipts/phase4/book-regression-initial.txt), '
        '[final league regression](receipts/phase4/league-tests-final.txt), '
        '[defense tests](receipts/phase4/defense-tests.txt).', '',
        'DESIGN: Reproduce with `python3 pb/build_giants.py --image <retail>`, '
        '`python3 pb/build_league.py --image <retail>`, `python3 pb/defense/build.py`, '
        '`python3 pb/phase4.py --write-pins`, then `bash pb/recipes/full_build.sh`. '
        'The last command starts from a fresh copy of the real final draft, uses `nice -n 15 taskset -c 0-23`, '
        'writes only under the designated Storage directory, records statuses and deletes the disposable ISO on exit. '
        'The older lab recipes were also rebuilt from real production files. Check-only is not composition proof.', '',
        f"PROVED OFFLINE: Build evidence directory: `{build['session']}`. Output size before deletion: "
        f"{build['disc_bytes']:,} bytes. NVMe free at status checks: {build['nvme_free_bytes']/1024**3:.2f} GiB. "
        'The disc was deleted after status checks; the log and build JSON remain. '
        '[Exact source and pack hashes](receipts/phase4/build-inputs.json) identify the changed files used on top '
        'of phase 3 commit `6f7815db5`. The source recipe and other worktrees were not modified. No xemu was run.', '',
        'PROVED OFFLINE: Build composition, owner byte status and offline menu execution are proved for these inputs. '
        'DESIGN: Live Spy pursuit, screen timing benefit, CPU opponent-aware selection and game stability still require '
        'main\'s lab. This build uses the final draft\'s roster input exactly; it does not substitute the separate '
        '2026-team project builder.', '',
        'PROVED OFFLINE: Per-team compiler results follow. Node/name use is after both packs, before unrelated '
        'production writers. Every screen is certified at D; empty Spy records are explicit.', '',
        '| Team | PROVED OFFLINE D screens | PROVED OFFLINE Spy records | PROVED OFFLINE nodes / name bytes |',
        '| --- | ---: | ---: | ---: |',
    ]
    for team,row in contracts['teams'].items():
        c=composition['teams'][team]
        lines.append(f"| {team} | {row['screens']} | {len(row['spy_records'])} | {c['nodes']} / {c['name_bytes']} |")
    lines += ['', 'PROVED OFFLINE: Current test results:', '',
              '| Suite | PROVED OFFLINE result |', '| --- | --- |']
    for name in ('composition-tests.txt','owner-regression.txt','spy-native-regression.txt',
                 'league-tests-final.txt','defense-tests.txt'):
        tail=(OUT/name).read_text().splitlines()[-10:]
        result=next(line for line in reversed(tail) if 'passed' in line)
        assert 'failed' not in result, (name,result)
        lines.append(f'| [{name}](receipts/phase4/{name}) | {result} |')
    lines += ['', 'PROVED OFFLINE: Every top-level final inspection row follows, including disabled owners and '
              'metadata. Nested details remain in the linked full inspection JSON. Builder classification: '
              f"{len(summary['applied'])} applied, {len(summary['expected_foreign'])} expected foreign, "
              f"{len(summary['not_applied'])} not applied and {len(summary['not_inspected'])} without a separate inspection row.", '',
              '| Owner / inspection key | PROVED OFFLINE final value |', '| --- | --- |']
    for key,value in sorted(build['owners'].items()):
        if isinstance(value,dict):
            value=value.get('status','details in full-build.json; no standalone status')
        elif isinstance(value,(list,tuple)):
            value=f'{len(value)} detail rows in full-build.json'
        value=str(value).replace('|','\\|').replace('\n',' ')
        lines.append(f'| `{key}` | {value} |')
    lines += ['', 'PROVED OFFLINE: The builder\'s explicit non-applied, expected-foreign and uninspected classifications:', '', '```json',
              json.dumps({k:summary[k] for k in ('not_applied','expected_foreign','not_inspected','skipped_pending')},indent=2), '```', '',
              'PROVED OFFLINE: Last 25 build-log lines, preserved verbatim:', '', '```text', *build['log_tail'], '```', '',
              'PROVED OFFLINE: Shared Git metadata is read-only. Delivery uses a pathspec commit in private '
              '`.scratch/pb.git` and `.scratch/pb-phase4.bundle`, based on `6f7815db5`, with the required '
              'Astra co-author. No push or tags. Exact commit and bundle hash are in '
              '`.scratch/pb-phase4-delivery.json`.', '']
    (ROOT/'pb/PB_REPORT.md').write_text('\n'.join(lines))


if __name__=='__main__':main()
