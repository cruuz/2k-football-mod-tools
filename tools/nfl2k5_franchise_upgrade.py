#!/usr/bin/env python3
"""Upgrade an older SOFTDRINK 2026 franchise, or sync coach art, hair styles or award history from a disc
(played-clubs is the opt-in guess for the first season's TEAM column).

Inputs are read only. Output is a new signed save directory; --dry-run writes
only the requested receipt. The receipt includes input/output SHA-256 hashes
and every changed field. No HDD image is edited by this command.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_franchise_upgrade as upgrade  # noqa: E402
from mod_editor.core.nfl2k5_franchise_upgrade_io import (  # noqa: E402,F401
    COMMANDS, DEFAULT_COHORT, check_paths, hash_file, load_container, load_disc,
    plan_upgrade, write_copy, write_plan,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("--input", required=True, type=Path, help="signed FXG save folder or zip")
    parser.add_argument("--disc", required=True, type=Path, help="current/final disc, read only")
    parser.add_argument("--output", type=Path, help="new signed save folder")
    parser.add_argument("--receipt", required=True, type=Path, help="new JSON receipt including all field changes")
    parser.add_argument("--cohort", default=DEFAULT_COHORT, type=Path)
    parser.add_argument("--team-history", type=Path, help="optional counter-pinned evidence for completed franchise seasons")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        upgrade.require(args.dry_run or args.output is not None, "--output is required unless --dry-run")
        check_paths(args.input, args.disc, args.output, args.receipt)
        plan = plan_upgrade(args.input, args.disc, command=args.command, cohort_path=args.cohort,
                            team_history_path=args.team_history)
        receipt = write_plan(plan, None if args.dry_run else args.output, args.receipt)
        print(json.dumps({k: v for k, v in receipt.items() if k not in ("steps", "write", "validation")}))
        return 0
    except (ValueError, OSError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
