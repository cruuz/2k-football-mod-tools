"""Collect passing standalone receipts for one unchanged beta-69 source set.

No retail assets, executables, native RAM or disc bytes are exported.
"""
from pathlib import Path
import argparse
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]


def collect(groups, negative_control):
    rows, pins, manifest = [], None, None
    native = []
    for group in groups:
        data = json.loads(Path(group).read_text())
        if manifest is not None and data['manifest_sha256'] != manifest:
            raise ValueError('suites use different gate manifests')
        manifest = data['manifest_sha256']
        for row in data['tests']:
            if row['result'] != 'passed' or row['exit_code']:
                raise ValueError(f'non-passing suite: {row["command"]}: {row["result"]}')
            if row['skipped']:
                if (row['command'] != 'python3 tests/mod_editor/test_nfl2k5_my_career_generic_build.py'
                        or row['skipped'] != 1):
                    raise ValueError(f'unreviewed skip: {row["command"]}')
                row = dict(row, skip_reason=(
                    'Existing generic disc-recipe test requires 100 GB root reserve plus '
                    'bounded fixture space; available space is below that guard. No disc was built.'))
            current = row['source_sha256']
            if pins is not None and current != pins:
                raise ValueError('suites use different production sources')
            pins = current
            for name, digest in current.items():
                if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
                    raise ValueError(f'production source changed: {name}')
            log = ROOT / row['log']
            if hashlib.sha256(log.read_bytes()).hexdigest() != row['log_sha256']:
                raise ValueError(f'test log changed: {log}')
            for line in log.read_text().splitlines():
                for marker in ('B69_PLAYCALL_RECEIPT ', 'B68_SUPERSIM_RECEIPT ',
                               'B68_PAT_RECEIPT ', 'NATIVE_SUPERSIM_RECEIPT '):
                    if line.startswith(marker):
                        native.append(dict(kind=marker.strip(), result=json.loads(line[len(marker):])))
            rows.append(row)
    commands = [row['command'] for row in rows]
    if len(set(commands)) != len(commands):
        raise ValueError('duplicate suite receipts')
    gates = ['test_xbe_patch_memory_writes.py', 'test_xbe_patch_cave_references.py',
             'test_nfl2k5_cave_oracle.py', 'test_nfl2k5_owner_pairwise_composition.py']
    if not all(any(command.endswith(gate) for command in commands) for gate in gates):
        raise ValueError('all four XBE gates are required')
    caller = [row['result'] for row in native if row['kind'] == 'B69_PLAYCALL_RECEIPT']
    if {(row['handbacks'][0]['position'], row['postgame_policy']) for row in caller} != {
            (0, 0), (0, 1), (0, 2), (11, 0), (11, 1), (11, 2), (7, 1)}:
        raise ValueError('native caller matrix is incomplete')
    for row in caller:
        expected = 1 if row['handbacks'][0]['position'] == 7 else 2
        if len(row['handbacks']) != expected or any(
                h['pre_snap_state'] != 13 or h['snap_state'] != 14
                or h['next_fast_forward_updates'] != 8
                for h in row['handbacks']):
            raise ValueError('native hand-back/snap/rearm sequence is incomplete')
    negative = json.loads(Path(negative_control).read_text())
    if (negative.get('base') != '922c009d' or negative.get('expected_failure') !=
            'first-play caller differs from saved policy' or not any(
                row['pc'] == '0x1891f3' and row['call_complete']
                and row['present'] != '0x0' for row in negative['trace'])):
        raise ValueError('beta-68 first-play negative control is missing')
    return dict(schema='nfl2k5.mycareer.b69-validation.v1', experimental=True,
                runtime_witnessed=False, source_sha256=pins,
                manifest_sha256=manifest, negative_control=negative,
                suites=rows, total_suites=len(rows), total_tests=sum(r['tests'] for r in rows),
                total_skipped=sum(r['skipped'] for r in rows),
                native=native,
                limits=['Declared scene/device and ready-animation boundaries; no console or framebuffer.',
                        'Human selection enters native menu callback 207440; physical cursor input is unwitnessed.',
                        'Snap, fourth-down, dead-ball and game completion are explicit inputs.',
                        'The optional CB probe exposed a corrected clip-slot fixture input, but did not produce an accepted selected-player return; no CB possession proof.',
                        'Release manifest and protected studio/build/registry wiring await integration.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--negative-control', required=True, type=Path)
    parser.add_argument('groups', nargs='+', type=Path)
    args = parser.parse_args()
    result = collect(args.groups, args.negative_control)
    args.output.write_bytes((json.dumps(result, indent=2, sort_keys=True) + '\n').encode())
    print(f'{result["total_suites"]} suites, {result["total_tests"]} tests, '
          f'{result["total_skipped"]} skipped; all four XBE gates passed.')
