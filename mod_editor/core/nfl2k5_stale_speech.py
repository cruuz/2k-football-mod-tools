"""Stale per-team and per-stadium booth lines: the game says its own fallback line or nothing (beta 81, sb-booth).
EXPERIMENTAL.

Stale-line audit, parts 2 and 4, as ruled by the coordinator (2026-11-25) and corrected after the independent review:
"retarget the stadium lines that have a generic line; skip the head-coach intros; skip the stale stadiums in Berman's
city intros; skip Berman's team-history blurbs only where they state something no longer true; remove the 'Redskins'
lines; keep every correct 'Washington' call"; "a false statement is worse than an old name".

How the game picks one of these lines (static RE of the retail executable)
------------------------------------------------------------------------
A context key of the ``lines`` speech index (SPCI, outer 3, third table) has one recording per context value, per
speaker variant: the stream is the key's first stream, plus the counts of the earlier variants' lists, plus the value's
position in its list. Saying the key takes two steps.

1. The key's context handler (the table at 0x4FC850, rows {first key, last key, handler}, looked up at 0x139970)
   computes a context. The kinds this module meets (``HANDLERS``):

   * ``team`` (0x1398E0, reached from 0x139A00 home team, 0x139A20 visiting team, 0x139A40, 0x139A70, 0x139AA0,
     0x139AD0, 0x139B20, 0x139B90, 0x139BE0): the club's speech id (team record +0x154) if the key has a recording
     for it on either variant (0x67390); otherwise 997 for the home club or 998 for the visiting club, if that one is
     recorded; otherwise 999. The side is the in-game home struct (0x61C50). While the subsystem at [0xA99884] is set
     it compares with 0x2B34A0 instead (the scheduled game's home club); 0x139A70/0x139AA0 then take their club from
     0x2B34A0/0x2B34D0 as well, so their side stays consistent.
   * ``id_or_999`` (0x137EC0 the stadium number, 0x138FC0 and 0x10CCE0 a club): the value if recorded, else 999.
   * ``id_or_99`` (0x138200, key 50020): the home club's speech id if recorded, else 99.
   * ``raw`` (0x138BE0, key 512): the speech id of the club whose side of the field the ball is on, as it is.
   * ``highlight`` (0x2B3C10 -> 0x2B3B90, keys 38502/38506/38550): context 1 while [0xA99884] is clear; while it is
     set, the scheduled game's home club's id if recorded, else 997 if 998 is recorded, else 999.
   * ``caller``: key 9444 has no row in the table; its context comes from its caller, which is not traced.

2. The booth resolver 0x67560 looks for (its variant, context), then (its variant, 999), then the other variant with
   the context and with 999; when none is recorded the sequencer drops the phrase (0xC3424 -> 0xC33D9) and the
   broadcast goes on. No handler returns 0xFFFF (stadium contexts are bytes, "none" is -1, the compare is a
   zero-extended u16 against a dword), so a list value of 0xFFFF never matches; counts never change, so stream
   numbering never moves.

So removing a club from a list whose key also has 997/998 does not skip the line: the club gets the game's home or
visiting line ("The home team has it.", "Touchdown visiting team."). ``now_plays`` models both steps over the real
index and every receipt carries its result; the tests pin it per key against transcripts of the retail recordings.

What this owner does
--------------------
For each (key, context) in ``RULES`` whose condition holds on the built disc, the context's value becomes 0xFFFF in
every context list of that key (all speaker variants). Every list edited here belongs to its key alone or is shared
only by keys with identical rules (38506/38550, and Washington's "Redskins" lines on their shared lists); a list that
any other key uses refuses. A (list, context) whose recording the user replaced through the commentary replacement
(``keep_streams``) is left alone, so the user's recording stays reachable. Conditions read the built disc:

* ``row``: the stadium row with that number shows another display name than retail (renamed by the venue options;
  spaces and case are ignored);
* ``place`` / ``nickname``: the club with that speech id no longer carries its retail city (Raiders, Rams, Chargers)
  or nickname (Washington);
* ``coach``: the club's head coach is no longer its 2004 coach (a 2004 storyline is no longer current);
* ``season``: the build uses the 2026 season (a line dated by the year: "your 2004 <club>", "the beautiful new
  stadium", "Raljon, Maryland");
* ``always``: the recording names a building that was already gone in 2004 (Veterans Stadium, CMGI Field, Ericsson
  Stadium ...).

What Washington hears instead (2026 disc; side = Washington at home / away; transcripts of the retail streams):

  1201  "The home team has it." / "The visiting team has it!"          (team; 997/998)
  9405  "Ball at the home team." / "Ball at the visiting team."        (team)
  9413  "...kicking off for the home team." / "...for the visiting team." (team)
  9424  "Touchdown home team!" / "Touchdown visiting team." or, on the second speaker, "Touchdown!" (team)
  9425  "First down, home team." / "first down visiting team."         (team)
  9426  "Safety home team." / "Safety Visiting Team."                  (team)
  9427  "Interception, home team." / "Interception visiting team."     (team)
  9467  "Your home team." (home only)       9468  "The visiting team." (away only)
  38247/38853 "Away, team!" (away only)   38248/38854 "Home team." (home only)   (crowd chants)
  9414  "It's time for football!" (999)    9456  "And now, your very own team." (999)
  50020 the context-99 line "Let's get some penetration ..." (id_or_99)
  dropped: 512 (raw id; its list has no 999), 9474-9476, 38851/38852, 38859/38860 (no 997/998/999 in their lists)
  9444  untraced context source: dropped if its caller passes the raw id, the home/visiting line if it goes through
        0x1398E0.
Stadium and storyline lines: 9453 -> "visiting us for the game.", 38506 -> "over in the stadium we had", 38550 -> "the
stadium", 38502 -> "in the big city we had" (999); 38800, 38803, 13850 and 9455 are dropped. Created teams (speech id
999) lose 9455's "And now, your very own created team." (ruled).

Not edited (LATER): the halftime/postgame recaps and the franchise news (lists 5602 and 11166): there Washington
would be called "the home players" or "the visitors" outside a game or on the wrong side, so they keep "Redskins".

A disc whose roster this module cannot read, or on which no condition holds, is left alone. Data only: two bytes per
(list, context) in the one ``lines`` SPCI, stored uncompressed. Unwitnessed in game for these keys; the mechanism
(no match -> next line) was witnessed for 14039 (nfl2k5_stadium_welcome).
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Any, Callable, Iterable

from .nfl2k5_stadium_welcome import SPCI_OUTER_INDEX, SPCI_STORED, find_spci, same_name

OWNER = "nfl2k5_stale_speech"
SCHEMA = "nfl2k5_stale_speech/v2"
LABEL = "EXPERIMENTAL"
SKIP = 0xFFFF
HOME_LINE, VISITOR_LINE, GENERIC_LINE, NO_CLUB_LINE = 997, 998, 999, 99
TEAMS_2004 = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27,
              28, 29, 30, 37)

R, A, P, N, C, S = "row", "always", "place", "nickname", "coach", "season"
_STADIUM_LINE = {1: R, 3: R, 6: R, 7: R, 8: R, 11: R, 12: R, 14: R, 15: R, 18: R, 19: R, 22: R, 23: R, 24: R, 30: R}
#: key -> {context: condition}; the comment is what the retail recording says (transcribed) and what plays instead
RULES: dict[int, dict[int, str]] = {
    # "visiting us at <stadium>" -> 999 "visiting us for the game."
    9453: {**_STADIUM_LINE, 17: R, 2: A, 4: A, 16: A, 21: A, 22: A, 25: A},
    # "over at <stadium> we had" / "<stadium>." (one shared list; 4 "Erikson Stadium", 29 "Raljon, Maryland")
    # -> 999 "over in the stadium we had" / "the stadium"
    38506: {**_STADIUM_LINE, 0: R, 20: P, 25: A, 4: A, 29: S},
    38550: {**_STADIUM_LINE, 0: R, 20: P, 25: A, 4: A, 29: S},
    # "On the east side of the bay in Oakland" / "on the Mississippi River in St. Louis" / "in San Diego right by
    # Coronado Bay" -> 999 "in the big city we had"
    38502: {20: P, 23: P, 24: P},
    # Berman's pregame city intro (no generic: dropped); 26 "the beautiful new stadium", 29 "suburban Washington, D.C.
    # Raljon, Maryland"; 37 Houston ("home of the great Super Bowl 38") is still true and stays
    38800: {**_STADIUM_LINE, 0: R, 17: R, 25: R, 27: R, 28: R, 20: P, 23: P, 24: P, 9: C, 21: C, 26: S, 29: S},
    # Berman's team-history blurb, only where it is no longer true (no generic: dropped); 3 "the Bills have had
    # problems even joining the wedding party in recent years", 9 "finally starting to turn the corner"
    38803: {0: C, 3: C, 4: C, 6: C, 8: C, 9: C, 11: C, 13: C, 16: C, 17: C, 22: C, 26: C, 27: C, 28: C, 37: C,
            23: P, 24: P, 29: N},
    # the head-coach intro names the club's 2004 coach (no generic: dropped)
    13850: {team: C for team in TEAMS_2004},
    # Washington's "Redskins" lines on lists of their own (see the module docstring for what plays instead)
    512: {29: N}, 1201: {29: N}, 9414: {29: N}, 9427: {29: N}, 9444: {29: N}, 9456: {29: N}, 9467: {29: N},
    9468: {29: N}, 50020: {29: N},
    # the PA's "And now, your 2004 <club>!" (ruling 3, option a; condition: the 2026 season): no code or director site
    # queues 9455 by value, so it cannot be pointed at 9456. Its real clubs, the 2004 alumni and all-star teams are
    # dropped; its list has no 997, so they would fall back to 999 "And now, your very own created team.", and 999
    # goes too (created teams lose that line); the dated classic teams (100-168) keep theirs.
    9455: {other: S for other in (*TEAMS_2004, 31, 34, 35, 40, 41, 42, 43, 44, 45, 46, 999)},
    # Washington's "Redskins" lines on lists shared only with other "Redskins" lines: the PA (9405, 9413, 9424-9426,
    # 9474-9476), crowd chants (38851/38852, 38247/38248, 38853/38854) and Berman's team names (38859/38860)
    9405: {29: N},
    9413: {29: N},
    9424: {29: N},
    9425: {29: N},
    9426: {29: N},
    9474: {29: N},
    9475: {29: N},
    9476: {29: N},
    38851: {29: N},
    38852: {29: N},
    38859: {29: N},
    38860: {29: N},
    38247: {29: N},
    38248: {29: N},
    38853: {29: N},
    38854: {29: N},
}
TEAM, TEAM_HOME, TEAM_VISITOR = "team", "team:home", "team:visitor"
ID_OR_999, ID_OR_99, RAW, HIGHLIGHT, CALLER = "id_or_999", "id_or_99", "raw", "highlight", "caller"
#: key -> its context handler kind (the table at 0x4FC850; see the module docstring)
HANDLERS = {
    9453: ID_OR_999, 38800: ID_OR_999, 13850: ID_OR_999, 9456: ID_OR_999,           # 0x137EC0, 0x10CCE0, 0x138FC0
    38502: HIGHLIGHT, 38506: HIGHLIGHT, 38550: HIGHLIGHT,                            # 0x2B3C10
    38803: TEAM, 1201: TEAM, 9405: TEAM, 9413: TEAM, 9424: TEAM, 9425: TEAM, 9426: TEAM, 9427: TEAM,
    9414: TEAM_HOME, 9455: TEAM_HOME, 9467: TEAM_HOME, 9475: TEAM_HOME,             # 0x139A00
    9468: TEAM_VISITOR, 9474: TEAM_VISITOR, 9476: TEAM_VISITOR,                      # 0x139A20
    38852: TEAM_HOME, 38860: TEAM_HOME, 38248: TEAM_HOME, 38854: TEAM_HOME,          # 0x139A70
    38851: TEAM_VISITOR, 38859: TEAM_VISITOR, 38247: TEAM_VISITOR, 38853: TEAM_VISITOR,  # 0x139AA0
    50020: ID_OR_99, 512: RAW, 9444: CALLER,
    14039: ID_OR_999,                                       # the pregame welcome (nfl2k5_stadium_welcome), 0x137EC0
}
#: handler kind -> the handlers of the table at 0x4FC850 that are that kind (checked against the retail executable)
HANDLER_ADDRESSES = {
    TEAM: (0x139A40, 0x139AD0, 0x139B20, 0x139B90, 0x139BE0), TEAM_HOME: (0x139A00, 0x139A70),
    TEAM_VISITOR: (0x139A20, 0x139AA0), ID_OR_999: (0x137EC0, 0x138FC0, 0x10CCE0), ID_OR_99: (0x138230,),
    RAW: (0x138BE0,), HIGHLIGHT: (0x2B3C10,), CALLER: (),
}
#: context list index -> its retail values (u16 little-endian, hex); the pin every edit is checked against
RETAIL_LISTS = {
    2302: ("010002000300040006000700080009000a000b000c000d000e000f001000110012001300150016001700180019001a001e00"
         "1f0020002100250026002700e703"),
    4664: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e001f0020002500e703"),
    4522: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e00250064007b007d0090009e00a200e703"),
    5121: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e001f00200025003000320033003400350036003700380039003a003b003c003d003e003f004000"
         "410042004300440045004600470049004a004b004c004d004e004f00500051005200530054005500"),
    5224: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e001f002100220023002500280029002a002b002c002d002e00"),
    2784: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e002500"),
    231: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e001f002200230024002500280029002a002b002c002d005900e503e603"),
    538: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e001f00220023002500280029002a002b002c002d0064007d00a200e503e603"),
    1187: ("1f0022002300280029002a002b002c002d002e00a200"),
    1199: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e0025006400e703"),
    1824: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e001f00220023002500280029002a002b002c002d002e006400a200e603"),
    1870: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e001f00220023002500280029002a002b002c002d002e006400a200e503"),
    2256: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e001f00220023002500280029002a002b002c002d002e00a200e503e603"),
    2498: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e001f00220023002500280029002a002b002c002d002e00a200e703"),
    2649: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e001f00220023002500280029002a002b002c002d002e007b0090009e00a200e503"),
    2697: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e001f00220023002500280029002a002b002c002d002e007b0090009e00a200e603"),
    9905: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e0063006400650066006700680069006a006b006c006d006e006f00700071007200730074007500"
         "76007700780079007a007b007c007d007e007f00800081008200c7002b018f01"),
    1056: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e001f00220023002500280029002a002b002c002d002e006400a200e503e603"),
    1234: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e001f00220023002500280029002a002b002c002d002e006400a200e603e803e903ea03eb03ec03"
         "ed03ee03ef03f003f103f203f303f403f503f603f703f803f903fa03fb03fc03fd03fe03ff03000401040204030404040504"
         "060407040a040b040d0410041104120413041404150416044c048a04ce07"),
    1325: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e001f00220023002500280029002a002b002c002d002e0064007d00a200e503e703e803e903ea03"
         "eb03ec03ed03ee03ef03f003f103f203f303f403f503f603f703f803f903fa03fb03fc03fd03fe03ff030004010402040304"
         "04040504060407040a040b040d0410041104120413041404150416044c0465048a04cd07cf07102711271227132714271527"
         "16271727182719271a271b271d271e271f2720272127222723272427252726272727282729272a272b272c272d272e272f27"
         "32273327382739273b273c273d277427f52af82af92afa2afb2afc2afd2afe2aff2a002b012b022b032b052b062b072b082b"
         "092b0a2b0b2b0c2b0d2b0e2b0f2b102b112b122b132b142b152b162b172b1a2b1b2b202b212b232b242b252b5c2bdd2e224e"
         "234e244e254e264e274e284e294e2a4e2b4e2d4e2e4e2f4e304e314e324e334e344e354e364e374e384e394e3a4e3b4e3c4e"
         "3d4e3f4e424e434e484e494e4b4e4c4e4d4e05520a520b520c520d520e520f52105211521252135215521652175218521952"
         "1a521b521c521d521e521f5220522152225223522452255227522a522b5230523152335234523552ed553275337534753575"
         "36753775387539753a753b753e753f754075437544754575467547754a754c754d751a791b791c791d791e791f7920792179"
         "227923792679277928792b792c792d792e792f79327934793579429c439c459c479c4a9c4b9c509c579c2aa02ba02da02fa0"
         "32a033a038a03fa0"),
    1630: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e001f00220023002500280029002a002b002c002d002e0064007d00a200e503e803e903ea03eb03"
         "ec03ed03ee03ef03f003f103f203f303f403f503f603f703f803f903fa03fb03fc03fd03fe03ff0300040104020403040404"
         "0504060407040a040b040d0410041104120413041404150416044c0465048a04cd0717271d271e27ff2a052b062b2d4e1552"
         "4975"),
    1732: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e001f00220023002500280029002a002b002c002d002e0064007d00a200e503e803e903ea03ec03"
         "ed03ee03ef03f003f103f203f303f403f503f603f703f803f903fa03fb03fc03fd03fe03ff03000401040204030404040504"
         "060407040a040b040d0410041104120413041404150416044c0465048a04cd07"),
    2745: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e0025006400a200"),
    5423: ("000001000500060008000a000b000c000d000e000f00100011001200130014001500180019001b001d00"),
    5555: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e00210025003a005c005d005e005f00600061006200"),
    4460: ("00000100020003000400050006000700080009000a000b000c000d000e000f0010001100120013001400150016001700180019"
           "001a001b001c001d001e001f002100220023002500280029002a002b002c002d002e0064007b007d009000a200e503e603e703"),
    5445: ("00000100020003000400050006000700080009000a000b000c000d000e000f0010001100120013001400150016001700180019"
           "001a001b001c001d001e001f002100220023002500280029002a002b002c002d002e005c005d005e005f006000610062006400"
           "7b007d009000a200e503e603e703"),
    2385: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e001f00220023002500280029002a002b002c002d002e006400650066006700680069006a006b00"
         "6c006d006e006f0070007100720073007400750076007700780079007a007b007c007d007e007f0080008100820083008400"
         "850086008700880089008a008b008c008d008e008f0090009100920093009400950096009700980099009a009b009c009d00"
         "9e009f00a000a100a200a300a400a500a600a700a800e703"),
}
#: retail display names of the stadium rows a ``row`` condition reads (data/nfl2k5_modern_venues_2026/names.json)
RETAIL_ROWS = {0: "Arizona Stadium", 1: "The Georgia Dome", 3: "Ralph Wilson Stadium", 6: "Paul Brown Stadium",
               7: "Texas Stadium", 8: "INVESCO Field at Mile High Stadium", 11: "The RCA Dome", 12: "ALLTEL Stadium",
               14: "Pro Player Stadium", 15: "H. H. H. Metrodome", 17: "The Louisiana Super Dome",
               18: "Giants Stadium", 19: "Giants Stadium", 22: "Heinz Field", 23: "Edward Jones Dome ",
               24: "QUALCOMM Stadium", 25: "San Francisco Park", 27: "Tampa Bay Stadium", 28: "Titans Coliseum",
               30: "The Cleveland Browns Stadium"}
RETAIL_PLACES = {20: "Oakland", 23: "St. Louis", 24: "San Diego"}
RETAIL_NICKNAMES = {29: "Redskins"}
#: the 2004 head coach of each club (retail roster), by speech id
RETAIL_COACHES = {0: "Green", 1: "Mora Jr.", 2: "Billick", 3: "Mularkey", 4: "Fox", 5: "Smith", 6: "Lewis",
                  7: "Coach", 8: "Shanahan", 9: "Mariucci", 10: "Sherman", 11: "Dungy", 12: "Del Rio", 13: "Vermeil",
                  14: "Wannstedt", 15: "Tice", 16: "Belichick", 17: "Haslett", 18: "Coughlin", 19: "Edwards",
                  20: "Turner", 21: "Reid", 22: "Cowher", 23: "Martz", 24: "Schottenheimer", 25: "Erickson",
                  26: "Holmgren", 27: "Gruden", 28: "Fisher", 29: "Gibbs", 30: "Davis", 37: "Capers"}


class StaleSpeechError(ValueError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise StaleSpeechError(message)


def _rel(body: bytes, field: int) -> int:
    return field + struct.unpack_from("<I", body, field)[0] - 1


def _rows(body: bytes) -> Iterable[tuple[int, int, int, int]]:
    """(key, its position-in-row variant count, list-index array offset, first stream) for every third-table key."""
    table = _rel(body, 0x38)
    for row in range(body[0x42]):
        at = table + 16 * row
        _mask, count, variants = struct.unpack_from("<HHB", body, at + 8)
        keys_at = _rel(body, at)
        keys = struct.unpack_from(f"<{count}H", body, keys_at)
        index_at = _rel(body, at + 4)
        for p, key in enumerate(keys):
            first = struct.unpack_from("<H", body, keys_at + 2 * (count + p))[0]
            yield key, variants, index_at + 2 * variants * p, first


def context_lists(body: bytes) -> tuple[dict[int, list[int]], dict[int, set[int]], int]:
    """(key -> its context list indexes, list index -> the keys that use it, body offset of the lists table) for the
    third table of a lines SPCI body (rows: keys, list-index array, u16 mask, u16 count, u8 variants)."""
    by_key: dict[int, list[int]] = {}
    users: dict[int, set[int]] = {}
    for key, variants, index_at, _first in _rows(body):
        for v in range(variants):
            index = struct.unpack_from("<H", body, index_at + 2 * v)[0]
            by_key.setdefault(key, []).append(index)
            users.setdefault(index, set()).add(key)
    return by_key, users, _rel(body, 0x3C)


def first_streams(body: bytes) -> dict[int, int]:
    """key -> its first lines.bin stream (third table)."""
    return {key: first for key, _variants, _index_at, first in _rows(body)}


def _list_at(lists: int, index: int) -> int:
    return lists + 2 * index


def list_values(body: bytes, lists: int, index: int) -> tuple[int, ...]:
    at = _list_at(lists, index)
    count = struct.unpack_from("<H", body, at)[0]
    return struct.unpack_from(f"<{count}H", body, at + 2)


def retail_values(index: int) -> tuple[int, ...]:
    raw = bytes.fromhex(RETAIL_LISTS[index])
    return struct.unpack(f"<{len(raw) // 2}H", raw)


def list_state(index: int, values: tuple[int, ...]) -> str:
    """retail / applied (only rule contexts of its keys set to 0xFFFF) / foreign."""
    retail = retail_values(index)
    if values == retail:
        return "retail"
    if len(values) != len(retail):
        return "foreign"
    allowed = {c for key, rule in RULES.items() if index in _LIST_KEYS.get(key, ()) for c in rule}
    changed = [(r, v) for r, v in zip(retail, values) if r != v]
    return "applied" if all(v == SKIP and r in allowed for r, v in changed) else "foreign"


#: key -> the retail context lists it uses (one per speaker variant), checked against the disc in plan_lists
_LIST_KEYS = {
    9453: (2302,), 38506: (4664,), 38550: (4664,), 38502: (4522,), 38800: (5121,), 38803: (5224,),
    13850: (2784,), 9455: (2385,), 512: (231,), 1201: (538,), 9414: (1187, 1199), 9427: (1824, 1870),
    9444: (2256,), 9456: (2498,), 9467: (2649,), 9468: (2697,), 50020: (9905,), 9405: (1056,),
    9413: (1056,), 9424: (1234, 1325), 9425: (1234, 1630), 9426: (1234, 1732), 9474: (2745,),
    9475: (2745,), 9476: (2745,), 38851: (5423,), 38852: (5423,), 38859: (5555,), 38860: (5555,),
    38247: (4460,), 38248: (4460,), 38853: (5445,), 38854: (5445,),
}


def plan_lists(body: bytes) -> dict[int, tuple[int, ...]]:
    """list index -> current values, after checking the table shape: every rule key uses exactly its pinned lists,
    no other key uses them, keys sharing a list share its rules, and every list is retail or edited by this owner."""
    by_key, users, lists = context_lists(body)
    out = {}
    for key, rule in RULES.items():
        require(tuple(by_key.get(key, ())) == _LIST_KEYS[key], f"key {key} does not use its pinned context lists")
        for index in by_key[key]:
            others = users[index] - set(RULES)
            require(not others, f"context list {index} is shared with keys {sorted(others)}")
            for other in users[index]:
                require(RULES[other] == rule, f"keys {key} and {other} share list {index} with different rules")
            values = list_values(body, lists, index)
            require(list_state(index, values) != "foreign", f"context list {index} is not the retail one; refusing")
            out[index] = values
    return out


def stream_of(first: int, key: int, variant: int, context: int) -> int:
    """The lines.bin stream of (key, speaker variant, context) for a key of ``_LIST_KEYS`` (retail positions; this
    owner never changes a count, so the numbering holds on an edited index too)."""
    lists = _LIST_KEYS[key]
    return first + sum(len(retail_values(i)) for i in lists[:variant]) + retail_values(lists[variant]).index(context)


def spoken(body: bytes, key: int, context: int, side: str) -> tuple[int, list[int | None]] | None:
    """What the game plays for ``key`` when its handler is given the club or stadium ``context`` and that club is on
    ``side`` ("home" / "visitor"): (the context the handler returns, the stream per speaker variant or None when the
    phrase is dropped). None for a key whose context source is not traced (``caller``)."""
    by_key, _users, lists = context_lists(body)
    first = first_streams(body)[key]
    variants, at = [], first
    for index in by_key[key]:
        values = list_values(body, lists, index)
        variants.append((values, at))
        at += len(values)

    def recorded(c: int) -> bool:
        return any(c in values for values, _ in variants)

    kind = HANDLERS[key]
    if kind == CALLER:
        return None
    if kind in (TEAM, TEAM_HOME, TEAM_VISITOR):
        side_line = HOME_LINE if side == "home" else VISITOR_LINE
        ctx = context if context != GENERIC_LINE and recorded(context) else (
            side_line if recorded(side_line) else GENERIC_LINE)
    elif kind == ID_OR_999:
        ctx = context if recorded(context) else GENERIC_LINE
    elif kind == ID_OR_99:
        ctx = context if recorded(context) else NO_CLUB_LINE
    elif kind == RAW:
        ctx = context
    else:                                       # HIGHLIGHT, with [0xA99884] set (otherwise the context is always 1)
        ctx = context if context != GENERIC_LINE and recorded(context) else (
            HOME_LINE if recorded(VISITOR_LINE) and side == "home" else (
                VISITOR_LINE if recorded(GENERIC_LINE) and side == "visitor" else GENERIC_LINE))
    out: list[int | None] = []
    for v in range(len(variants)):
        order = [(v, ctx), (v, GENERIC_LINE)] + [(u, c) for u in range(len(variants)) if u != v
                                                 for c in (ctx, GENERIC_LINE)]
        hit = next((variants[u][1] + variants[u][0].index(c) for u, c in order if c in variants[u][0]), None)
        out.append(hit)
    return ctx, out


def sides(key: int) -> tuple[str, ...]:
    kind = HANDLERS[key]
    return ("home",) if kind == TEAM_HOME else ("visitor",) if kind == TEAM_VISITOR else ("home", "visitor")


def now_plays(body: bytes, key: int, context: int) -> dict[str, Any]:
    """{side: [stream or None per speaker variant]} for one context of ``key`` on this body ("untraced" for 9444)."""
    out: dict[str, Any] = {}
    for side in sides(key):
        result = spoken(body, key, context, side)
        if result is None:
            return {"untraced": "the caller supplies the context (no handler row); dropped or the home/visiting line"}
        out[side] = result[1]
    return out


def decide(facts: dict[str, Any]) -> dict[int, dict[int, str]]:
    """key -> {context: reason} for every rule whose condition holds on this disc."""
    rows, teams, season = facts["rows"], facts["teams"], bool(facts.get("season_2026"))
    out: dict[int, dict[int, str]] = {}
    for key, rule in RULES.items():
        for ctx, cond in rule.items():
            team = teams.get(ctx, {})
            if cond == R:
                why = (f"row s{ctx:02d} shows {rows[ctx]!r}" if ctx in rows and ctx in RETAIL_ROWS
                       and not same_name(rows[ctx], RETAIL_ROWS[ctx]) else None)
            elif cond == A:
                why = "named a building already gone in 2004"
            elif cond == P:
                why = (f"the club's city is {team.get('city')!r}" if team.get("city") not in (None, RETAIL_PLACES[ctx])
                       else None)
            elif cond == N:
                why = (f"the club's nickname is {team.get('nickname')!r}"
                       if team.get("nickname") not in (None, RETAIL_NICKNAMES[ctx]) else None)
            elif cond == S:
                why = "the build uses the 2026 season" if season else None
            else:
                why = (f"the club's head coach is {team.get('coach')!r}"
                       if team.get("coach") not in (None, RETAIL_COACHES[ctx]) else None)
            if why:
                out.setdefault(key, {})[ctx] = why
    return out


def disc_facts(path: Path | str) -> dict[str, Any]:
    """Stadium row names, and each club's city, nickname and head coach by speech id, read from the built disc."""
    from . import nfl2k5_coach_staff as staff
    from . import nfl2k5_modern_metlife as mm
    from . import nfl2k5_roster_records as rr
    with rr._outer_image()(path) as archive:
        body = archive.read_entry(rr.ROST_OUTER_INDEX)[rr.RESOURCE_HEADER_SIZE:]
    rows: dict[int, str] = {}
    for _offset, fields in mm._stadium_records(body):
        code = fields["asset_code"][1]
        if len(code) == 3 and code[0] == "s" and code[1:].isdigit():
            rows.setdefault(int(code[1:]), fields["display_name"][1])
    document = rr.RosterDocument(body, base=0)
    teams: dict[int, dict[str, Any]] = {}
    for coach in staff.read_roster(body):
        team = document.teams[coach.club.index]
        teams[coach.club.asset] = {"city": team.city, "nickname": team.nickname, "coach": coach.last}
    return {"rows": rows, "teams": teams}


