"""A synthetic franchise save with a real-shaped coach table, for the b780 head coach move tests.

``synthetic_staff_franchise`` is the core tests' synthetic franchise (three league clubs: IND, ATL, SF) with six coach
records grafted into the arena: the three clubs' head coaches, one named coach no club employs and the game's two empty
placeholder records.  The coach text (first name, last name, three biography lines per record) is laid end to end in one
region with zeros after it, exactly the shape the retail and SOFTDRINK rosters have, so the real text writer runs on
it.  Variants break one rule at a time so every refusal can be tested.
"""

from __future__ import annotations

import struct
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_franchise_save as fs  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from test_nfl2k5_franchise_save import synthetic_franchise  # noqa: E402
from test_nfl2k5_roster_records import synthetic_body  # noqa: E402

COACH_AT = 0x85000                      # a zero stretch of the synthetic arena (file offset)
STRINGS_AT = 0x86000
NONE = None

#: first, last, biography lines, photo, body, flags, career numbers, the club that employs him
STAFF = (
    ("Bill", "Belichick", ("One of the winningest coaches", "in football history", ""), 7016, 21, 0,
     dict(seasons_with_team=5, total_seasons=10, wins=75, losses=69, ties=0, season_wins=3, season_losses=1,
          winning_seasons=5, super_bowls=2, playoff_wins=7, playoff_losses=1, super_bowl_wins=2, super_bowl_losses=0), 0),
    ("Andy", "Reid", ("An offensive mastermind", "", ""), 7013, 13, 0,
     dict(seasons_with_team=13, total_seasons=27, wins=279, losses=157, ties=1, season_wins=2, season_losses=2,
          winning_seasons=21, super_bowls=6, playoff_wins=25, playoff_losses=17, super_bowl_wins=3, super_bowl_losses=3), 1),
    ("Kyle", "Shanahan", ("", "", ""), 7025, 25, 0,
     dict(seasons_with_team=9, total_seasons=9, wins=82, losses=67, ties=0, season_wins=0, season_losses=0,
          winning_seasons=5, super_bowls=2, playoff_wins=9, playoff_losses=5, super_bowl_wins=0, super_bowl_losses=2), 2),
    ("Mike", "Holmgren", ("Won a Super Bowl with Green Bay", "", ""), 7010, 19, 0,
     dict(seasons_with_team=8, total_seasons=31, wins=174, losses=122, ties=0, winning_seasons=17, super_bowls=3,
          playoff_wins=13, playoff_losses=11, super_bowl_wins=1, super_bowl_losses=2), NONE),
    ("xxxxxxxxxx", "xxxxxxxxxx", ("", "", ""), 8999, 50, fs.COACH_FLAG_FREE, {}, NONE),
    ("************************", "************************", ("", "", ""), 8999, 0xFFFF, fs.COACH_FLAG_FREE, {}, NONE),
)


def _rel(buffer: bytearray, field: int, target: int) -> None:
    struct.pack_into("<i", buffer, field, target - field + 1)


