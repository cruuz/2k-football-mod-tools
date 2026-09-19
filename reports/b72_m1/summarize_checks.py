"""Summarize only completed, passing standalone checks; retain the initial failure."""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'reports/b72_m1'
EXTRA = ('test_mycareer_art', 'test_b69_j1_fit', 'test_b69_j1_wiring', 'test_b69_j1_native',
         'test_b69_j1_build', 'test_studio_session', 'test_music_playlist_project',
         'test_audio_annotation_project_archive', 'test_project_document_workflow',
         'test_models_project_wiring', 'test_b71_t5_project_open')
GATES = ('test_xbe_patch_memory_writes', 'test_xbe_patch_cave_references',
         'test_nfl2k5_cave_oracle', 'test_nfl2k5_owner_pairwise_composition')


def parsed(name, log):
    text = (OUT/log).read_text(encoding='utf-8')
    # Buffered stdout receipts may follow unittest's stderr summary.
    match = re.search(r'^Ran (\d+) tests? in ([\d.]+)s\n\nOK(?: \(skipped=(\d+)\))?$',
                      text, re.MULTILINE)
    if not match or re.search(r'^FAILED\b', text, re.MULTILINE):
        raise ValueError(f'{name}: no completed passing unittest result in {log}')
    return dict(test=name, log=log, tests=int(match[1]), seconds=float(match[2]),
                skipped=int(match[3] or 0), status='passed')


def main():
    suites = json.loads((OUT/'suites-results.json').read_text())
    gates = json.loads((OUT/'gates-results.json').read_text())
    expected = {p.stem for p in (ROOT/'tests/mod_editor').glob('test_nfl2k5_my_career*.py')} | set(EXTRA)
    if {r['test'] for r in suites} != expected or {r['test'] for r in gates} != set(GATES):
        raise ValueError('Required standalone checks are still incomplete.')
    rows = []
    for row in suites + gates:
        name = row['test']
        log = name+'.log'
        if row['returncode']:
            if name != 'test_nfl2k5_my_career':
                raise ValueError(f'{name}: failed with return code {row["returncode"]}')
            log = name+'-final.log'
        rows.append(parsed(name, log))
    rows.append(parsed('test_nfl2k5_position_choices', 'test_nfl2k5_position_choices.log'))
    additional = [parsed('final event module', 'events-final.log'),
                  parsed('final advisory module', 'advisory-final.log')]
    result = dict(status='passed', standalone_suites=len(rows), tests=sum(r['tests'] for r in rows),
                  skipped=sum(r['skipped'] for r in rows), gates=list(GATES), results=rows,
                  additional_checks=additional,
                  initial_failure='Creation test assumed QB had only three templates; assertion updated and full suite rerun.',
                  native_outcomes_witnessed=False)
    (OUT/'aggregate.json').write_bytes((json.dumps(result, indent=2)+'\n').encode('utf-8'))
    print(json.dumps({key: result[key] for key in ('status', 'standalone_suites', 'tests', 'skipped')}, indent=2))


if __name__ == '__main__':
    main()