def patch_body(body: bytes, decisions: dict[int, dict[int, str]],
               keep_streams: Iterable[int] = ()) -> tuple[bytes, dict[str, Any]]:
    """The body with every decided (key, context) set to 0xFFFF in the key's lists, except a (list, context) whose
    recording, for any key using that list, is in ``keep_streams`` (the user's own commentary)."""
    keep = frozenset(keep_streams)
    plan_lists(body)
    by_key, users, lists = context_lists(body)
    first = first_streams(body)
    out = bytearray(body)
    edits, kept = [], []
    for key, contexts in sorted(decisions.items()):
        for index in by_key[key]:
            retail = retail_values(index)
            for ctx in sorted(contexts):
                if ctx not in retail:
                    continue                                    # this variant's list has no such context
                mine = sorted(stream_of(first[u], u, v, ctx) for u in users[index]
                              for v, i in enumerate(_LIST_KEYS[u]) if i == index)
                if keep & set(mine):
                    kept.append({"key": key, "list": index, "context": ctx, "streams": sorted(keep & set(mine))})
                    continue
                at = _list_at(lists, index) + 2 + 2 * retail.index(ctx)
                struct.pack_into("<H", out, at, SKIP)
                edits.append({"key": key, "list": index, "context": ctx, "body_offset": f"0x{at:X}"})
    result = bytes(out)
    changed = sum(1 for a, b in zip(body, result) if a != b)
    plays = {}
    for key, contexts in sorted(decisions.items()):
        removed = [c for c in sorted(contexts) if not any(k["key"] == key and k["context"] == c for k in kept)]
        if removed:
            plays[str(key)] = {"kind": HANDLERS[key], "context": removed[0], **now_plays(result, key, removed[0])}
    return result, {"edits": edits, "changed_bytes": changed, "kept_for_user_recordings": kept, "now_plays": plays}


