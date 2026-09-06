"""``python -m mod_editor.games.nfl2k5_ps2``: this game alone, with no studio.

``--window <id>`` opens one of its windows; with no arguments it describes the
module.  Everything else is ``python -m mod_editor.games``.
"""

from __future__ import annotations

import sys
from typing import Optional, Sequence


def main(argv: Optional[Sequence[str]] = None) -> int:
    # Imported here, not at module level: a game package reaches the core only
    # through the contract at import time (the boundary check enforces it).
    from mod_editor.games.__main__ import main as games_main

    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments:
        return games_main(["open", "nfl2k5_ps2", *arguments])
    return games_main(["show", "nfl2k5_ps2"])


if __name__ == "__main__":
    raise SystemExit(main())
