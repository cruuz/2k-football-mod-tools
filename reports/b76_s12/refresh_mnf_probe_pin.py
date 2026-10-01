"""Re-pin the older 'mnf' probe's appended-bytes identity after a logo recolour (b76-s12, b76-s14).

The 'mnf' runtime probe (not the shipped sprite route) appends one 64x64 logo panel
per team, built from data/nfl2k5_scorebug_mnf/logos/*.png, plus its fonts and atlas.
PROBE_APPEND_PINS['mnf'] in mod_editor/core/nfl2k5_scorebug_resources.py pins the
digest of those bytes, so recolouring nyg.png and lar.png moves it by design.

This script recomputes every compiler pin with tools/nfl2k5_scorebug_exact.py's own
compiler_pins() from the pinned retail inputs, REFUSES if any pin other than
PROBE_APPEND_PINS['mnf'] would change, and rewrites only that one value. It never
relaxes or removes a pin. Re-run it on a merged tree after any change to the logo
PNGs; then run ``python3 packaging/repin.py --apply``.

Usage:  python3 reports/b76_s12/refresh_mnf_probe_pin.py [--check]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_scorebug_resources as art  # noqa: E402
from nfl2k5_scorebug_exact import Build, compiler_pins  # noqa: E402

MODULE = ROOT / 'mod_editor/core/nfl2k5_scorebug_resources.py'
PACK = ROOT / 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
XBE = PACK.parents[1] / 'default.xbe'


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--check', action='store_true', help='Report only; write nothing')
    p.add_argument('--receipt', type=Path, default=Path(__file__).resolve().parent / 'mnf-probe-pin.json')
    a = p.parse_args(argv)
    if not PACK.is_file() or not XBE.is_file():
        raise SystemExit('The pinned retail pack 0 and default.xbe are required (extracted/ESPN NFL 2K5 (USA)/)')
    build = Build(PACK, XBE)
    try:
        pins = compiler_pins(build)
    finally:
        build.close()
    moved = {}
    for name, value in pins.items():
        current = getattr(art, name)
        if name == 'PROBE_APPEND_PINS':
            for probe, digest in value.items():
                if current.get(probe) != digest:
                    moved['PROBE_APPEND_PINS.' + probe] = (current.get(probe), digest)
        elif current != value:
            moved[name] = (current, value)
    unexpected = sorted(k for k in moved if k != 'PROBE_APPEND_PINS.mnf')
    receipt = dict(module=str(MODULE.relative_to(ROOT)), moved={k: dict(before=v[0], after=v[1]) for k, v in moved.items()},
                   unexpected=unexpected, cause='team marks in data/nfl2k5_scorebug_mnf/logos recoloured (b76-s12: nyg, lar; b76-s14: nyj, dal, ind, no, jax)')
    if unexpected:
        print(json.dumps(receipt, indent=2))
        raise SystemExit('Refusing: pins other than PROBE_APPEND_PINS[mnf] would move: ' + ', '.join(unexpected))
    if a.check or 'PROBE_APPEND_PINS.mnf' not in moved:
        print(json.dumps(receipt, indent=2))
        return 0 if 'PROBE_APPEND_PINS.mnf' not in moved else 1
    text = MODULE.read_text(encoding='utf-8')
    new_pins = dict(art.PROBE_APPEND_PINS, mnf=moved['PROBE_APPEND_PINS.mnf'][1])
    text, count = re.subn(r'(?m)^PROBE_APPEND_PINS = .*$', lambda _m: 'PROBE_APPEND_PINS = ' + repr(new_pins), text)
    if count != 1:
        raise SystemExit('Expected exactly one PROBE_APPEND_PINS line')
    MODULE.write_text(text, encoding='utf-8', newline='\n')
    a.receipt.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
