"""Inspect or install beta-69 rules into a new XBE file; never overwrites input.

EXPERIMENTAL / UNWITNESSED. With every option Off, copy bytes unchanged.
Existing installs may be replayed; changing the selected union needs a clean base.
"""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_coin_defer as coin
from mod_editor.core import nfl2k5_decided_clock as clock
from mod_editor.core import nfl2k5_cpu_scrambles as scrambles
from mod_editor.core import nfl2k5_xbe_space as space


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('status', 'apply'))
    parser.add_argument('xbe', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--cpu-defer', action='store_true')
    parser.add_argument('--decided-clock', action='store_true')
    parser.add_argument('--modern-scrambles', action='store_true')
    parser.add_argument('--margin', type=int, choices=clock.MARGINS, default=17)
    parser.add_argument('--seconds', type=int, choices=clock.SECONDS, default=60)
    args = parser.parse_args(argv)
    if (args.action == 'apply') != (args.output is not None):
        parser.error('apply requires --output; status accepts no output')
    if args.action == 'status' and (args.cpu_defer or args.decided_clock or args.modern_scrambles):
        parser.error('status accepts no feature switches')
    try:
        with args.xbe.open('rb') as stream:
            payload = stream.read(space.SCALE_FILE_SIZE+1)
        if len(payload) > space.SCALE_FILE_SIZE:
            raise ValueError('Expected bounded default.xbe bytes')
        if args.action == 'apply':
            owners = [(module, options) for enabled, module, options in (
                (args.cpu_defer, coin, {}),
                (args.decided_clock, clock, dict(margin=args.margin, seconds=args.seconds)),
                (args.modern_scrambles, scrambles, {})) if enabled]
            if owners and space.status(payload) == 'retail':
                payload = space.apply(payload, sum((m.REQUESTS for m, _ in owners), ()), scaleout=True)[0]
            for module, options in owners:
                payload = module.apply(payload, **options)[0]
            receipt = {m.OWNER: m.verify(payload) for m in (coin, clock, scrambles)}
            created = False
            try:
                with args.output.open('xb') as stream:
                    created = True
                    stream.write(payload)
            except BaseException:
                if created:
                    args.output.unlink(missing_ok=True)
                raise
        else:
            receipt = {m.OWNER: m.verify(payload) for m in (coin, clock, scrambles)}
        print(json.dumps(receipt, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print(f'Modern rules refused: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
