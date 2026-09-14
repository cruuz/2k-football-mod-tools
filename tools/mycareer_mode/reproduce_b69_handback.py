"""Reproduce beta 68's first-play hand-back against the beta 69 native series.

Read the two historical MyCareer modules from git in this isolated process.
No retail bytes, native RAM or executables are written. The expected failure
is evidence of the old behavior, not an in-game witness.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import types


def reproduce(base):
    import mod_editor.core as package
    for short in ('nfl2k5_my_career_mode_code', 'nfl2k5_my_career_mode'):
        name = 'mod_editor.core.' + short
        module = types.ModuleType(name)
        module.__package__ = 'mod_editor.core'
        module.__file__ = str(Path('mod_editor/core') / (short + '.py'))
        source = subprocess.check_output(
            ['git', 'show', f'{base}:mod_editor/core/{short}.py'], text=True)
        sys.modules[name] = module
        setattr(package, short, module)
        exec(compile(source, module.__file__, 'exec'), module.__dict__)
    from tests import nfl2k5_b69_series as series
    from tests.nfl2k5_supersim_draft_fixture import retail_bytes
    old_services, rows = series.menu_services, []

    def services(machine, side):
        old_services(machine, side)

        def trace(_uc, address, _size, _user):
            team = machine.reg('ESI' if address == 0x1891F3 else 'ECX')
            rows.append(dict(
                pc=hex(address), team=hex(team),
                present=hex(machine.get(machine.state + 2568)),
                wait=machine.get(machine.state + 2708),
                phase=machine.get(0xE602B8),
                call_complete=(bool(machine.get(machine.get(team + 12) + 36) & 8)
                               if team in (0xE5FC20, 0xE5FC60) else None)))
        for pc in (0xA1412, 0xA1419, 0x1891F3):
            machine.uc.hook_add(machine.u.UC_HOOK_CODE, trace, begin=pc, end=pc)

    series.menu_services = services
    try:
        series.policy_probe(package.nfl2k5_my_career_mode.apply(retail_bytes())[0],
                            0, 0, drives=3)
    except AssertionError as error:
        if str(error) != 'first-play caller differs from saved policy':
            raise
        if not any(row['pc'] == '0x1891f3' and row['call_complete']
                   and row['present'] != '0x0' for row in rows):
            raise AssertionError('missing returning unit with completed CPU call') from error
        return dict(base=base, expected_failure=str(error), trace=rows)
    raise AssertionError('beta 68 unexpectedly opens returning first-play choice')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='922c009d')
    args = parser.parse_args()
    print(json.dumps(reproduce(args.base), indent=2), flush=True)
