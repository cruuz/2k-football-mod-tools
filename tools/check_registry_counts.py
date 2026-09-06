#!/usr/bin/env python3
"""Every capability count in this repository, derived from the registry and checked.

Thirteen places state how many rows the capability registry has, how many of
them are covered, how many distinct validators they name, or how many belong to
one game.  All four numbers are pure functions of
``mod_editor/capabilities/registry.v1.json``; none of them is an independent
fact.  ``tools/registry_add_rows.py`` moves all thirteen when it adds a row,
which is why a game PR does not hunt for them by hand -- but nothing until now
*checked* them, so a hand edit, a bad merge or a resolved conflict could leave
two of the thirteen disagreeing and only fail later, inside a packaging gate,
as a number with no explanation attached.

This tool derives the counts and says which sites agree::

    python3 tools/check_registry_counts.py            # check; prints one line per site
    python3 tools/check_registry_counts.py --json     # the derived counts, nothing else
    python3 tools/check_registry_counts.py --quiet    # only the verdict and any mismatch

It prints ``REGISTRY_COUNTS_OK`` and exits 0 when every site agrees with the
registry, and names each disagreement with the value the registry implies
otherwise.

**What is derived and what must stay a literal.**  Only three of the thirteen
sites are shipped in a release (``packaging/check_2k5_mod_studio_runtime.py``,
``docs/mod_editor/2k5_mod_studio_getting_started.md``, and the registry itself);
the other ten exist only in the repository.  A literal in a repo-only site
compares the registry against a number derived from the registry, so it can be
computed at check time with nothing lost.  The literal in the **shipped** runtime
gate is different: it compares a staged registry against an expectation written
before staging, and deriving it from the staged registry would make it
``x == x``.  That one is a real guard and this tool does not propose removing
it.  See ``docs/owner/EFFICIENCY_REVIEW.md``.

Standard library only.  A site that is absent -- as most of them are in a staged
tree -- is reported as absent, not as a failure.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = "mod_editor/capabilities/registry.v1.json"
ALLOWLIST = "packaging/release-allowlist.txt"

#: The rule ``tools/validate_all_mod_editor_capabilities.py`` actually uses: a row
#: is *deferred* when it names no validator, whatever its classification says.  A
#: row may be classified ``unknown`` and still have a validator that runs, and one
#: such row is why the counts in that file had drifted from the registry.
#: Classification only decides whether a *missing* validator is allowed.
MAY_LACK_A_VALIDATOR = ("unknown", "unsafe/deferred")

#: The game whose row count several sites quote beside the total.
QUOTED_GAME = "nfl2k5_xbox"


def derive(registry: dict) -> Dict[str, int]:
    rows = registry["capabilities"]
    deferred = [row for row in rows if row.get("validation_command") is None]
    misfiled = [row["id"] for row in deferred
                if row.get("classification") not in MAY_LACK_A_VALIDATOR]
    if misfiled:
        raise ValueError("row(s) with no validator and an active classification: "
                         + ", ".join(misfiled))
    return {
        "capabilities": len(rows),
        "covered": len(rows) - len(deferred),
        "deferred": len(deferred),
        "unique_validators": len({row["validation_command"] for row in rows
                                  if row.get("validation_command")}),
        "games": len(registry.get("games", [])),
        f"{QUOTED_GAME}_capabilities": sum(1 for row in rows if row.get("game") == QUOTED_GAME),
    }


def deferred_ids(registry: dict) -> Tuple[str, ...]:
    """The ids ``EXPECTED_DEFERRED_IDS`` has to equal, in the order it uses."""

    return tuple(row["id"] for row in registry["capabilities"]
                 if row.get("validation_command") is None)


def sites(counts: Dict[str, int], ids: Sequence[str] = ()) -> List[Tuple[str, str, str]]:
    """``(file, what it states, the regular expression that must match)``.

    Each pattern carries enough context to be unique: the row total is 112
    today and ``112`` also appears in this repository as a byte union, a vertex
    count and part of 63,112, so a bare number would match the wrong line.
    """

    rows = counts["capabilities"]
    game = counts[f"{QUOTED_GAME}_capabilities"]
    return [
        ("packaging/check_2k5_mod_studio_runtime.py", "the shipped gate's row count",
         rf"require\(len\(registry\.capabilities\) == {rows},"),
        ("packaging/check_2k5_mod_studio_runtime.py", "the closure marker",
         rf'"registry={rows} sections=12 nfl2k5_capabilities={game} "'),
        ("packaging/check_apf2k8_mod_studio_runtime.py", "the APF gate's row count",
         rf"len\(registry\.capabilities\) == {rows}"),
        ("tests/mod_editor/test_apf_studio_installer.py", "the installer test's copy of it",
         rf'"len\(registry\.capabilities\) == {rows}"'),
        ("tests/mod_editor/test_phase1_packaging.py", "the packaging test's prose count",
         rf'"registry has {rows} cross-title rows"'),
        ("tests/mod_editor/test_phase1_packaging.py", "the packaging test's closure marker",
         rf'"registry={rows} sections=12 nfl2k5_capabilities={game}"'),
        ("tools/validate_all_mod_editor_capabilities.py", "EXPECTED_CAPABILITIES",
         rf"EXPECTED_CAPABILITIES = {rows}\b"),
        ("tools/validate_all_mod_editor_capabilities.py", "EXPECTED_COVERED_CAPABILITIES",
         rf"EXPECTED_COVERED_CAPABILITIES = {counts['covered']}\b"),
        ("tools/validate_all_mod_editor_capabilities.py", "EXPECTED_DEFERRED_CAPABILITIES",
         rf"EXPECTED_DEFERRED_CAPABILITIES = {counts['deferred']}\b"),
        ("tools/validate_all_mod_editor_capabilities.py", "EXPECTED_UNIQUE_VALIDATORS",
         rf"EXPECTED_UNIQUE_VALIDATORS = {counts['unique_validators']}\b"),
        ("tools/validate_all_mod_editor_capabilities.py", "EXPECTED_DEFERRED_IDS",
         r"EXPECTED_DEFERRED_IDS = \(\s*"
         + r"\s*".join(re.escape(f'"{identifier}",') for identifier in ids)
         + r"\s*\)"),
        ("APF2K8-README.md", "the README's row count",
         rf"APF capabilities \({rows} across all three registered game/platform targets\),"),
        ("docs/mod_editor/APF2K8_STATUS.md", "the APF status count",
         rf"contains {rows} records globally and 37 APF"),
        ("docs/mod_editor/2k5_mod_studio_getting_started.md", "the shipped getting-started count",
         rf"The current registry has {rows} cross-title rows, including {game} Xbox NFL 2K5"),
        ("STATUS.md", "the status table",
         rf"\| Capability registry \| {rows} rows total; {game} Xbox NFL 2K5 rows; "),
    ]


def allowlist_coverage(root: Path) -> Optional[Dict[str, int]]:
    """How much of the release allowlist is already a union of module fragments.

    Evidence for the proposal that the canonical list be *composed* from the
    fragments rather than copied into by hand: the fragments already exist and
    are already regenerated from the canonical file, so the only thing in the
    way of inverting that is which file is authoritative.
    """

    canonical = root / ALLOWLIST
    if not canonical.is_file():
        return None
    lines = [line.strip() for line in canonical.read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.strip().startswith("#")]
    covered: set = set()
    fragments = 0
    for fragment in sorted((root / "mod_editor" / "games").glob("*/allowlist.fragment.txt")):
        fragments += 1
        covered.update(line.strip() for line in fragment.read_text(encoding="utf-8").splitlines()
                       if line.strip() and not line.strip().startswith("#"))
    return {"lines": len(lines), "fragments": fragments,
            "covered_by_a_fragment": len(covered & set(lines)),
            "outside_every_fragment": len(set(lines) - covered)}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="check_registry_counts.py",
                                     description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--json", action="store_true", help="print the derived counts and exit")
    parser.add_argument("--quiet", action="store_true", help="only the verdict and any mismatch")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    registry_path = root / REGISTRY
    if not registry_path.is_file():
        print(f"no capability registry at {REGISTRY} under {root}", file=sys.stderr)
        return 1
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    try:
        counts = derive(registry)
    except ValueError as exc:
        print(f"the registry is not self-consistent: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(counts, indent=2, sort_keys=True))
        return 0

    if not args.quiet:
        print("derived from " + REGISTRY + ": "
              + "  ".join(f"{key}={value}" for key, value in sorted(counts.items())))

    absent = wrong = agree = 0
    for relative, what, pattern in sites(counts, deferred_ids(registry)):
        path = root / relative
        if not path.is_file():
            absent += 1
            if not args.quiet:
                print(f"  --    {relative}: {what} (not in this tree)")
            continue
        if re.search(pattern, path.read_text(encoding="utf-8")):
            agree += 1
            if not args.quiet:
                print(f"  ok    {relative}: {what}")
        else:
            wrong += 1
            print(f"  DRIFT {relative}: {what} does not match the registry; "
                  f"the registry implies {counts['capabilities']} rows, "
                  f"{counts['covered']} covered, {counts['unique_validators']} validators, "
                  f"{counts[f'{QUOTED_GAME}_capabilities']} {QUOTED_GAME} rows. "
                  f"tools/registry_add_rows.py moves these pins when it adds a row; "
                  f"a site that has drifted anyway is repaired by making it agree "
                  f"with the registry, never the other way round.")

    coverage = allowlist_coverage(root)
    if coverage and not args.quiet:
        print(f"  --    {ALLOWLIST}: {coverage['lines']} lines, "
              f"{coverage['covered_by_a_fragment']} of them also in one of "
              f"{coverage['fragments']} module fragments, "
              f"{coverage['outside_every_fragment']} outside every fragment")

    if wrong:
        print(f"REGISTRY_COUNTS_DRIFT sites={agree + wrong + absent} wrong={wrong}")
        return 1
    print(f"REGISTRY_COUNTS_OK sites={agree + wrong + absent} agree={agree} absent={absent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
