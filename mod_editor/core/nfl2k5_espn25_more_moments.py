"""ESPN 25th Anniversary: 25 more moments (rows 26 to 50), USA Xbox. EXPERIMENTAL / UNWITNESSED.

Retail has 25 moments: 108-byte SITU records in situation.iff (pack 0, outer 22), each naming its two teams by
franchise name and season. The select handler 20CB30 finds each side's team-season with 20BD80 in the roster's
historic list (75 entries of 16 bytes) and loads its one-team roster file with 2D17B0 into a spare slot.

This option (job m1 of the moments wave) adds up to 25 moments whose team-seasons have their own new files:
- situation.iff: the 25 retail records keep every value and string (their field-relative pointers move with the
  string pool), the new records follow, the count becomes 25 + N. The sibling chunks (MRKS, LAYT, TXTR) are
  kept byte for byte. Pack 0 grows by whole blocks (nfl2k5_resource_growth) and its disc node moves to the end.
- One new file per team-season, "h-<code>-<season>-<name>-<n>.iff": a one-team roster built from the franchise's
  closest retail historic file (team record, stadium, coach, uniform era table, appearance per position) with the
  data's 53 players, names, numbers, positions, depth, physicals and ratings. They are appended to pack F as new
  outer entries at the end of the directory (the directory has 101 free slots before any payload would move), so
  every existing outer index and payload stays where it is.
- The roster block does not grow. The new team-seasons are listed in a moment-only table inside this option's
  executable allocation, in the historic list's own 16-byte format. 20BD80 checks it first and returns 0x10000 + k;
  the two 2D17B0 calls in 20CB30 point the roster's historic list at that table for the length of the retail call.
- Executable, in place: the moment count (20C340), the completed-moment test (20C390), a won moment's mark
  (20C695), the announcer line (20C4A1: no retail line for rows 26 and up, whose speech ids belong to other lines),
  and the details screen's venue line (the call of 77460 at 2C5A71): a new row shows its real venue (the data's
  "stadium" text) while the game keeps using the stand-in stadium record for everything else.
  Rows 1 to 32 keep the saved dword (bits 25 to 31 were never used by retail); rows 33 to 50 use a session dword
  that is never saved, so no save changes shape. The reward loop stays on the original 25.

Measured (m1, v7 lab run): the main heap has 16 MB free at the Anniversary list and 128 KB after game setup, so
nothing here stays resident during a game: situation.iff is released at selection and the imported teams use the
retail spare slots.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import struct
import zlib

from . import nfl2k5_espn25_more_moments_code as assembly
from . import nfl2k5_roster_records as rr
from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

ROOT = Path(__file__).resolve().parents[2]
MOMENTS_JSON = ROOT / "data/nfl2k5_espn25_more_moments.json"
TEAMS_DIR = ROOT / "data/nfl2k5_espn25_more_teams"
APPEARANCE_JSON = ROOT / "data/nfl2k5_espn25_more_moments_appearance.json"   # beta 76.3; beside the generated data

OWNER = "nfl2k5_espn25_more_moments"
CODE_SIZE = 2560          # hooks, the moment team table (50 entries), the venue table (25) and the texts
DATA_SIZE = 16            # the session dword for rows 33 to 50, then spare zero bytes
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 16))
# beta 76.3 (25th Anniversary QC, Noah 10/2: "Player faces on stats after plays are totally wrong and random",
# "you made Chris hogan black", "not seeing star player icons"). A team file's photo id keys the post-play portrait
# and the live head; a template slot's own id showed another real person. A player now gets his own art or retail's
# historic no-photo range (no portrait, no live face: the generic head for his skin tone).
NOPHOTO_BASE = 7100
STAR_MIN_OVERALL = 90          # the main roster's star rule (nfl2k5_player_tags.STAR_MIN_OVERALL)
UI_LABEL = "25th Anniversary: 25 more moments"
BUILD_CAPTION = "25 more ESPN 25th Anniversary moments with their own team-seasons"
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Retail: the ESPN 25th Anniversary mode has 25 moments. Patch: up to 25 more "
    "(rows 26 to 50), each with its own real team-seasons, situation, stadium and uniforms. The retail 25 moments "
    "and every retail historic team stay as they are. The details screen shows each new moment's real venue name; the "
    "game plays it in the closest stadium on the disc. Completed marks for rows 26 to 32 are saved like retail; rows "
    "33 to 50 remember a win until the console is switched off. New rows have no announcer introduction. Historic "
    "and moment teams that wore a franchise's current uniform keep its retail look on a spare style, so 2026 team "
    "art shows only on the current teams.")

RETAIL_COUNT = 25
MAX_NEW = 25
MAX_TEAMS = 50                       # two new team-seasons per moment at most
MOMENT_BASE = 0x10000
SITU_OUTER = 22
FIRST_CHUNK = 32 + 0x71B0            # the retail SITU chunk (wrapper + body); the siblings follow it
FIRST_ID = 176                       # new identity numbers: retail uses up to 170, e2's research team 175
FILE_NUMBER = 9                      # the file-name digit; retail historic files use 0 to 5
MAX_SEASON_AGE_SHIFT = 99
TABLE_OFFSET = 0x100                 # the moment team table inside the code allocation
STAR_OFFSET = TABLE_OFFSET - 28   # the C1030 star copy, just before the table (beta 76.3)
VENUE_OFFSET = TABLE_OFFSET + 16 * MAX_TEAMS   # one text pointer per new row (0: the stand-in's own name)
NAMES_OFFSET = VENUE_OFFSET + 4 * MAX_NEW      # the franchise names, then the venue texts (UTF-16)
MAX_VENUE = 40                       # characters of a venue text

SYMBOLS = dict(name_equal=0x30CF0, search_resume=0x20BD86, historic_load=0x2D17B0, after_set=0x20C6A8,
               stadium_get=0x77460)
# (label, va, retail bytes, entry label, kind): kind "jmp" pads with int3 after a 5-byte jump, "call" keeps 5.
HOOKS = (
    ("search", 0x20BD80, "8b0d1829b700", "search", "jmp"),
    ("load_home", 0x20CBAA, "e8014c0c00", "load_team", "call"),
    ("load_away", 0x20CBD5, "e8d64b0c00", "load_team", "call"),
    ("mark_set", 0x20C695, "8b0d5818bf00b801000000d3e00905cc18bf00", "mark_set", "jmp"),
    ("venue", 0x2C5A71, "e8ea19dbff", "venue_name", "call"),
)
COUNT_VA, COUNT_RETAIL = 0x20C340, "b819000000c3"
# beta 76.3: C1030 (Load Historic Team's per-player import) copies a team-file record into a spare roster record field
# by field and never copies +0x52/+0x53, so a star tag (+0x53 bit 0) in a team file never reached the record the star
# renderer reads (entity+0x3C). At the end of each player's copy (0xC1D6A: EBP = file record, EDI = new record; flags,
# EAX and ECX are reloaded there) the owned code copies that one bit, replays the two retail instructions and resumes.
STAR_VA, STAR_RETAIL, STAR_RESUME = 0xC1D6A, "8b4424100fb68e1c010000", 0xC1D75
TEST_VA = 0x20C390
TEST_RETAIL = "b801000000d3e02305cc18bf00f7d81bc0f7d8c3909090909090909090909090"
ANNOUNCER_VA = 0x20C4A1
ANNOUNCER_RETAIL = "8b0d5818bf0081c13ca5ffffe97e65e6ff9090909090909090909090909090"
# Retail code this relies on, with our own sites normalised back to retail bytes before hashing.
GUARDS = (
    (0x20BD80, 0x65, "the historic (name, season) search 20BD80"),
    (0x20C110, 0x5C, "the list enter event (loads the saved marks)"),
    (0x20C250, 0x98, "the list context load and the reward loop"),
    (0x20C340, 0x70, "the count, caption and completion callbacks"),
    (0x20C3C0, 0x35, "the details exit event (team release)"),
    (0x20C400, 0xB0, "the details enter event and the announcer line"),
    (0x20C5C0, 0x5E, "the record copy at selection"),
    (0x20C670, 0x54, "the won-moment mark and save"),
    (0x20CB30, 0x15C, "the moment select handler"),
    (0x2D17B0, 0x19D, "Load Historic Team, called unchanged"),
    (0x196DC0, 0x18, "the profile's saved marks"),
    (0x30CF0, 0x40, "text equality used by the search"),
    (0x2C5A70, 0x24, "the details screen's venue text callback"),
    (0xC1D40, 0x40, "C1030's per-player tail (the star copy site)"),
)
GUARD_SHA256 = {
    0x20bd80: "d81fd0421d9f73396e3f60857037281146cb77f326876388009bec3d983322b9",
    0x20c110: "3fd5644ad672872597aba3e408dcdd950d649b3551c3d5213ff928c4862c074f",
    0x20c250: "7efb6e40464362dfb9ec86457ffd963955a4a06c3f0079850208f0df87fe758f",
    0x20c340: "053943d7a96fe96687e569137b540d2ccb0e325af9f933bf1fd9f1aa693c14ee",
    0x20c3c0: "3fc93f51da734cbea1eaa24cf02b3824c424ab5a5a9e3449817aaef22be39fbc",
    0x20c400: "9b9f2162b13f55caf8f25a9bb22f6401facfe6be36ae6a1aaebf930fb62ee81b",
    0x20c5c0: "38f566b07df7385262dd77f515ac3ae598d6da48413b328cbd334456be852f5f",
    0x20c670: "7693bd6488be429005064f91c97b4b8ddede752732d70a2b1e3c7a84b5671aac",
    0x20cb30: "404756b49a8199ff68d8255d937072f7c7cd9fdaa0aa48358c44117873cd84c5",
    0x2d17b0: "c72530b9b42e5e53d7b9fd02e004d6e5e7a719daa6d9b5ef16874bd8be27b8d3",
    0x196dc0: "87ca59fb8c7394ee8e7c9cfeba1e33964da0d8b3424e22f0e460513ca92761e4",
    0x30cf0: "50a55aabd822ec7502c7c9e027e7645f2ee867a582be30adfaebec51205fff5d",
    0x2c5a70: "54b9c1e48955285179d17ea2f1887d885bf1d72464e4a702cd646c21a19f888d",
    0xc1d40: "ab0bcc14b30f23123d9093d223ae54d955d66361b92352db108a95376dd20cac",
}

WEATHER = {"clear": 0, "light rain": 1, "heavy rain": 2, "flurries": 3, "heavy snow": 4}
TIME_OF_DAY = {"day": 0, "afternoon": 1, "night": 2}
PAIRED = {"T", "G", "DE", "DT", "OLB", "ILB", "CB", "WR"}
MINIMUMS = {"QB": 2, "K": 1, "P": 1, "WR": 4, "HB": 2, "FB": 1, "TE": 2, "T": 2, "G": 2, "C": 1, "DE": 2, "DT": 2,
            "CB": 3, "FS": 1, "SS": 1}
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")
EXTRA_COLUMNS = ("depth", "height", "weight", "birth_date", "years_pro", "hand")


class sc:
    """The SITU layout helpers this module needs, as nfl2k5_espn25_scenarios defines them (kept local so the
    executable pass's import closure does not grow by the scenario editor)."""
    RECORDS, STRIDE, POINTERS = 0x44, 0x6C, (0, 4, 8, 12, 20, 24)
    TEXT = {"title": 0, "description": 4, "objective": 8, "date": 12}

    @staticmethod
    def u32(data, at):
        require(0 <= at <= len(data) - 4, "truncated scalar")
        return struct.unpack_from("<I", data, at)[0]

    @staticmethod
    def rel(data, at):
        require(0 <= at <= len(data) - 4, "truncated pointer")
        return at + struct.unpack_from("<i", data, at)[0] - 1

    @staticmethod
    def utf16(data, at, end=None):
        end = len(data) if end is None else end
        require(0 <= at < end <= len(data) and at % 2 == 0, "invalid text pointer")
        stop = at
        while stop + 1 < end and data[stop:stop + 2] != b"\0\0":
            stop += 2
        require(stop + 1 < end, "unterminated text")
        return bytes(data[at:stop]).decode("utf-16le")

    @staticmethod
    def text_bytes(value, capacity=16384):
        require(isinstance(value, str) and value.strip() and "\0" not in value, "text must be nonempty without NUL")
        raw = value.encode("utf-16le") + b"\0\0"
        require(len(raw) <= capacity, f"text needs {len(raw)} bytes; allocation holds {capacity}")
        return raw


class MoreMomentsError(ValueError):
    """Foreign prerequisites, invalid data or an allocation outside the complete owner union."""


def require(condition, message):
    if not condition:
        raise MoreMomentsError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def name_id(name):
    return zlib.crc32(name.upper().encode("utf-16le")) & 0xFFFFFFFF


# ------------------------------------------------------------------------------------------------------------ data

def _read_json(path):
    raw = Path(path).read_bytes()
    require(len(raw) <= 4 * 1024 * 1024, f"{path}: larger than 4 MiB")
    return json.loads(raw)


def _clock(text):
    m = re.fullmatch(r"(\d{1,2}):([0-5]\d)", str(text))
    require(m is not None, f"clock {text!r} must be M:SS")
    seconds = int(m.group(1)) * 60 + int(m.group(2))
    require(0 < seconds <= 900, f"clock {text!r} must be 0:01 to 15:00")
    return seconds


def _date_ok(text):
    m = re.fullmatch(r"([A-Z][a-z]+) (\d{1,2}), (\d{4})", str(text))
    require(m is not None and m.group(1) in MONTHS, f"date {text!r} must read like 'February 3, 2008'")
    datetime.date(int(m.group(3)), MONTHS.index(m.group(1)) + 1, int(m.group(2)))
    return text


def _ascii(text, label, low, high):
    require(isinstance(text, str) and text == text.strip() and text, f"{label} must be text")
    require(all(32 <= ord(ch) < 127 for ch in text), f"{label} must be plain ASCII")
    require("—" not in text and "--" not in text, f"{label}: no em dashes")
    require(low <= len(text) <= high, f"{label} must be {low} to {high} characters, not {len(text)}")
    return text


class Data:
    """The moments and their team-seasons, validated against the contract (docs/..._contract.md)."""

    def __init__(self, moments, teams, rosters, appearance=None):
        self.moments, self.teams, self.rosters = moments, teams, rosters
        self.appearance = appearance

    @classmethod
    def load(cls, moments_path=MOMENTS_JSON, teams_dir=TEAMS_DIR, appearance_path=None):
        for path in (Path(moments_path), Path(teams_dir) / "teams.json"):
            require(path.is_file(), f"25 more moments: the moments data is missing ({path.name})")
        doc = _read_json(moments_path)
        require(isinstance(doc, dict) and doc.get("schema") == 1 and isinstance(doc.get("moments"), list),
                "moments file must be {schema: 1, moments: [...]}")
        tdoc = _read_json(Path(teams_dir) / "teams.json")
        require(isinstance(tdoc, dict) and tdoc.get("schema") == 1 and isinstance(tdoc.get("teams"), dict),
                "teams.json must be {schema: 1, teams: {...}}")
        moments = doc["moments"]
        require(1 <= len(moments) <= MAX_NEW, f"1 to {MAX_NEW} moments, not {len(moments)}")
        used = []
        for m in moments:
            for side in ("away", "home"):
                key = m.get(side)
                require(key in tdoc["teams"], f"moment {m.get('id')!r}: unknown team {key!r}")
                if key not in used:
                    used.append(key)
        require(len(used) <= MAX_TEAMS, f"at most {MAX_TEAMS} team-seasons")
        teams, rosters = {}, {}
        for key in used:
            teams[key] = dict(tdoc["teams"][key], team_key=key)
            path = Path(teams_dir) / f"{key}.csv"
            require(path.is_file(), f"25 more moments: the roster of {key} is missing ({path.name})")
            raw = path.read_bytes()
            require(len(raw) <= 256 * 1024, f"{path}: larger than 256 KiB")
            rosters[key] = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
        if appearance_path is None and Path(teams_dir) == TEAMS_DIR:
            appearance_path = APPEARANCE_JSON          # the shipped looks belong to the shipped rosters only
        data = cls(moments, teams, rosters, _load_appearance(appearance_path, rosters) if appearance_path else None)
        data.validate()
        return data

    def team_order(self):
        """Team-seasons in first-use order: the table order and identity numbers follow it."""
        return list(self.teams)

    def validate(self):
        ids = set()
        for m in self.moments:
            require(isinstance(m, dict), "every moment is an object")
            mid = m.get("id")
            require(isinstance(mid, str) and mid and mid not in ids, f"moment id {mid!r} must be unique text")
            ids.add(mid)
            title = _ascii(m.get("title"), f"{mid}: title", 3, 27)
            require(title == title.upper(), f"{mid}: title must be upper case")
            _date_ok(m.get("date"))
            _ascii(m.get("history"), f"{mid}: history", 120, 445)
            _ascii(m.get("goal"), f"{mid}: goal", 20, 120)
            require(type(m.get("stadium_index")) is int and 0 <= m["stadium_index"] <= 81, f"{mid}: stadium_index")
            require(m.get("user_side") in ("away", "home") and m.get("possession") in ("away", "home"),
                    f"{mid}: user_side and possession are 'away' or 'home'")
            for block in ("score_now", "final_score", "timeouts"):
                v = m.get(block)
                require(isinstance(v, dict) and set(v) == {"away", "home"}, f"{mid}: {block} needs away and home")
                for side in ("away", "home"):
                    high = 3 if block == "timeouts" else 99
                    require(type(v[side]) is int and 0 <= v[side] <= high, f"{mid}: {block}.{side}")
            require(type(m.get("quarter")) is int and 1 <= m["quarter"] <= 4,
                    f"{mid}: quarter 1 to 4 (overtime starts are not proved)")
            _clock(m.get("clock"))
            require(type(m.get("down")) is int and 0 <= m["down"] <= 4, f"{mid}: down 0 to 4")
            dist = m.get("distance")
            require(type(dist) in (int, float) and math.isfinite(dist) and 0.01 <= dist <= 99, f"{mid}: distance")
            self.ball_yards(m)
            require(m.get("weather") in WEATHER, f"{mid}: weather is one of {sorted(WEATHER)}")
            require(m.get("time_of_day") in TIME_OF_DAY, f"{mid}: time_of_day is one of {sorted(TIME_OF_DAY)}")
            require(type(m.get("temperature")) is int and -30 <= m["temperature"] <= 120, f"{mid}: temperature")
            kits = m.get("kits")
            require(isinstance(kits, dict) and set(kits) == {"away", "home"}, f"{mid}: kits need away and home")
            if m.get("stadium") is not None:
                _ascii(m["stadium"], f"{mid}: stadium (the venue text)", 3, MAX_VENUE)
        for key, t in self.teams.items():
            require(re.fullmatch(r"[a-z0-9]+", t.get("selector", "")) is not None and len(t["selector"]) <= 15,
                    f"{key}: selector must be the lower-case franchise name")
            require(type(t.get("season")) is int and 1920 <= t["season"] <= 2030, f"{key}: season")
            require(re.fullmatch(r"\d{2}", str(t.get("asset_code", ""))) is not None, f"{key}: asset_code")
            require(re.fullmatch(r"[A-Z]{2,3}", str(t.get("abbreviation", ""))) is not None, f"{key}: abbreviation")
            for field in ("nickname", "city"):
                _ascii(t.get(field), f"{key}: {field}", 2, 15)
            self._validate_roster(key)
        keys = [(t["selector"], t["season"]) for t in self.teams.values()]
        require(len(set(keys)) == len(keys), "two team_keys name the same franchise and season")
        need = strings_bytes(self)
        require(need <= CODE_SIZE - NAMES_OFFSET,
                f"the franchise names and venue texts need {need} bytes; the owned code holds "
                f"{CODE_SIZE - NAMES_OFFSET}")

    def _validate_roster(self, key):
        rows = self.rosters[key]
        require(len(rows) == 53, f"{key}: 53 players, not {len(rows)}")
        columns = set(rows[0])
        need = {"first", "last", "position", "jersey", *EXTRA_COLUMNS, *rr.RATING_BYTE_ORDER}
        require(need <= columns, f"{key}: missing columns {sorted(need - columns)}")
        counts, depths = {}, {}
        for i, row in enumerate(rows):
            for part in ("first", "last"):
                rr.validate_name(row[part])
            pos = row["position"]
            require(pos in rr.POSITIONS, f"{key} row {i}: position {pos!r}")
            counts[pos] = counts.get(pos, 0) + 1
            depth = int(row["depth"])
            require(depth >= 1, f"{key} row {i}: depth starts at 1")
            depths.setdefault(pos, []).append(depth)
            require(1 <= int(row["jersey"]) <= 99, f"{key} row {i}: jersey 1 to 99")
            require(60 <= int(row["height"]) <= 90, f"{key} row {i}: height in inches")
            require(150 <= int(row["weight"]) <= 405, f"{key} row {i}: weight 150 to 405 pounds")
            datetime.date.fromisoformat(row["birth_date"])
            require(0 <= int(row["years_pro"]) <= 31, f"{key} row {i}: years_pro 0 to 31")
            require(row["hand"] in ("", "Left", "Right"), f"{key} row {i}: hand")
            for rating in rr.RATING_BYTE_ORDER:
                require(0 <= int(row[rating]) <= 100, f"{key} row {i}: {rating} 0 to 100")
        for pos, depth in depths.items():
            require(sorted(depth) == list(range(1, len(depth) + 1)), f"{key}: {pos} depth must be 1..{len(depth)}")
            require(len(depth) <= 8, f"{key}: at most 8 at {pos} (3-bit depth fields)")
        for pos, low in MINIMUMS.items():
            require(counts.get(pos, 0) >= low, f"{key}: at least {low} {pos}")
        require(counts.get("OLB", 0) + counts.get("ILB", 0) >= 3, f"{key}: at least 3 linebackers")

    def ball_yards(self, m):
        text = str(m.get("ball_on", "")).strip()
        if text == "50":
            return 0.0
        match = re.fullmatch(r"([A-Z]{2,3}) (\d{1,2})", text)
        require(match is not None and 1 <= int(match.group(2)) <= 50, f"{m.get('id')}: ball_on like 'ATL 29'")
        abbr, line = match.group(1), int(match.group(2))
        away = self.teams[m["away"]]["abbreviation"]
        home = self.teams[m["home"]]["abbreviation"]
        require(abbr in (away, home) and away != home, f"{m.get('id')}: ball_on names {abbr}, not {away} or {home}")
        return float(50 - line) if abbr == away else float(line - 50)


# ------------------------------------------------------------------------------------------------ the SITU chunk

def kit_index(reference_uniforms, kit):
    """kit: an int uniform index, or {"era_year": Y}; reference_uniforms: [(index, first, last)] from the roster."""
    if type(kit) is int:
        require(0 <= kit <= 14 and any(i == kit for i, _, _ in reference_uniforms), f"no uniform {kit}")
        return kit
    require(isinstance(kit, dict) and type(kit.get("era_year")) is int, "kit is an index or {era_year: Y}")
    year = kit["era_year"]
    for index, first, last in reference_uniforms:
        if index and first and last >= 1900 and first <= year <= last:
            return index
    return 0


def franchise_uniforms(main_rost, asset_code):
    """[(index, first, last)] for the NFL team with this asset code: index 0 is the current uniform."""
    body = main_rost[32:]
    rel = lambda a: (a + struct.unpack_from("<i", body, a)[0] - 1) if struct.unpack_from("<i", body, a)[0] else None
    table, count = rel(0x40 + 0x1C), struct.unpack_from("<I", body, 0x40 + 0x18)[0]
    for i in range(min(count, 32)):
        t = table + i * rr.TEAM_SIZE
        if sc.utf16(body, rel(t + 0x10C)) == asset_code:
            out = [(0, 0, 0)]
            for k in range(14):
                a, b = struct.unpack_from("<HH", body, t + 0x15A + 4 * k)
                if a or b:
                    out.append((k + 1, a, b if b >= 1900 else a))
            return out
    raise MoreMomentsError(f"no NFL team uses asset code {asset_code}")


def compile_records(data, main_rost):
    """The new SITU records (108 bytes each, pointer fields zero) and their six strings."""
    out = []
    for m in data.moments:
        away, home = data.teams[m["away"]], data.teams[m["home"]]
        rec = bytearray(sc.STRIDE)
        struct.pack_into("<I", rec, 0x10, m["stadium_index"])
        struct.pack_into("<II", rec, 0x1C, away["season"], home["season"])
        struct.pack_into("<II", rec, 0x24, 0 if m["user_side"] == "away" else 1, 0 if m["possession"] == "away" else 1)
        struct.pack_into("<IIII", rec, 0x2C, m["score_now"]["away"], m["final_score"]["away"],
                         m["score_now"]["home"], m["final_score"]["home"])
        struct.pack_into("<I", rec, 0x3C, m["quarter"] - 1)
        struct.pack_into("<ff", rec, 0x40, data.ball_yards(m), float(m["distance"]))
        struct.pack_into("<I", rec, 0x48, m["down"])
        struct.pack_into("<f", rec, 0x4C, float(_clock(m["clock"])))
        struct.pack_into("<II", rec, 0x50, m["timeouts"]["away"], m["timeouts"]["home"])
        struct.pack_into("<II", rec, 0x58, kit_index(franchise_uniforms(main_rost, away["asset_code"]), m["kits"]["away"]),
                         kit_index(franchise_uniforms(main_rost, home["asset_code"]), m["kits"]["home"]))
        struct.pack_into("<IIi", rec, 0x60, WEATHER[m["weather"]], TIME_OF_DAY[m["time_of_day"]], m["temperature"])
        strings = {0: m["title"], 4: m["history"], 8: m["goal"], 12: m["date"], 20: away["selector"], 24: home["selector"]}
        out.append((bytes(rec), strings))
    return out


def named_previews():
    """The explicit E2 text profile, never arbitrary edits accepted by the recognizer."""
    rows = _read_json(ROOT / "data/espn25_previews_2026.json")["moments"]
    require(len(rows) == 50 and [r["row"] for r in rows] == list(range(1, 51)), "named preview profile rows")
    return rows


def compile_situ(retail_collection, data, main_rost, *, named=False):
    """The whole situation.iff: the grown SITU chunk, then the retail siblings byte for byte."""
    require(len(retail_collection) > FIRST_CHUNK, "situation.iff is too short")
    first = retail_collection[:FIRST_CHUNK]
    situ = first[32:]
    require(struct.unpack_from("<I", situ, 64)[0] == RETAIL_COUNT and struct.unpack_from("<I", first, 8)[0] == RETAIL_COUNT,
            "situation.iff is not the retail 25-record collection")
    body = bytearray(situ[:sc.RECORDS + RETAIL_COUNT * sc.STRIDE])
    rows = [{offset: sc.utf16(situ, sc.rel(situ, sc.RECORDS + i * sc.STRIDE + offset)) for offset in sc.POINTERS}
            for i in range(RETAIL_COUNT)]
    for rec, strings in compile_records(data, main_rost):
        body.extend(rec)
        rows.append(strings)
    if named:
        require(len(rows) == 50, "the named text profile needs all 50 moments")
        for row, authored in zip(rows, named_previews()):
            for field, offset in sc.TEXT.items():
                row[offset] = authored["text"][field]
    count = len(rows)
    struct.pack_into("<I", body, 64, count)
    for index, row in enumerate(rows):
        for offset in sc.POINTERS:
            raw = sc.text_bytes(row[offset])
            at = sc.RECORDS + index * sc.STRIDE + offset
            struct.pack_into("<i", body, at, len(body) - at + 1)
            body.extend(raw)
    body.extend(bytes(-len(body) % 16))
    require(len(body) <= 256 * 1024, "the SITU chunk exceeds 256 KiB")
    wrapper = bytearray(first[:32])
    struct.pack_into("<II", wrapper, 4, len(body), count)
    return bytes(wrapper + body) + retail_collection[FIRST_CHUNK:]


# ------------------------------------------------------------------------------------------------ the team files

def _paired_chain(depth, count):
    """Retail left/right chains: 1 = left starter (rank 0), 2 = right starter (side 0), 3 = left second..."""
    k = (depth - 1) // 2
    return (k, count - 1 - k) if depth % 2 else (count - 1 - k, k)


def _append_text(body, text):
    at = len(body)
    body.extend(text.encode("utf-16le") + b"\0\0")
    return at


def _load_appearance(path, rosters):
    """{team_key: [look, ...]} from the appearance file, row for row with each roster CSV; None when it is absent.
    A look: tone 0 (lightest) .. 5 (darkest) or null (keep the template record), dreads, and for a player found in the
    retail 2004 roster (same name and birth date) his own record's photo id, whole skin value, face and dreads."""
    if not Path(path).is_file():
        return None
    doc = _read_json(path)
    require(isinstance(doc, dict) and doc.get("schema") == 1 and isinstance(doc.get("teams"), dict),
            "appearance.json must be {schema: 1, teams: {...}}")
    out = {}
    for key, rows in rosters.items():
        looks = doc["teams"].get(key)
        if looks is None:
            continue
        require(isinstance(looks, list) and len(looks) == len(rows), f"{key}: appearance needs one row per player")
        for i, (row, look) in enumerate(zip(rows, looks)):
            require(isinstance(look, dict) and look.get("name") == f"{row['first']} {row['last']}",
                    f"{key} row {i}: appearance row names {look.get('name')!r}, the roster {row['first']} {row['last']}")
            tone = look.get("tone")
            require(tone is None or (type(tone) is int and 0 <= tone <= 5), f"{key} row {i}: tone is 0 to 5 or null")
            require(look.get("dreads", 0) in (0, 1) and type(look.get("dreads", 0)) is int, f"{key} row {i}: dreads 0 or 1")
            own = look.get("retail")
            require(own is None or (isinstance(own, dict) and set(own) == {"photo", "skin", "face", "dreads"}
                                    and all(type(own[k]) is int for k in own) and 0 <= own["photo"] <= 0xFFFF
                                    and 0 <= own["skin"] <= 31 and 0 <= own["face"] <= 15 and own["dreads"] in (0, 1)),
                    f"{key} row {i}: retail appearance")
        out[key] = looks
    return out


def _set_rel(body, field, target):
    struct.pack_into("<i", body, field, target - field + 1)


def main_people(main_rost):
    """{(first, last, birth year % 100): (pbp_id, photo_id)} for the retail 2004 roster's rostered players."""
    doc = rr.RosterDocument(main_rost[32:])
    out = {}
    for p in doc.players:
        if p.group != "team":
            continue
        v = p.record.values
        year = v["birth_year_low"] | (v["birth_year_high"] << 3)
        out.setdefault((p.first.casefold(), p.last.casefold(), year % 100), (v["pbp_id"], v["photo_id"]))
    return out


def compile_team(template_raw, team, rows, colleges, identity, people=None, *, appearance=None, main_photos=frozenset()):
    """A one-team historic roster file for one team-season, from a retail historic file of the same franchise.
    appearance: the team's appearance.json rows (or None); main_photos: every photo id the current main roster uses."""
    from . import nfl2k5_my_career_prospects as prospects
    require(template_raw[:4] == b"ROST" and struct.unpack_from("<I", template_raw, 4)[0] == len(template_raw) - 32,
            "template is not a one-team ROST resource")
    body = bytearray(template_raw[32:])
    doc = rr.RosterDocument(bytes(body))
    require(len(doc.players) == 53 and len(doc.teams) == 1 and doc.teams[0].player_count == 53,
            "template must be a 53-player one-team file")
    players = sorted(doc.players, key=lambda p: p.index)
    donors = {}
    for p in players:
        donors.setdefault(p.record.position_name, []).append(p)
    for group in donors.values():
        group.sort(key=lambda p: (min(p.record.values["depth_rank"], p.record.values["depth_side"]), p.index))
    counts = {}
    for row in rows:
        counts[row["position"]] = counts.get(row["position"], 0) + 1
    season = team["season"]
    names = {}
    # Records first (fields inside the 84 bytes), names after (appended strings).
    for index, (slot, row) in enumerate(zip(players, rows)):
        pos = row["position"]
        pool = donors.get(pos) or players
        donor = pool[min(int(row["depth"]) - 1, len(pool) - 1)]
        record = rr.PlayerRecord.decode(bytes(template_raw[32 + donor.offset:32 + donor.offset + rr.PLAYER_SIZE]))
        v = record.values
        # Pointer fields keep this slot's own encodings; the names are rewritten below.
        own = rr.PlayerRecord.decode(bytes(body[slot.offset:slot.offset + rr.PLAYER_SIZE])).values
        for key in rr.POINTER_FIELDS:
            v[key] = own[key]
        v["position"] = rr.POSITIONS.index(pos)
        depth, n = int(row["depth"]), counts[pos]
        rank, side = _paired_chain(depth, n) if pos in PAIRED else (depth - 1, 0)
        v["depth_rank"], v["depth_side"] = rank, side
        v["jersey"] = int(row["jersey"])
        v["height"] = int(row["height"])
        v["weight_raw"] = int(row["weight"]) - 150
        born = datetime.date.fromisoformat(row["birth_date"])
        shifted = born.year + (2004 - season)       # the game ages players against 2004
        stored = shifted % 100
        v["birth_year_low"], v["birth_year_high"] = stored & 7, stored >> 3
        v["birth_month"], v["birth_day"] = born.month, born.day
        v["years_pro"] = int(row["years_pro"])
        v["hand"] = 0 if row["hand"] == "Left" else 1
        for rating in rr.RATING_BYTE_ORDER:
            v[rating] = int(row[rating])
        # His own art or none: his current main-roster record (the same person), else his retail 2004 photo id while
        # no current record uses it (its portrait and face are still his), else the no-photo range.
        look = appearance[index] if appearance else {}
        v["pbp_id"], v["photo_id"] = 9000 + int(row["jersey"]), NOPHOTO_BASE + index
        hit = people.get((row["first"].casefold(), row["last"].casefold(), born.year % 100)) if people else None
        if hit:
            v["pbp_id"], v["photo_id"] = hit
        elif look.get("retail") and look["retail"]["photo"] not in main_photos:
            v["photo_id"] = look["retail"]["photo"]
        # The donor's skin, face and dreads belonged to someone else. The tone (skin bits 0-2) comes from the
        # appearance data; a player with a retail 2004 record also takes its skin group, face and dreads.
        if look.get("tone") is not None:
            if look.get("retail"):
                record.skin = (look["retail"]["skin"] & ~7) | look["tone"]
                v["face"], v["dreads"] = look["retail"]["face"], look["retail"]["dreads"]
            else:
                record.skin = (record.skin & ~7) | look["tone"]
                v["dreads"] = look.get("dreads", 0)
        v["star_tag"] = int(prospects.native_overall(record) >= STAR_MIN_OVERALL)
        college = row.get("college", "")
        if college:
            require(colleges.count(college) == 1,
                    f"college must resolve exactly once in the main table: {college!r}")
            v["college_pointer"] = colleges.index(college)
        require(0 <= v["college_pointer"] < len(colleges), "template college index outside main table")
        body[slot.offset:slot.offset + rr.PLAYER_SIZE] = record.encode()
    for slot, row in zip(players, rows):
        for part, key in (("first", "first_name_pointer"), ("last", "last_name_pointer")):
            text = row[part]
            if text not in names:
                names[text] = _append_text(body, text)
            _set_rel(body, slot.offset + rr.FIELD_BY_NAME[key].offset, names[text])
    t = doc.teams[0].offset
    # Special teams (roster-slot indexes in the team record): the template's point at its own players, so choose
    # them again from this roster (PROVED IN GAME, m1c: the template's kick returner slot held the punter).
    row_at = {slot.offset: row for slot, row in zip(players, rows)}
    template_roles = {at: _slot_role(doc, template_raw[32 + t + at]) for at in SPECIAL_TEAMS}
    for at, index in special_teams(doc.teams[0].slots, row_at, template_roles).items():
        body[t + at] = index
    short = f"{season % 100:02d}"
    for field, text in ((rr.TEAM_NICKNAME, f"{team['nickname']} '{short}"),
                        (rr.TEAM_ABBREVIATION, f"{team['abbreviation']}{short}"),
                        (rr.TEAM_CITY, team["city"])):
        _set_rel(body, t + field, _append_text(body, text))
    struct.pack_into("<H", body, t + 0x118, identity)
    body.extend(bytes(-len(body) % 16))
    out = bytearray(template_raw[:32])
    struct.pack_into("<II", out, 4, len(body), len(body))
    result = bytes(out + body)
    check = rr.RosterDocument(result[32:])
    require(len(check.players) == 53 and check.teams[0].player_count == 53
            and [p.first for p in sorted(check.players, key=lambda p: p.index)] == [r["first"] for r in rows],
            f"{team['team_key']}: team file read-back differs")
    return result


def names_bytes(teams):
    """Bytes the distinct franchise names take after the moment team table (UTF-16 with a terminator each)."""
    return sum(2 * (len(name) + 1) for name in {t["selector"] for t in teams.values()})


def venues(data):
    """Per new row, the venue text the details screen shows (the data's "stadium": the real venue's name at the
    time of the game), or None to keep the stand-in stadium record's own name."""
    return [m.get("stadium") or None for m in data.moments]


def strings_bytes(data):
    """Bytes of the owned texts: the distinct franchise names, then the distinct venue texts."""
    return names_bytes(data.teams) + sum(2 * (len(v) + 1) for v in {v for v in venues(data) if v})


def probe_data():
    """The fixed table for owner-union probes (the reservations manifest, the allocator gates): 25 rows with venue
    texts and 50 team-seasons under 20 distinct 15-character franchise names, which fills the whole owned code
    allocation. The executable owner reads only each team-season's franchise, season and asset code, the row count
    and the venue texts, so these probes do not depend on the moments data that ships in data/."""
    teams = {}
    for k in range(MAX_TEAMS):
        key = f"probe_{k:02d}"
        teams[key] = dict(team_key=key, selector=f"probefranchs{k % 20:03d}", season=1950 + k,
                          asset_code=f"{k % 32:02d}")
    # 20 names of 15 characters (640 bytes), 24 venue texts of 14 and one of 21 (764 bytes): 1,404 bytes, all of it.
    texts = [f"Probe Venue {i:02d}" for i in range(MAX_NEW - 1)] + ["Probe Venue Row Fifty"]
    moments = [dict(id=f"probe_row_{RETAIL_COUNT + 1 + i}", stadium=texts[i]) for i in range(MAX_NEW)]
    return Data(moments, teams, {})


class Probe:
    """This owner with the fixed probe table (probe_data), for owner-union probes and gates."""
    OWNER = OWNER

    @staticmethod
    def apply(payload):
        return apply(payload, probe_data())      # resolved at call time, so an ownership recorder observes it

    @staticmethod
    def status(payload):
        return status(payload, probe_data())


# The team record's special-teams bytes, each a roster-slot index (position tallies over the 107 retail teams):
# +0x194 the holder (QB 82, P 24), +0x195/+0x196 kick returners 1 and 2, +0x197 the kicker, +0x198 the long snapper
# (C 91, TE 11), +0x199 the punt returner.
HOLDER, KR1, KR2, KICKER, SNAPPER, PR = 0x194, 0x195, 0x196, 0x197, 0x198, 0x199
SPECIAL_TEAMS = (HOLDER, KR1, KR2, KICKER, SNAPPER, PR)
KR_POSITIONS = ("WR", "CB", "FS", "SS", "HB", "FB")      # the returner fix's eligible sets (nfl2k5_returner_fix)
PR_POSITIONS = ("WR", "CB", "FS", "SS", "HB")


def returner_score(row):
    """The game's returner rating (category 10, 246A80): 0.4 speed, 0.2 agility, 0.1 stamina, 0.2 break tackle,
    0.1 ball security."""
    return (0.4 * int(row["speed"]) + 0.2 * int(row["agility"]) + 0.1 * int(row["stamina"])
            + 0.2 * int(row["break_tackle"]) + 0.1 * int(row["hold_onto_ball"]))


def _starter(row):
    depth = int(row["depth"])
    return depth <= (2 if row["position"] in PAIRED else 1)     # rank 0 or side 0 of the chain


def _slot_role(doc, slot):
    """(position, depth) of the template player at a roster slot, depth counted as the data's 1..n chain order."""
    team = doc.teams[0]
    if slot >= len(team.slots):
        return None
    player = next((p for p in doc.players if p.offset == team.slots[slot]), None)
    if player is None:
        return None
    v = player.record.values
    pos = player.record.position_name
    same = [p for p in doc.players if p.record.position_name == pos]
    if pos in PAIRED:
        n = len(same)
        for depth in range(1, n + 1):
            if _paired_chain(depth, n) == (v["depth_rank"], v["depth_side"]):
                return pos, depth
        return pos, 1
    return pos, v["depth_rank"] + 1


def special_teams(slots, row_at, template_roles):
    """{team-record offset: roster-slot index} for the six special-teams bytes, chosen from this roster."""
    by_slot = [(i, row_at.get(offset)) for i, offset in enumerate(slots)]
    by_slot = [(i, row) for i, row in by_slot if row is not None]

    def find(position, depth):
        return next((i for i, row in by_slot if row["position"] == position and int(row["depth"]) == depth), None)

    def best(positions, exclude=()):
        pool = [(i, row) for i, row in by_slot if row["position"] in positions and i not in exclude]
        for group in ([x for x in pool if not _starter(x[1])], pool):   # backups first, as the game does
            if group:
                return max(group, key=lambda x: (returner_score(x[1]), -x[0]))[0]
        return None

    out = {}
    out[KR1] = best(KR_POSITIONS)
    out[KR2] = best(KR_POSITIONS, exclude=(out[KR1],))
    out[PR] = best(PR_POSITIONS)
    out[KICKER] = find("K", 1)
    holder = template_roles.get(HOLDER) or ("QB", 2)
    out[HOLDER] = find(*holder) if holder[0] in ("QB", "P") else None
    if out[HOLDER] is None:
        out[HOLDER] = find("QB", 2) if find("QB", 2) is not None else find("P", 1)
    snapper = template_roles.get(SNAPPER) or ("C", 1)
    out[SNAPPER] = find(*snapper)
    if out[SNAPPER] is None:
        out[SNAPPER] = find("C", 2) if find("C", 2) is not None else find("C", 1)
    require(all(v is not None for v in out.values()), "special teams: a role has no player")
    return out


def table_entries(data):
    """[(team_key, file name, entry bytes without the name pointer, selector, identity)] in table order."""
    out = []
    for k, key in enumerate(data.team_order()):
        t = data.teams[key]
        code = t["asset_code"]
        filename = f"h-{code}-{t['season']}-{t['selector']}-{FILE_NUMBER}.iff"
        entry = bytearray(16)
        struct.pack_into("<HB", entry, 0, t["season"], FILE_NUMBER)
        entry[4:4 + 2 * len(code)] = code.encode("utf-16le")
        out.append((key, filename, bytes(entry), t["selector"], FIRST_ID + k))
    return out


def template_for(team, descriptors):
    """The retail historic file of this franchise (same asset code) closest in season; a named template wins."""
    if team.get("template"):
        hits = [d for d in descriptors if d["filename"] == team["template"]]
        require(len(hits) == 1, f"{team['team_key']}: template {team['template']!r} is not a retail historic file")
        return hits[0]
    pool = [d for d in descriptors if d["code"] == team["asset_code"]]
    require(pool, f"{team['team_key']}: no retail historic file with asset code {team['asset_code']}; name a template")
    return min(pool, key=lambda d: (abs(d["year"] - team["season"]), -d["year"]))


# ------------------------------------------------------------------------------------------------ the executable

def code_for(code_va, data_va, entries, venue_texts=()):
    """The owned code: hooks, the moment team table at +0x100, the venue table (one text pointer per new row, 0 for
    none) after it, then the franchise names and the venue texts."""
    require(len(entries) <= MAX_TEAMS, "too many team-seasons for the table")
    require(len(venue_texts) <= MAX_NEW, "too many rows for the venue table")
    symbols = dict(SYMBOLS, table=code_va + TABLE_OFFSET, team_count=len(entries), session=data_va,
                   venue_table=code_va + VENUE_OFFSET, venue_count=len(venue_texts))
    result = bytearray(assembly.CODE)
    for offset, kind, symbol, value in assembly.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<i", result, offset)[0]
        if kind == 2:
            target -= code_va + offset
        struct.pack_into("<I", result, offset, target & 0xFFFFFFFF)
    require(len(result) <= STAR_OFFSET, "hook code exceeds its space before the star copy")
    result = result.ljust(STAR_OFFSET, b"\xcc") + star_code(code_va + STAR_OFFSET)
    names, cursor = {}, NAMES_OFFSET
    blob = bytearray()
    table = bytearray()
    for _key, _file, entry, selector, _ident in entries:
        if selector not in names:
            names[selector] = cursor + len(blob)
            blob.extend(selector.encode("utf-16le") + b"\0\0")
        row = bytearray(entry)
        struct.pack_into("<I", row, 12, code_va + names[selector])
        table.extend(row)
    texts = {}
    venue_table = bytearray()
    for text in venue_texts:
        if not text:
            venue_table.extend(bytes(4))
            continue
        if text not in texts:
            texts[text] = cursor + len(blob)
            blob.extend(text.encode("utf-16le") + b"\0\0")
        venue_table.extend(struct.pack("<I", code_va + texts[text]))
    result.extend(table.ljust(16 * MAX_TEAMS, b"\0"))
    result.extend(venue_table.ljust(4 * MAX_NEW, b"\0"))
    require(len(result) == NAMES_OFFSET, "owned code layout")
    result.extend(blob)
    require(len(result) <= CODE_SIZE, "the moment team table and texts exceed the owned code")
    return bytes(result).ljust(CODE_SIZE, b"\xcc")


def star_code(va):
    """28 bytes: dest[0x53] ^= (dest[0x53] ^ src[0x53]) & 1; mov eax,[esp+0x10]; movzx ecx,byte [esi+0x11c]; jmp back."""
    code = bytes.fromhex("8a4f53" "324d53" "80e101" "304f53") + bytes.fromhex(STAR_RETAIL)
    code += b"\xe9" + struct.pack("<i", STAR_RESUME - (va + len(code) + 5))
    require(len(code) == TABLE_OFFSET - STAR_OFFSET, "star copy size drift")
    return code


def test_code(data_va):
    """20C390: (mask >> index) & 1, the saved dword for rows 1 to 32, the session dword for 33 to 50."""
    code = bytes.fromhex("83f920" "7307" "a1cc18bf00" "eb05") + b"\xa1" + struct.pack("<I", data_va) + \
        bytes.fromhex("d3e8" "83e001" "c3")
    return code.ljust(32, b"\x90")


def announcer_guard():
    code = bytearray(bytes.fromhex("a15818bf00" "83f819" "730b" "8d883ca5ffff"))
    at = ANNOUNCER_VA + len(code)
    code += b"\xe9" + struct.pack("<i", 0x72A30 - (at + 5)) + b"\xc3"
    return bytes(code).ljust(31, b"\x90")


def sites(code_va, data_va, total):
    """(label, va, retail bytes, patched bytes) for every in-place edit."""
    out = []
    for label, va, retail, entry, kind in HOOKS:
        before = bytes.fromhex(retail)
        target = code_va + assembly.LABELS[entry]
        after = (b"\xe9" if kind == "jmp" else b"\xe8") + struct.pack("<i", target - va - 5)
        out.append((label, va, before, after.ljust(len(before), b"\xcc")))
    out.append(("count", COUNT_VA, bytes.fromhex(COUNT_RETAIL), bytes((0xB8, total, 0, 0, 0, 0xC3))))
    star = b"\xe9" + struct.pack("<i", code_va + STAR_OFFSET - STAR_VA - 5)
    out.append(("star_copy", STAR_VA, bytes.fromhex(STAR_RETAIL), star.ljust(len(STAR_RETAIL) // 2, b"\xcc")))
    out.append(("mark_test", TEST_VA, bytes.fromhex(TEST_RETAIL), test_code(data_va)))
    out.append(("announcer", ANNOUNCER_VA, bytes.fromhex(ANNOUNCER_RETAIL), announcer_guard()))
    return out


def allocations(payload):
    rows = {(a["owner"], a["kind"]): a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER}
    code, data = rows.get((OWNER, "code")), rows.get((OWNER, "data"))
    require(code is not None and data is not None and code["size"] == CODE_SIZE and data["size"] == DATA_SIZE
            and len(rows) == 2, "reserve 25 more moments with the complete owner union on a clean base")
    return code, data


def _guard_digest(image, va, size, edits):
    raw = bytearray(image.read(va, size))
    for _, at, before, _ in edits:
        lo, hi = max(va, at), min(va + size, at + len(before))
        if lo < hi:
            raw[lo - va:hi - va] = before[lo - at:hi - at]
    return sha(bytes(raw))


def guard_digests(payload):
    """Recompute the guard hashes from a retail executable (used to pin GUARD_SHA256)."""
    image = XbeImage(payload)
    return {va: _guard_digest(image, va, size, sites(0, 0, RETAIL_COUNT)) for va, size, _ in GUARDS}


def _recognize(payload, data):
    from . import nfl2k5_moment_venues as historical_venues
    payload = historical_venues.underlying(payload)
    layout = space.layout(payload)
    image = XbeImage(payload)
    entries = table_entries(data) if data is not None else []
    total = RETAIL_COUNT + (len(data.moments) if data is not None else 0)
    owned = allocations(payload) if any(a["owner"] == OWNER for a in layout["allocations"]) else None
    edits = sites(owned[0]["va"], owned[1]["va"], total) if owned else sites(0, 0, total)
    states = set()
    expected = earlier = None
    if owned and data is not None:
        code, dat = owned
        body = image.read(code["va"], CODE_SIZE)
        expected = code_for(code["va"], dat["va"], entries, venues(data))
        # beta 76.0-76.2 installed the same code without the star copy (int3 there) and left the C1030 site retail
        earlier = expected[:STAR_OFFSET] + b"\xcc" * (TABLE_OFFSET - STAR_OFFSET) + expected[TABLE_OFFSET:]
    for label, va, before, after in edits:
        actual = image.read(va, len(before))
        if label == "star_copy" and earlier is not None and body == earlier:
            # Earlier code has int3 at the star target, so only its retail hook
            # is valid. A new JMP paired with that body would jump into int3.
            states.add("applied" if actual == before else "foreign")
            continue
        states.add("retail" if actual == before else "applied" if owned and actual == after else "foreign")
    if owned:
        states.add("retail" if body == b"\xcc" * CODE_SIZE else
                   "applied" if expected is not None and body in (expected, earlier) else "foreign")
    require(states in ({"retail"}, {"applied"}), "foreign/mixed 25 more moments hooks or owned code")
    for va, size, what in GUARDS:
        pin = GUARD_SHA256.get(va)
        require(pin is None or _guard_digest(image, va, size, edits) == pin, f"foreign {what} at {va:#x}")
    return next(iter(states))


def status(payload, data=None):
    try:
        if data is None:
            data = Data.load()
        return _recognize(payload, data)
    except (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, OSError):
        return "foreign"


def apply(payload, data=None):
    """Install on a clean base, or replay an installed copy unchanged."""
    data = Data.load() if data is None else data
    state = _recognize(payload, data)
    entries = table_entries(data)
    total = RETAIL_COUNT + len(data.moments)
    common = dict(owner=OWNER, experimental=True, runtime_witnessed=False, label=UI_LABEL, rows=total,
                  team_seasons=len(entries), rx_bytes=CODE_SIZE, rw_bytes=DATA_SIZE, save_growth=0)
    if state == "applied":
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[])
    if space.status(payload) == "retail":
        allocated, receipt = space.apply(payload, REQUESTS)
    else:
        allocations(payload)
        allocated, receipt = payload, {}
    code, dat = allocations(allocated)
    result, _ = space.install_code(allocated, OWNER, code_for(code["va"], dat["va"], entries, venues(data)))
    image = XbeImage(result)
    buffer = bytearray(result)
    edits = sites(code["va"], dat["va"], total)
    for _, va, before, after in edits:
        at = image.offset(va, len(before))
        buffer[at:at + len(before)] = after
    for section in _sections(buffer):
        buffer[section.header_offset + 36:section.header_offset + 56] = section_digest(buffer, section)
    result = bytes(buffer)
    require(_recognize(result, data) == "applied", "25 more moments postcondition failed")
    return result, dict(common, status="applied", allocation=receipt,
        changed_bytes=sum(a != b for a, b in zip(payload, result)) + len(result) - len(payload),
        file_growth=len(result) - len(payload), before_sha256=sha(payload), after_sha256=sha(result),
        edits=[dict(label=name, va=hex(va), size=len(before), before=before.hex(), after=after.hex())
               for name, va, before, after in edits]
              + [dict(label="owned_code", va=hex(code["va"]), size=CODE_SIZE),
                 dict(label="owned_session", va=hex(dat["va"]), size=DATA_SIZE)],
        reservations=space.reservations(result))


# ------------------------------------------------------------------------------------------------ the disc

RETAIL_SITU_SHA256 = "8a7a3742a944afbdf96da685f96a1ea5a5f3554fc2887e2ede3bd5c898ec35cc"
SITU_ID = 0x3F407CF4
RETAIL_ROW_TEXT_SHA256 = "ec224c5bf95ebbc40ccfe251310c049321a52b4380216ee884dc424890f27754"
# the retail rows' values with the six string pointers and the two kit indexes masked: the historic styles step
# (nfl2k5_historic_styles) moves a row's kit 0 to its franchise's spare style, which checks those itself
RETAIL_ROW_VALUES_SHA256 = "b3a6e814d1ce3bd42fe45cb5c2d3dbe894be9b9ac26c1447aeffdfe987c23223"
KIT_FIELDS = (0x58, 0x5C)
RETAIL_SIBLINGS_SHA256 = "2d90ad69ec29514898636f86d73edb9a514042be89c495fe2e269149d011b4ab"
DIRECTORY_SLACK = 101          # directory slots before the first payload would have to move (retail layout)


def _disc_inputs(disc, data):
    """Everything the compile needs from the disc copy: main roster, situation.iff, templates, colleges."""
    from . import nfl2k5_music_archive as archive  # noqa: F401  (the disc model owns the reads)
    entries = disc.archive_entries
    main = disc.read_entry_range(entries[5], 0, entries[5].size)
    situ_entry = entries[SITU_OUTER]
    require(situ_entry.name_id == SITU_ID, "outer 22 is not situation.iff")
    situ = disc.read_entry_range(situ_entry, 0, situ_entry.size)
    catalog_descriptors = _retail_descriptors(main)
    by_id = {e.name_id: e for e in entries}
    templates = {}
    for key in data.team_order():
        d = template_for(data.teams[key], catalog_descriptors)
        entry = by_id.get(d["id"])
        require(entry is not None, f"{key}: template {d['filename']} is missing from the disc")
        templates[key] = disc.read_entry_range(entry, 0, entry.size)
    return main, situ, templates


def _retail_descriptors(main):
    """The roster's 75 historic entries: (year, kit, code, selector, file name, name id)."""
    body = main[32:]
    require(body[12:16] == b"ROST" and sc.rel(body, 20) == 64 and sc.u32(body, 0x98) == 75,
            "foreign main historic descriptor layout")
    table = sc.rel(body, 0x9C)
    out = []
    for index in range(75):
        at = table + 16 * index
        year = struct.unpack_from("<H", body, at)[0]
        selector = sc.utf16(body, sc.rel(body, at + 12))
        code = sc.utf16(body, at + 4, at + 12)
        filename = f"h-{code}-{year}-{selector}-{body[at + 2]}.iff"
        out.append(dict(index=index, year=year, kit=body[at + 2], code=code, selector=selector,
                        filename=filename, id=name_id(filename)))
    return out


def compile_files(main, templates, data, *, one_pool=False):
    """{file name: bytes} for every team-season, in table order. The last one ends the archive, which must end on
    a sector, so its ROST body carries the zero padding: every directory size stays its file's own wrapper size, as
    it is for all 75 retail historic files."""
    main_doc = rr.RosterDocument(main[32:])
    colleges = main_doc.colleges
    main_photos = frozenset(p.record.values["photo_id"] for p in main_doc.players)
    people = main_people(main)
    looks = getattr(data, "appearance", None) or {}
    out = {}
    entries = table_entries(data)
    for n, (key, filename, _entry, _selector, identity) in enumerate(entries):
        raw = compile_team(templates[key], data.teams[key], data.rosters[key], colleges, identity, people,
                           appearance=looks.get(key), main_photos=main_photos)
        if one_pool:
            raw = _one_pool(raw)
        if n == len(entries) - 1:
            raw = pad_to_sector(raw)
        out[filename] = raw
    return out


def pad_to_sector(raw):
    """Zero bytes after the ROST body's last string (compile_team already pads it to 16), lengths updated."""
    pad = -len(raw) % 2048
    out = bytearray(raw + bytes(pad))
    body = len(out) - 32
    struct.pack_into("<II", out, 4, body, body)
    return bytes(out)


def _one_pool(raw):
    """The One-pool positions build's historic 4-3 rule, as the pools option applies it to the retail 75."""
    from tools import nfl2k5_roster_reclassify as rc
    resource = rc.parse_resource(0, 0, raw)
    moves, _ = rc.plan_resource(resource, {})
    body = bytearray(resource.body)
    rc.apply_moves(body, moves)
    return raw[:32] + bytes(body)


def plan_image(disc, data, *, one_pool=False, named=False):
    """Compile and lay out every change; nothing is written."""
    from . import nfl2k5_resource_growth as growth
    from dataclasses import replace
    main, situ, templates = _disc_inputs(disc, data)
    require(sha(situ) == RETAIL_SITU_SHA256, "situation.iff is not the retail 25-moment collection")
    collection = compile_situ(situ, data, main, named=named)
    require(len(collection) % 16 == 0, "the grown collection must stay 16-byte aligned")
    files = compile_files(main, templates, data, one_pool=one_pool)
    entries = disc.archive_entries
    ids = {e.name_id for e in entries}
    for filename in files:
        require(name_id(filename) not in ids, f"{filename} is already on the disc")
    require(len(files) <= DIRECTORY_SLACK, "more new files than the directory's free slots")
    p0 = disc.pack_extents["0"]
    read_pack0 = lambda n, at: disc.read(n, p0.byte_offset + at)  # noqa: E731
    plan = growth.plan_pack0(read_pack0, p0.size, SITU_OUTER, SITU_ID, collection, padding_bytes=(0, 0x9F))
    growth_bytes = plan.size_after - plan.size_before
    header = sc.u32(plan.table, 0)
    count = header
    require(count == len(entries), "archive entry count changed")
    table = bytearray(plan.table)
    last = entries[-1]
    cursor = last.virtual_offset + growth_bytes + last.size
    names = list(files)
    new_rows, placed = [], []
    for i, filename in enumerate(names):
        at = (cursor + 2047) // 2048 * 2048
        raw = files[filename]
        size = len(raw)
        require(i < len(names) - 1 or size % 2048 == 0, "the last new file must end on a sector")
        new_rows.append(struct.pack("<III", name_id(filename), size, at // 2048))
        placed.append((filename, at, size))
        cursor = at + size
    end = cursor
    first_payload = entries[0].virtual_offset
    require(len(table) + 12 * len(new_rows) <= first_payload, "the directory has no free slots left")
    struct.pack_into("<I", table, 0, count + len(new_rows))
    packs = disc.packs
    f_index = len(packs) - 1
    f_start = sum(p.size for p in packs[:-1]) + growth_bytes
    f_old = disc.pack_extents["F"].size
    f_new = end - f_start
    require(f_new >= f_old and f_new % 2048 == 0, "pack F layout")
    struct.pack_into("<I", table, 12 + 4 * f_index, f_new // 2048)
    table.extend(b"".join(new_rows))
    plan = replace(plan, table=bytes(table))
    return dict(collection=collection, files=files, placed=placed, plan=plan, growth=growth_bytes,
                f_start=f_start, f_old=f_old, f_new=f_new, count_before=count, count_after=count + len(new_rows))


def apply_to_image(path, *, data=None, one_pool=False, named=False):
    """Grow situation.iff in pack 0, append the team files in pack F, switch both disc nodes. Rollback on failure."""
    from . import nfl2k5_music_archive as archive
    from . import nfl2k5_resource_growth as growth
    from . import platform_compat as io
    data = Data.load() if data is None else data
    path = Path(path).resolve()
    state = image_status(path, data)
    if state == "applied":
        if named:
            require(named_image_status(path) == "applied", "rebuild from retail to select the named preview profile")
        return dict(status="already_applied", image_growth=0)
    require(state == "retail", f"25 more moments: the disc resources are {state}")
    with archive.Disc(path, descriptors=()) as disc:      # every read below goes through this descriptor
        original_identity = archive.identity(path)
        laid = plan_image(disc, data, one_pool=one_pool, named=named)
        p0, pf = disc.pack_extents["0"], disc.pack_extents["F"]
        old_f = disc.read(pf.size, pf.byte_offset)
        node0, nodef = disc.nodes["0"][0], disc.nodes["F"][0]
        old_nodes = [(node0, struct.pack("<II", p0.sector, p0.size)), (nodef, struct.pack("<II", pf.sector, pf.size))]
        read_pack0 = lambda n, at: disc.read(n, p0.byte_offset + at)  # noqa: E731
        old_size = disc.image_size
        base = p0.base_offset
        new_f = bytearray(old_f)
        for filename, at, size in laid["placed"]:
            offset = at - laid["f_start"]
            if offset > len(new_f):
                new_f.extend(bytes(offset - len(new_f)))
            require(offset == len(new_f), "pack F placement")
            raw = laid["files"][filename]
            new_f.extend(raw + bytes(size - len(raw)))
        new_f.extend(bytes(laid["f_new"] - len(new_f)))
        require(len(new_f) == laid["f_new"], "pack F length")
        require(archive.identity(path) == original_identity, "image changed after preflight")
        with path.open("r+b") as writer:
            fd = writer.fileno()

            def write(blob, at):
                require(io.pwrite(fd, blob, at) == len(blob), "short write")
            try:
                offset0 = archive.align_up(old_size)
                if offset0 > old_size:
                    write(bytes(offset0 - old_size), old_size)
                transport = growth.write_pack0(fd, read_pack0, laid["plan"], offset0)
                end0 = offset0 + laid["plan"].size_after
                offsetf = archive.align_up(end0)
                if offsetf > end0:
                    write(bytes(offsetf - end0), end0)
                write(bytes(new_f), offsetf)
                require(io.pread(fd, len(new_f), offsetf) == bytes(new_f), "pack F read-back")
                write(struct.pack("<II", (offset0 - base) // 2048, laid["plan"].size_after), node0)
                write(struct.pack("<II", (offsetf - base) // 2048, len(new_f)), nodef)
                os.fsync(fd)
                require(image_status(path, data) == "applied", "25 more moments: read-back failed")
            except Exception as exc:
                try:
                    for node, raw in reversed(old_nodes):
                        write(raw, node)
                    os.ftruncate(fd, old_size)
                    os.fsync(fd)
                except Exception as rollback:  # noqa: BLE001
                    raise MoreMomentsError(f"{exc}; rollback failed: {rollback}; discard the output copy") from exc
                raise
            growth_total = os.fstat(fd).st_size - old_size
    return dict(status="applied", experimental=True, runtime_witnessed=False, rows=RETAIL_COUNT + len(data.moments),
                team_files=[dict(file=f, virtual_offset=at, size=size) for f, at, size in laid["placed"]],
                directory_count=[laid["count_before"], laid["count_after"]], pack0_transport=transport,
                pack_f=[laid["f_old"], laid["f_new"]], image_growth=growth_total, one_pool=one_pool,
                named_previews=named)


def situ_rows(collection, data):
    """'applied' when a grown situation.iff holds the retail 25 rows (values and texts) and exactly the data's rows."""
    count = RETAIL_COUNT + len(data.moments)
    first_len = 32 + sc.u32(collection, 4)
    if sc.u32(collection, 8) != count or len(collection) <= first_len:
        return "foreign"
    body = collection[32:first_len]
    if sc.u32(body, 64) != count or sha(collection[first_len:]) != RETAIL_SIBLINGS_SHA256:
        return "foreign"
    rows, values = [], []
    for i in range(count):
        record = body[sc.RECORDS + i * sc.STRIDE:sc.RECORDS + (i + 1) * sc.STRIDE]
        rows.append([sc.utf16(body, sc.rel(body, sc.RECORDS + i * sc.STRIDE + p)) for p in sc.POINTERS])
        masked = bytearray(record)
        for p in sc.POINTERS + KIT_FIELDS:
            masked[p:p + 4] = bytes(4)
        values.append(bytes(masked))
    if sha(json.dumps([r[4:] for r in rows[:RETAIL_COUNT]]).encode()) != "ded9e4c02882ef9e32d90dfb6efc991803624b5c4725730fc6dc434467f76ce2":
        return "foreign"
    known_named = count == 50 and all(
        all(rows[i][list(sc.POINTERS).index(offset)] == authored["text"][field]
            for field, offset in sc.TEXT.items()) for i, authored in enumerate(named_previews()))
    if ((sha(json.dumps(rows[:RETAIL_COUNT]).encode()) != RETAIL_ROW_TEXT_SHA256 and not known_named)
            or sha(b"".join(values[:RETAIL_COUNT])) != RETAIL_ROW_VALUES_SHA256):
        return "foreign"
    for m, row in zip(data.moments, rows[RETAIL_COUNT:]):
        if row != [m["title"], m["history"], m["goal"], m["date"], data.teams[m["away"]]["selector"],
                   data.teams[m["home"]]["selector"]]:
            return "foreign"
    return "applied"


def named_image_status(path):
    from . import nfl2k5_historic_styles as hs
    try:
        with hs.Source(path) as src:
            collection = src.get(identity=SITU_ID)
        body = collection[32:32 + sc.u32(collection, 4)]
        if sc.u32(body, 64) != 50:
            return "retail"
        for i, row in enumerate(named_previews()):
            for field, offset in sc.TEXT.items():
                if sc.utf16(body, sc.rel(body, sc.RECORDS + i * sc.STRIDE + offset)) != row["text"][field]:
                    return "foreign"
        return "applied"
    except (ValueError, KeyError, IndexError, struct.error, OSError):
        return "foreign"


def image_status(path, data=None):
    """'retail' (25 retail moments, none of the files), 'applied' (the compiled collection and every file), else foreign."""
    from . import nfl2k5_music_archive as archive
    try:
        data = Data.load() if data is None else data
        with archive.Disc(Path(path), descriptors=()) as disc:
            entries = disc.archive_entries
            situ_entry = entries[SITU_OUTER]
            if situ_entry.name_id != SITU_ID:
                return "foreign"
            situ = disc.read_entry_range(situ_entry, 0, situ_entry.size)
            by_id = {e.name_id: e for e in entries}
            names = [f for _k, f, _e, _s, _i in table_entries(data)]
            present = [name_id(f) in by_id for f in names]
            if sha(situ) == RETAIL_SITU_SHA256 and not any(present):
                return "retail"
            if not all(present):
                return "foreign"
            if situ_rows(situ, data) != "applied":
                return "foreign"
            main = disc.read_entry_range(entries[5], 0, entries[5].size)
            colleges = rr.RosterDocument(main[32:]).colleges
            for key, filename, _entry, _selector, identity in table_entries(data):
                raw = disc.read_entry_range(by_id[name_id(filename)], 0, by_id[name_id(filename)].size)
                body_len = struct.unpack_from("<I", raw, 4)[0]
                doc = rr.RosterDocument(raw[32:32 + body_len])
                team = doc.teams[0]
                if (len(doc.players) != 53 or struct.unpack_from("<H", raw, 32 + team.offset + 0x118)[0] != identity
                        or [p.first for p in sorted(doc.players, key=lambda p: p.index)] != [r["first"] for r in data.rosters[key]]):
                    return "foreign"
                for player, row in zip(sorted(doc.players, key=lambda p: p.index), data.rosters[key]):
                    index = player.record.values["college_pointer"]
                    name = row.get("college", "")
                    if not 0 <= index < len(colleges):
                        return "foreign"
                    if name and (colleges.count(name) != 1 or colleges[index] != name):
                        return "foreign"
            return "applied"
    except (ValueError, KeyError, IndexError, struct.error, OSError):
        return "foreign"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("status", help="executable status against the repository's moments data")
    p.add_argument("source", type=Path)
    p = sub.add_parser("image-status", help="disc resources status (situation.iff and the team files)")
    p.add_argument("image", type=Path)
    args = parser.parse_args(argv)
    if args.command == "status":
        require(args.source.stat().st_size <= 16 * 1024 * 1024, "choose default.xbe, at most 16 MiB")
        receipt = dict(status=status(args.source.read_bytes()), owner=OWNER, experimental=True, runtime_witnessed=False)
    else:
        receipt = dict(status=image_status(args.image), owner=OWNER, experimental=True, runtime_witnessed=False)
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
