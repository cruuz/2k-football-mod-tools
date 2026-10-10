"""b77 / a1: what each of the 51 ESPN 25th Anniversary menu entries must show and open, from the authored data.

Plain Python (no emulator): the retail situation.iff decoded here for rows 1 to 25, the moments data for rows 26 to
51, the field, venue and era catalogs, and the chronological display order computed from the dates. Used by the native
menu proof (tests/nfl2k5_b77_menu_native.py) and by the a2 player-list generator.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_espn25_more_moments as mm  # noqa: E402

MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")


def iso(date_text):
    m = re.fullmatch(r"([A-Z][a-z]+) (\d{1,2}), (\d{4})", date_text)
    return datetime.date(int(m[3]), MONTHS.index(m[1]) + 1, int(m[2]))


def retail_rows(retail_situ):
    """The 25 retail records of the retail situation.iff, decoded in Python (not by the game)."""
    body = retail_situ[32:32 + mm.sc.u32(retail_situ, 4)]
    assert mm.sc.u32(body, 64) == 25
    rows = []
    for i in range(25):
        at = mm.sc.RECORDS + i * mm.sc.STRIDE
        text = lambda off: mm.sc.utf16(body, mm.sc.rel(body, at + off))      # noqa: E731
        u32 = lambda off: struct.unpack_from("<I", body, at + off)[0]        # noqa: E731
        f32 = lambda off: struct.unpack_from("<f", body, at + off)[0]        # noqa: E731
        rows.append(dict(title=text(0), date=text(12), away=(text(20), u32(0x1C)), home=(text(24), u32(0x20)),
                         user_side=u32(0x24), possession=u32(0x28), score_now=(u32(0x2C), u32(0x34)),
                         final=(u32(0x30), u32(0x38)), quarter=u32(0x3C) + 1, ball=f32(0x40), distance=f32(0x44),
                         down=u32(0x48), seconds=f32(0x4C), timeouts=(u32(0x50), u32(0x54)),
                         weather=u32(0x60), time=u32(0x64), temp=struct.unpack_from("<i", body, at + 0x68)[0]))
    return rows


def authored_rows(data):
    rows = []
    for m in data.moments:
        away, home = data.teams[m["away"]], data.teams[m["home"]]
        rows.append(dict(title=m["title"], date=m["date"], away=(away["selector"], away["season"]),
                         home=(home["selector"], home["season"]), user_side=0 if m["user_side"] == "away" else 1,
                         possession=0 if m["possession"] == "away" else 1,
                         score_now=(m["score_now"]["away"], m["score_now"]["home"]),
                         final=(m["final_score"]["away"], m["final_score"]["home"]), quarter=m["quarter"],
                         ball=data.ball_yards(m), distance=float(m["distance"]), down=m["down"],
                         seconds=float(mm._clock(m["clock"])), timeouts=(m["timeouts"]["away"], m["timeouts"]["home"]),
                         weather=mm.WEATHER[m["weather"]], time=mm.TIME_OF_DAY[m["time_of_day"]],
                         temp=m["temperature"], away_key=m["away"], home_key=m["home"]))
    return rows


def expected_rows(retail_situ, data, *, named=True):
    """51 rows in physical order: the facts a click must open, plus the venue, field and era facts of that row.
    named=True is the E2 text profile (data/espn25_previews_2026.json) that the shipped disc and the Studio's named
    previews put on rows 1 to 50; named=False keeps the retail titles and dates."""
    rows = retail_rows(retail_situ) + authored_rows(data)
    assert len(rows) == 51
    if named:
        for row, preview in zip(rows, mm.named_previews()):
            row["title"], row["date"] = preview["text"]["title"], preview["text"]["date"]
    catalog = {r["row"]: r for r in json.loads((ROOT / "data/nfl2k5_espn25_fields.json").read_text())["moments"]}
    venues = {r["row"]: r for r in mm_venues()}
    eras = {r["row"]: r for r in json.loads((ROOT / "data/nfl2k5_era_rules.json").read_text())["mappings"]}
    for i, row in enumerate(rows):
        number = i + 1
        row["physical"] = number
        row["stadium"] = catalog[number]["native_stadium_index"]
        row["venue"] = venues[number]["venue"]
        row["era"] = eras[number]
        assert catalog[number]["date"] == iso(row["date"]).isoformat(), f"field catalog row {number} is another date"
        assert venues[number]["date"] == iso(row["date"]).isoformat(), f"venue catalog row {number} is another date"
        date = iso(row["date"])
        season = date.year if date.month >= 8 else date.year - 1
        assert eras[number]["season"] == season, f"era catalog row {number} is another season"
    return rows


def mm_venues():
    from mod_editor.core import nfl2k5_moment_venues as venues
    return venues.rows()


def display_order_from(rows):
    """Chronological display row -> physical row (1-based), computed here from the dates, not by the code under test."""
    return [row["physical"] for row in sorted(rows, key=lambda r: (iso(r["date"]), r["physical"]))]
