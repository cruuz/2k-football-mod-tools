"""Consolidate the completed sweep and explicit retries without hiding failures."""
import json
from pathlib import Path
import re

from b72_sweep import ROOT, SKIP


def main():
    report = ROOT / 'reports/b72_t1'
    initial = json.loads((report / 'sweep/results.json').read_text())['results']
    rows = {row['file']: dict(row, log='sweep/' + Path(row['file']).stem + '.log') for row in initial}
    for filename in ('sweep_retry_results.json', 'sweep_standalone_results.json', 'sweep_extra_results.json'):
        path = report / filename
        if not path.exists():
            continue
        for row in json.loads(path.read_text()):
            previous = rows[row['file']]
            log = 'sweep/' + Path(row['file']).stem
            log += '.standalone.log' if row.get('runner') == 'unittest main wrapper' else '.log'
            rows[row['file']] = dict(row, log=log, initial_status=previous.get('initial_status', previous['status']))
    expected = {p.name for p in (ROOT / 'tests/mod_editor').glob('test_*.py') if p.stem not in SKIP}
    assert rows.keys() == expected, 'A required test file has no final result'
    totals = {}
    for row in rows.values():
        log = (report / row['log']).read_text(errors='replace')
        summary = next((line for line in reversed(log.splitlines()) if re.search(r'\d+ (passed|failed|skipped|error)', line)), '')
        row['summary'] = summary
        for count, label in re.findall(r'(\d+) (subtests passed|passed|failed|skipped|errors?|xfailed|xpassed)', summary):
            totals[label] = totals.get(label, 0) + int(count)
        if row.get('runner') == 'unittest main wrapper':
            match = re.search(r'Ran (\d+) tests?', log)
            assert match and '\nOK' in log, 'Standalone wrapper did not complete successfully'
            totals['standalone tests'] = totals.get('standalone tests', 0) + int(match[1])
    result = dict(excluded=sorted(SKIP), totals=totals, results=sorted(rows.values(), key=lambda row: row['file']))
    (report / 'sweep_final.json').write_text(json.dumps(result, indent=2) + '\n')
    failed = [row['file'] for row in rows.values() if row['status'] != 'OK']
    print(json.dumps(dict(files=len(rows), failed=failed, totals=totals), indent=2))
    return int(bool(failed))


if __name__ == '__main__':
    raise SystemExit(main())
