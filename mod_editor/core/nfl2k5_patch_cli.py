"""Copy-only CLI for reviewed owners whose public API has no command parser."""
from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path

OWNERS = ("abilities_runtime", "practice_squad_screen", "xbe_space", "dynamic_kickoff_relocated", "zone_drop", "roster_storage", "player_star", "camera")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("owner", choices=OWNERS)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.source.stat().st_size > 32 * 1024 * 1024:
            raise ValueError("Expected a bounded XBE, not a disc image")
        module = importlib.import_module("mod_editor.core.nfl2k5_" + args.owner)
        payload, receipt = module.apply(args.source.read_bytes())
        with args.output.open("xb") as stream:
            stream.write(payload)
        print(json.dumps(receipt, sort_keys=True))
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Patch refused: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