def synthetic_staff_franchise(*, year_field: int = 7, user_team: int = 0, contiguous: bool = True,
                              free_tail: bool = True, shared_text: bool = False, shared_record: bool = False) -> bytes:
    """The synthetic franchise save plus the coach table above.

    ``contiguous=False`` puts a stray non-zero byte between two strings (a save that keeps its coach text in pieces),
    ``free_tail=False`` fills the rest of the game's 5,506-byte region so nothing can grow, ``shared_text`` makes a
    club field point at one coach string, ``shared_record`` makes two clubs lead with the same coach record.
    """

    data = bytearray(synthetic_franchise(year_field=year_field, user_team=user_team))
    save = fs.FranchiseSave(bytes(data))
    cursor = STRINGS_AT
    first_text_at = None

    def put(text: str) -> int:
        nonlocal cursor
        raw = text.encode("utf-16-le") + b"\0\0"
        at = cursor
        data[at:at + len(raw)] = raw
        cursor += len(raw)
        return at

    for index, (first, last, bio, photo, body, flags, career, _team) in enumerate(STAFF):
        record = COACH_AT + index * fs.COACH_SIZE
        for field, text in zip(fs.COACH_STRING_FIELDS, (first, last, *bio)):
            at = put(text)
            first_text_at = at if first_text_at is None else first_text_at
            _rel(data, record + field, at)
            if not contiguous and index == 2 and field == 0x00:
                data[cursor] = 0x41                          # a stray byte between two coach strings
                cursor += 2
        struct.pack_into("<H", data, record + fs.COACH_FIELDS["body"][0], body)
        data[record + fs.COACH_FLAGS] = flags
        struct.pack_into("<H", data, record + fs.COACH_FIELDS["photo"][0], photo)
        for name, value in career.items():
            rel, fmt = fs.COACH_FIELDS[name]
            struct.pack_into(fmt, data, record + rel, value)
        data[record + fs.COACH_FIELDS["playcalling_run"][0]] = 40 + index
        for k in range(len(fs.COACH_RATINGS)):
            data[record + fs.COACH_RATINGS_OFFSET + k] = 50 + 3 * index + (k % 7)
        for k in range(fs.COACH_TENDENCY_COUNT):
            data[record + fs.COACH_TENDENCIES_OFFSET + k] = 30 + 4 * k + index
    if not free_tail:
        data[STRINGS_AT + fs.COACH_STRING_REGION - 2] = 0x5A     # something else lives at the end of the region
    struct.pack_into("<I", data, fs.ARENA_ROOT + 0x30, len(STAFF))
    _rel(data, fs.ARENA_ROOT + 0x34, COACH_AT)
    for index, (*_rest, team) in enumerate(STAFF):
        if team is not None:
            _rel(data, save.team_offset(team) + rr.TEAM_COACH, COACH_AT + index * fs.COACH_SIZE)
    if shared_record:
        _rel(data, save.team_offset(2) + rr.TEAM_COACH, COACH_AT)             # SF now leads with Belichick's record too
    if shared_text:
        assert first_text_at is not None
        _rel(data, 0x84000, first_text_at)                                   # a stray reference from a zero stretch
    return bytes(data)


BODY_COACH_AT = 0x50000                 # a zero stretch of the synthetic disc body
BODY_STRINGS_AT = 0x51000


def synthetic_staff_body() -> bytes:
    """The synthetic disc ROST body (three clubs) with the same six coach records, for pages that read a disc."""

    data = bytearray(synthetic_body())
    cursor = BODY_STRINGS_AT

    def put(text: str) -> int:
        nonlocal cursor
        raw = text.encode("utf-16-le") + b"\0\0"
        at = cursor
        data[at:at + len(raw)] = raw
        cursor += len(raw)
        return at

    from mod_editor.core import nfl2k5_roster_records as records
    obj = records.OBJ_OFF
    for index, (first, last, bio, photo, body, flags, career, _team) in enumerate(STAFF):
        record = BODY_COACH_AT + index * fs.COACH_SIZE
        for field, text in zip(fs.COACH_STRING_FIELDS, (first, last, *bio)):
            _rel(data, record + field, put(text))
        struct.pack_into("<H", data, record + fs.COACH_FIELDS["body"][0], body)
        data[record + fs.COACH_FLAGS] = flags
        struct.pack_into("<H", data, record + fs.COACH_FIELDS["photo"][0], photo)
        for name, value in career.items():
            rel, fmt = fs.COACH_FIELDS[name]
            struct.pack_into(fmt, data, record + rel, value)
        data[record + fs.COACH_FIELDS["playcalling_run"][0]] = 40 + index
        for k in range(len(fs.COACH_RATINGS)):
            data[record + fs.COACH_RATINGS_OFFSET + k] = 50 + 3 * index + (k % 7)
    struct.pack_into("<I", data, obj + 0x30, len(STAFF))
    _rel(data, obj + 0x34, BODY_COACH_AT)
    document = records.load_body(bytes(data))
    for index, (*_rest, team) in enumerate(STAFF):
        if team is not None:
            _rel(data, document.teams[team].offset + records.TEAM_COACH, BODY_COACH_AT + index * fs.COACH_SIZE)
    return bytes(data)
