"""``python -m mod_editor.games``: list, open or prove game modules.

This is the command line the studio's one ``--game`` flag delegates to, and it
needs no other entry point: a user who owns only one game's release can run
``python -m mod_editor.games <game-id> --window <id>`` with no studio state.

    python -m mod_editor.games                       list hosted and refused modules
    python -m mod_editor.games <game-id>             describe one module and its windows
    python -m mod_editor.games <game-id> --window W  open one of its windows alone
    python -m mod_editor.games --chooser             open the "Select other games" chooser
    python -m mod_editor.games --conformance [ID]    run the conformance harness
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Optional, Sequence

from . import discover
from .chooser import chooser_headline, chooser_rows, open_window
from .contract import Refusal


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m mod_editor.games", description=__doc__.splitlines()[0])
    parser.add_argument("game", nargs="?", help="a hosted game id, e.g. nfl2k5_ps2")
    parser.add_argument("--window", metavar="ID", help="open this window of the game, alone")
    parser.add_argument("--chooser", action="store_true", help="open the game chooser window")
    parser.add_argument("--conformance", action="store_true", help="run the conformance harness")
    parser.add_argument("--work-dir", type=Path, help="conformance: where synthetic sources go")
    parser.add_argument("--static-only", action="store_true", help="conformance: skip the behavioural half")
    parser.add_argument("--games-root", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.conformance:
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

    report = discover(args.games_root)
    rows = chooser_rows(report)

    if args.chooser:
        from PyQt5.QtWidgets import QApplication

        from .chooser_qt import GameChooserDialog

        application = QApplication.instance() or QApplication(sys.argv[:1])
        dialog = GameChooserDialog(report)
        dialog.show()
        return application.exec_()

    if args.game is None:
        print(chooser_headline(rows))
        for row in rows:
            print(f"  {row.game_id:<16} {row.status_text:<12} {row.detail}")
        return 0

    matches = [row for row in rows if row.game_id == args.game]
    if not matches:
        print(f"error: no game module is called {args.game!r}; run without arguments to list them.",
              file=sys.stderr)
        return 2
    row = matches[0]
    if not row.loadable:
        print(f"error: {row.detail}", file=sys.stderr)
        return 1
    if args.window is None:
        print(row.detail)
        for window in row.windows:
            needs = " (needs the studio's open project)" if window.needs_studio_session else ""
            print(f"  --window {window.window_id:<12} {window.menu_label}{needs}")
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
