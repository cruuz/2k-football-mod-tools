"""The text members of the ZIP, edited one line slot at a time.

72 members of the 2002 disc and 74 of the 2003 disc are plain text, in two
shapes [M]: the ``*_crowd.ini`` crowd tables, ``field.tab`` and (2003)
``credits.txt`` are printable ASCII with CRLF endings, 32 of 32 and 34 of 34;
the 40 ``.trv`` trivia banks are ``size % 40 == 0`` on 40 of 40 with every
record printable ASCII padded with NUL.

The lane is :class:`mod_editor.games._lanes.blitz_zip_lanes.TextLineLane`; this
file is the three rows it takes on **this** disc -- which members, which page,
and this game's own schema string.
"""

from __future__ import annotations

from typing import Dict, Optional, Sequence

from mod_editor.games._lanes.blitz_zip_lanes import TextLineLane, text_lane_main

from . import containers

SCHEMA = "nflblitz2003_ps2_text_lines/v1"
GAME_ID = containers.GAME_ID

CROWD_LANE = TextLineLane(
    containers, SCHEMA,
    "identity.crowd_tables", "colors", "identity", "The per-team crowd tables",
    suffix=containers.CROWD_SUFFIX, validator="text",
    what="One CRLF ASCII table per NFL team; the 2003 disc adds the Houston Texans.")
FIELD_LANE = TextLineLane(
    containers, SCHEMA,
    "gameplay.field_table", "gameplay_tuning_sliders", "gameplay", "field.tab",
    exact=(containers.FIELD_TABLE,), validator="text",
    what="The one gameplay table on the disc, CRLF ASCII with a leading comment line.")
TRIVIA_LANE = TextLineLane(
    containers, SCHEMA,
    "playbooks.trivia_banks", "scripts_config", "playbooks", "The trivia banks",
    suffix=containers.TRIVIA_SUFFIX, exact=containers.LOOSE_TEXT, validator="text",
    what="40 banks of fixed 40-byte NUL-padded ASCII records, and the 2003 disc's credits.")

LANES = (CROWD_LANE, FIELD_LANE, TRIVIA_LANE)
_BY_NAME: Dict[str, TextLineLane] = {"crowd": CROWD_LANE, "field": FIELD_LANE,
                                     "trivia": TRIVIA_LANE}


def _main(argv: Optional[Sequence[str]] = None) -> int:
    return text_lane_main(containers, _BY_NAME, "NFL Blitz 2003 (PS2)", argv)


__all__ = ["CROWD_LANE", "FIELD_LANE", "LANES", "SCHEMA", "TRIVIA_LANE", "TextLineLane"]


if __name__ == "__main__":
    raise SystemExit(_main())
