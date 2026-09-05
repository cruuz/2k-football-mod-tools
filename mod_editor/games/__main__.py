"""``python -m mod_editor.games``: list, open, prove, pin and scaffold game modules.

This is the command line the studio's ``--game`` / ``--games-chooser`` flags
delegate to, and it needs no studio state: a user who owns only one game's
release can open its window with ``open <game-id> --window <id>``.

    list                                  hosted and refused modules (the default)
    show <game-id>                        one module and its windows
    open <game-id> --window <id>          open one window alone
    chooser                               the "Select other games…" window
    conformance [--game ID] [--static-only] [--work-dir DIR]
    pins --check | --write | --release    the frozen contract pins (see CONTRACT_CHANGELOG.md)
    fragments <game-id> --check | --write regenerate a module's fragments from the canonical files
    new <game-id> --title T --platform P  scaffold a module that passes conformance
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Optional, Sequence

from . import discover
from .chooser import chooser_headline, chooser_rows, open_window
from .contract import ContractError, Refusal


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m mod_editor.games", description=__doc__.splitlines()[0])
    parser.add_argument("--games-root", type=Path, help=argparse.SUPPRESS)
    commands = parser.add_subparsers(dest="command")

    commands.add_parser("list", help="hosted and refused modules")

    show = commands.add_parser("show", help="one module and its windows")
    show.add_argument("game")

    opener = commands.add_parser("open", help="open one window of a module, alone")
    opener.add_argument("game")
    opener.add_argument("--window", required=True, metavar="ID")

    commands.add_parser("chooser", help="open the game chooser window")

    conformance = commands.add_parser("conformance", help="run the conformance harness")
    conformance.add_argument("--game", help="one game id (default: every hosted game)")
    conformance.add_argument("--work-dir", type=Path)
    conformance.add_argument("--static-only", action="store_true")

    pins = commands.add_parser("pins", help="check or rewrite the frozen contract pins")
    mode = pins.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--release", action="store_true", help="drop the (unreleased) marker and pin")

    fragments = commands.add_parser("fragments", help="regenerate a module's fragments")
    fragments.add_argument("game")
    fmode = fragments.add_mutually_exclusive_group(required=True)
    fmode.add_argument("--check", action="store_true")
    fmode.add_argument("--write", action="store_true")
    fragments.add_argument("--repo-root", type=Path, help=argparse.SUPPRESS)

    new = commands.add_parser("new", help="scaffold a new game module")
    new.add_argument("game")
    new.add_argument("--title", required=True)
    new.add_argument("--platform", required=True)
    new.add_argument("--serial", default=None, help="the disc serial the module recognises, if any")
    new.add_argument("--repo-root", type=Path, help=argparse.SUPPRESS)
    return parser


def _list(rows) -> int:
    print(chooser_headline(rows))
    for row in rows:
        print(f"  {row.game_id:<16} {row.status_text:<12} {row.detail}")
    return 0


def _row(rows, game_id: str):
    matches = [row for row in rows if row.game_id == game_id]
    if not matches:
        print(f"error: no game module is called {game_id!r}; run 'list' to see them.", file=sys.stderr)
        return None, 2
    row = matches[0]
    if not row.loadable:
        print(f"error: {row.detail}", file=sys.stderr)
        return None, 1
    return row, 0


def _tolerant_console() -> None:
    """Never let a console code page kill a report.

    Lane messages quote file names and bytes verbatim, so a refusal can carry a
    character the console cannot encode (a Windows console is cp1252 by default;
    a flipped pnach byte decodes to U+FFFD).  Printing has to degrade to an
    escape such as ``\\ufffd`` instead of dying with UnicodeEncodeError part
    way through the conformance lines, which is what happened on Windows.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(errors="backslashreplace")
        except (LookupError, ValueError):  # pragma: no cover - exotic streams
            pass


def main(argv: Optional[Sequence[str]] = None) -> int:
    _tolerant_console()
    args = _parser().parse_args(argv)
    command = args.command or "list"

    if command == "conformance":
        from .conformance import main as conformance_main

        forwarded: list[str] = []
        if args.game:
            forwarded += ["--game", args.game]
        if args.work_dir:
            forwarded += ["--work-dir", str(args.work_dir)]
        if args.games_root:
            forwarded += ["--games-root", str(args.games_root)]
        if args.static_only:
            forwarded.append("--static-only")
        return conformance_main(forwarded)

    if command == "pins":
        from . import pins

        try:
            if args.check:
                problems = pins.check()
                for problem in problems:
                    print(f"PIN MISMATCH: {problem}")
                if problems:
                    return 1
                print(f"CONTRACT_PINS_OK version={pins.read()['contract_version']} files={len(pins.FROZEN_FILES)}")
                return 0
            path = pins.write(release=args.release)
        except ContractError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"CONTRACT_PINS_WRITTEN {path} version={pins.read()['contract_version']}")
        return 0

    if command == "fragments":
        from .fragments import main as fragments_main

        forwarded = [args.game, "--write" if args.write else "--check"]
        if args.games_root:
            forwarded += ["--games-root", str(args.games_root)]
        if args.repo_root:
            forwarded += ["--repo-root", str(args.repo_root)]
        return fragments_main(forwarded)

    if command == "new":
        from .scaffold import main as scaffold_main

        forwarded = [args.game, "--title", args.title, "--platform", args.platform]
        if args.serial:
            forwarded += ["--serial", args.serial]
        if args.repo_root:
            forwarded += ["--repo-root", str(args.repo_root)]
        return scaffold_main(forwarded)

    report = discover(args.games_root)
    rows = chooser_rows(report)

    if command == "list":
        return _list(rows)

    if command == "chooser":
        from PyQt5.QtWidgets import QApplication

        from .chooser_qt import GameChooserDialog

        application = QApplication.instance() or QApplication(sys.argv[:1])
        dialog = GameChooserDialog(report)
        dialog.show()
        return application.exec_()

    row, code = _row(rows, args.game)
    if row is None:
        return code

    if command == "show":
        print(row.detail)
        for window in row.windows:
            needs = " (needs the studio's open project)" if window.needs_studio_session else ""
            print(f"  --window {window.window_id:<18} {window.menu_label}{needs}")
        return 0

    from PyQt5.QtWidgets import QApplication

    application = QApplication.instance() or QApplication(sys.argv[:1])
    try:
        window = open_window(report, row.game_id, args.window)
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    window.show()
    return application.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