def _read_body(archive: Any) -> tuple[Any, int, bytes]:
    entry = archive.entries[SPCI_OUTER_INDEX]
    raw = archive.read(entry.virtual_offset, entry.size)
    at = find_spci(raw)
    return entry, at, raw[at + 0x20:at + 0x20 + SPCI_STORED]


def apply_to_image(path: Path | str, *, season_2026: bool = False, keep_streams: Iterable[int] = (),
                   progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Apply the rules that hold on this built COPY (in place, read back). Idempotent; a context already skipped
    stays skipped; a disc whose roster cannot be read is left alone. ``keep_streams``: lines streams the user's own
    commentary replaced (left reachable)."""
    from . import nfl2k5_roster_records as rr
    say = progress or (lambda _m: None)
    head = {"owner": OWNER, "schema": SCHEMA, "label": LABEL, "runtime_witnessed": False}
    try:
        facts = disc_facts(path)
    except (OSError, ValueError, KeyError, IndexError, AttributeError, struct.error) as exc:
        return {**head, "state": "skipped", "reason": f"no readable roster: {exc}", "changed_bytes": 0}
    decisions = decide({**facts, "season_2026": season_2026})
    if not decisions:
        return {**head, "state": "not_needed", "reason": "no rule holds on this disc", "changed_bytes": 0}
    with rr._outer_image()(path, writable=True) as archive:
        entry, at, body = _read_body(archive)
        result, receipt = patch_body(body, decisions, keep_streams)
        if receipt["changed_bytes"]:
            say(f"Stale booth lines: {len(receipt['edits'])} team and stadium contexts now take the game's own line or "
                f"none")
            start = entry.virtual_offset + at + 0x20
            for i in range(0, SPCI_STORED, 2):
                if body[i:i + 2] != result[i:i + 2]:
                    require(archive.write(start + i, result[i:i + 2]) == 2, "short write in the speech index")
            back = archive.read(start, SPCI_STORED)
            require(back == result, "the speech index did not read back")
    return {**head, "state": "applied", "decisions": {str(k): v for k, v in decisions.items()}, **receipt}


def pending_bytes(path: Path | str, *, season_2026: bool = False, keep_streams: Iterable[int] = ()) -> int:
    """Bytes a fresh apply would still change on this disc (0 = every rule that holds is in place): the late-step
    survival check after the final archive pass."""
    from . import nfl2k5_roster_records as rr
    decisions = decide({**disc_facts(path), "season_2026": season_2026})
    if not decisions:
        return 0
    with rr._outer_image()(path) as archive:
        _entry, _at, body = _read_body(archive)
    return patch_body(body, decisions, keep_streams)[1]["changed_bytes"]
