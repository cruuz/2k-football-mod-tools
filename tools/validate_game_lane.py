#!/usr/bin/env python3
"""One validator for every game-module lane, driven by the module's own manifest.

Each lane of a game module ships a validator whose registry row names it.  Ten
of them existed for Madden NFL 09 alone, and nine of the ten differed from each
other in exactly two ways: which source files they compiled, and which sentence
they echoed at the end.  Everything else -- find the repository root, force an
offscreen Qt platform, run ``mod_editor.games conformance`` for the game, print
a ``*_VALIDATION_PASS`` token -- was copied.  Copied text drifts: one of the ten
ran the ISO9660 self-tests twice, and four validators of a third game ran
``python3 -m unittest``, which cannot work in a shipped tree because ``tests/``
is not shipped -- those four now delegate here too, with their proofs moved
into the tools' own ``--selftest`` paths.

So the behaviour lives here once, and what differs per lane lives in the game
package where it belongs::

    mod_editor/games/<game_id>/validators.json

    {
      "schema": "vc_game_lane_validators/v1",
      "game_id": "madden09_ps2",
      "lanes": {
        "text": {
          "what": "the text lane",
          "compile": ["mod_editor/games/madden09_ps2/text_lane.py"],
          "selftest": [],
          "conformance": true
        }
      }
    }

A lane's ``compile`` list is byte-compiled (to a scratch directory, so a shipped
tree gains no ``__pycache__``), each ``selftest`` entry is run as its own
process, and ``conformance`` runs the game-module harness.  The pass token is
**derived**, never written down: ``<GAME_ID>_<LANE>_VALIDATION_PASS`` upper-cased.
All twenty-six validators in this repository already spell their token that way,
so nothing had to be renamed to adopt this.

Usage::

    python3 tools/validate_game_lane.py --game madden09_ps2 --lane text
    python3 tools/validate_game_lane.py --game madden09_ps2 --all
    python3 tools/validate_game_lane.py --game madden09_ps2 --list

``--all`` runs every lane's own steps and the conformance harness **once**
rather than once per lane, which is the whole cost of the loop: conformance is
about four seconds and the ten Madden 09 validators spent forty of their
forty-eight seconds re-running it.

Output is one line per step.  A step's own output is shown only when it fails,
or under ``--verbose``: the conformance harness prints 544 PASS lines and 56 KB
for Madden 09, and a gate that has to be read is a gate nobody reads.

Standard library only.  No test framework is imported: this must run in a
shipped tree, where ``tests/`` does not exist.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import py_compile
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Sequence

SCHEMA = "vc_game_lane_validators/v1"
ROOT = Path(__file__).resolve().parents[1]
MANIFEST_NAME = "validators.json"
#: How much of a failed step's output is worth printing before it is noise.
FAILURE_TAIL_LINES = 40


class ValidatorError(Exception):
    """A refusal, one sentence, naming the fix."""


def pass_token(game_id: str, lane: str) -> str:
    """``madden09_ps2`` + ``text`` -> ``MADDEN09_PS2_TEXT_VALIDATION_PASS``."""

    return f"{game_id}_{lane}_VALIDATION_PASS".upper()


def manifest_path(game_id: str, root: Path = ROOT) -> Path:
    return root / "mod_editor" / "games" / game_id / MANIFEST_NAME


def load_manifest(game_id: str, root: Path = ROOT) -> Dict[str, Any]:
    path = manifest_path(game_id, root)
    if not path.is_file():
        raise ValidatorError(
            f"{game_id} has no lane-validator manifest: write "
            f"{path.relative_to(root)} in the shape docs/product/GAME_MODULE_CONTRACT.md "
            f"describes, or run this against a game that has one."
        )
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValidatorError(f"{path.relative_to(root)} is not readable JSON: {exc}") from exc
    if document.get("schema") != SCHEMA:
        raise ValidatorError(
            f"{path.relative_to(root)} declares schema {document.get('schema')!r}; "
            f"this tool reads {SCHEMA!r}."
        )
    if document.get("game_id") != game_id:
        raise ValidatorError(
            f"{path.relative_to(root)} says game_id {document.get('game_id')!r} "
            f"but sits in the {game_id} package; one of the two is wrong."
        )
    lanes = document.get("lanes")
    if not isinstance(lanes, dict) or not lanes:
        raise ValidatorError(f"{path.relative_to(root)} declares no lanes.")
    return document


def _run(argv: Sequence[str], root: Path, label: str, verbose: bool) -> None:
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    # A step that imports a sibling writes a __pycache__ beside it, and a
    # staged tree that gains files fails the release check.  The compile step
    # already redirects its own .pyc; this covers every step's imports too.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = os.pathsep.join(
        [str(root)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    result = subprocess.run(list(argv), cwd=str(root), env=env,
                            capture_output=not verbose, text=True, check=False)
    if result.returncode == 0:
        print(f"  ok    {label}")
        return
    if not verbose:
        output = ((result.stdout or "") + (result.stderr or "")).splitlines()
        for line in output[-FAILURE_TAIL_LINES:]:
            print(f"        | {line}")
    raise ValidatorError(f"{label} failed (exit {result.returncode}).")


def compile_sources(paths: Sequence[str], root: Path) -> None:
    """Byte-compile without leaving a ``__pycache__`` in the tree under test."""

    with tempfile.TemporaryDirectory(prefix="validate-game-lane-") as scratch:
        for index, relative in enumerate(paths):
            source = root / relative
            if not source.is_file():
                raise ValidatorError(
                    f"{relative} is named by the manifest and is not in this tree; "
                    f"either ship it or drop it from the lane's compile list."
                )
            try:
                py_compile.compile(str(source), cfile=str(Path(scratch) / f"{index}.pyc"),
                                   doraise=True)
            except py_compile.PyCompileError as exc:
                raise ValidatorError(f"{relative} does not compile: {exc}") from exc
    print(f"  ok    compiled {len(paths)} source file(s)")


def selftest_argv(entry: Any, root: Path) -> List[str]:
    if not isinstance(entry, dict):
        raise ValidatorError("a selftest entry must be an object with 'script' or 'module'.")
    args = [str(item) for item in entry.get("args", [])]
    if "script" in entry:
        script = root / str(entry["script"])
        if not script.is_file():
            raise ValidatorError(f"{entry['script']} is named as a selftest and is not in this tree.")
        return [sys.executable, str(script)] + args
    if "module" in entry:
        return [sys.executable, "-m", str(entry["module"])] + args
    raise ValidatorError("a selftest entry needs either 'script' or 'module'.")


def run_conformance(game_id: str, root: Path, verbose: bool) -> None:
    _run([sys.executable, "-m", "mod_editor.games", "conformance", "--game", game_id],
         root, f"conformance --game {game_id}", verbose)


def run_lane(game_id: str, lane: str, document: Dict[str, Any], root: Path,
             verbose: bool, conformance: bool,
             already_run: Optional[set] = None) -> str:
    spec = document["lanes"].get(lane)
    if spec is None:
        raise ValidatorError(
            f"{game_id} has no lane validator called {lane!r}; it has: "
            f"{', '.join(sorted(document['lanes']))}."
        )
    print(f"{game_id} / {lane} -- {spec.get('what', lane)}")
    compile_sources([str(item) for item in spec.get("compile", [])], root)
    for entry in spec.get("selftest", []):
        argv = selftest_argv(entry, root)
        name = entry.get("script") or entry.get("module")
        # Two Madden 09 lanes both ran the ISO9660 self-tests; over --all that
        # is one proof paid for twice.
        if already_run is not None and tuple(argv) in already_run:
            print(f"  ok    selftest {name} (already run for this game)")
            continue
        _run(argv, root, f"selftest {name}", verbose)
        if already_run is not None:
            already_run.add(tuple(argv))
    if conformance and spec.get("conformance", True):
        run_conformance(game_id, root, verbose)
    return pass_token(game_id, lane)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="validate_game_lane.py", description=__doc__.splitlines()[0])
    parser.add_argument("--game", required=True, help="game id, e.g. madden09_ps2")
    parser.add_argument("--lane", action="append", default=[],
                        help="lane validator key; repeatable")
    parser.add_argument("--all", action="store_true", help="every lane the manifest declares")
    parser.add_argument("--list", action="store_true", help="print the lanes and exit")
    parser.add_argument("--verbose", action="store_true",
                        help="let each step print its own output")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    try:
        root = args.root.resolve()
        document = load_manifest(args.game, root)
        lanes = sorted(document["lanes"])
        if args.list:
            for lane in lanes:
                print(f"{lane}\t{pass_token(args.game, lane)}\t"
                      f"{document['lanes'][lane].get('what', '')}")
            return 0
        selected = lanes if args.all else args.lane
        if not selected:
            raise ValidatorError("name a lane with --lane, or run every lane with --all.")

        # --all runs the harness once for the game rather than once per lane:
        # every lane's conformance run proves the same 544 checks.
        shared = args.all and any(document["lanes"][lane].get("conformance", True)
                                  for lane in selected)
        already_run: Optional[set] = set() if args.all else None
        tokens = [run_lane(args.game, lane, document, root, args.verbose,
                           conformance=not shared, already_run=already_run)
                  for lane in selected]
        if shared:
            print(f"{args.game} -- the harness, once for every lane above")
            run_conformance(args.game, root, args.verbose)
        for token in tokens:
            print(token)
    except ValidatorError as exc:
        print(f"validation refused: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
