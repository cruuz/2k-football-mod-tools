#!/usr/bin/env python3
"""Offline, deterministic generator for the 25 more ESPN 25th Anniversary moments (job m2, 2026-09-23).

EXPERIMENTAL / UNWITNESSED data for the m1 engine (docs/nfl2k5_espn25_more_moments_data.md has the schema).

Inputs, never committed:
- nflverse-data release files (CC-BY-4.0), downloaded unchanged into --inputs: play_by_play_<season>.csv.gz,
  roster_<season>.csv, roster_weekly_<season>.csv (2002 on), depth_charts_<season>.csv (2001 on),
  stats_player_reg_<season>.csv.gz, snap_counts_<season>.csv (2012 on), combine.csv, players.csv;
- the user's retail ESPN NFL 2K5 (USA) game (--retail): the 2004 main roster (the ratings reference, the
  college table, the retail identities of players 2K5 already had) and the retail historic team files.
The hand-written part (titles, texts, goals, the chosen plays, stadium and kit choices, sources) is
tools/nfl2k5_espn25_more_moments_spec.json; the cited 40-yard times of players the nflverse combine file lacks
are data/nfl2k5_ratings_forty_sources.json (each with its page and quote). Everything else is computed.

Outputs: data/nfl2k5_espn25_more_moments.json, data/nfl2k5_espn25_more_teams/ (teams.json, manifest.json and one
CSV per team-season) and data/nfl2k5_ratings_reference.json. --check regenerates into temporary storage and
compares every output byte.
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import re
import sys
import tempfile
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core import nfl2k5_ratings_model as rm  # noqa: E402

DEFAULT_INPUTS = Path("/media/noah/Storage/.b76-research/m2/inputs/nflverse")
DEFAULT_RETAIL = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)")
SPEC = ROOT / "tools/nfl2k5_espn25_more_moments_spec.json"
OUT_DATA = ROOT / "data"
MOMENTS_NAME = "nfl2k5_espn25_more_moments.json"
TEAMS_DIR = "nfl2k5_espn25_more_teams"
REFERENCE_NAME = "nfl2k5_ratings_reference.json"
FORTY_SOURCES = ROOT / "data/nfl2k5_ratings_forty_sources.json"   # hand-curated input (cited 40 times)
EVIDENCE = "EXPERIMENTAL / UNWITNESSED: sourced data and a documented ratings model; no lab run, not played by Noah"
CSV_COLUMNS = (("pool", "index", "first", "last", "position", "jersey", "college") + tuple(rr.RATING_BYTE_ORDER)
               + ("depth", "height", "weight", "birth_date", "years_pro", "hand"))
POSITION_ORDER = ("QB", "HB", "FB", "WR", "TE", "T", "G", "C", "DE", "DT", "OLB", "ILB", "CB", "FS", "SS", "K", "P")
MINIMUMS = {"QB": 2, "K": 1, "P": 1, "WR": 4, "HB": 2, "FB": 1, "TE": 2, "T": 2, "G": 2, "C": 1, "DE": 2, "DT": 2,
            "OLB": 2, "ILB": 2, "CB": 3, "FS": 1, "SS": 1}
# m1's contract asks for 3 linebackers; m2 keeps 2 ILB and 2 OLB so both 4-3 and 3-4 books find starters.
LB_MINIMUM = 3
FAMILY = {"QB": "QB", "K": "KP", "P": "KP", "WR": "REC", "TE": "REC", "HB": "RB", "FB": "RB", "T": "OL", "G": "OL",
          "C": "OL", "DE": "DL", "DT": "DL", "OLB": "LB", "ILB": "LB", "CB": "DB", "FS": "DB", "SS": "DB"}
# Donor order when a retail minimum is short (a documented role fill, recorded per player).
DONORS = {"FB": ("HB", "TE"), "HB": ("FB", "WR"), "TE": ("FB", "T"), "WR": ("TE", "CB", "HB"),
          "T": ("G", "C"), "G": ("T", "C"), "C": ("G", "T"), "DE": ("DT", "OLB"), "DT": ("DE",),
          "OLB": ("ILB", "DE", "SS"), "ILB": ("OLB",), "CB": ("FS", "SS"), "FS": ("SS", "CB"), "SS": ("FS", "CB"),
          "QB": ("WR", "HB"), "K": ("P",), "P": ("K",)}
# nflverse team code -> retail identity abbreviation (the m1 contract: retail identity abbreviations only).
IDENTITY = {"ARI": "ARZ", "ATL": "ATL", "BAL": "BAL", "BUF": "BUF", "CAR": "CAR", "CHI": "CHI", "CIN": "CIN",
            "CLE": "CLE", "DAL": "DAL", "DEN": "DEN", "DET": "DET", "GB": "GB", "HOU": "HOU", "IND": "IND",
            "JAX": "JAX", "KC": "KC", "LA": "STL", "STL": "STL", "LAR": "STL", "LAC": "SD", "SD": "SD", "LV": "OAK",
            "OAK": "OAK", "MIA": "MIA", "MIN": "MIN", "NE": "NE", "NO": "NO", "NYG": "NYG", "NYJ": "NYJ",
            "PHI": "PHI", "PIT": "PIT", "SEA": "SEA", "SF": "SF", "TB": "TB", "TEN": "TEN", "WAS": "WAS"}
# The same club under the codes different nflverse files and eras use (pbp uses the current code everywhere).
CODE_ALIASES = {"ARI": {"ARI", "ARZ"}, "BAL": {"BAL", "BLT"}, "CLE": {"CLE", "CLV"}, "HOU": {"HOU", "HST"},
                "LA": {"LA", "SL", "STL", "LAR"}, "LAC": {"LAC", "SD"}, "LV": {"LV", "OAK"}}


def club_codes(club: str) -> set[str]:
    return CODE_ALIASES.get(club, {club})


# The 32 franchises: selector (2004 nickname, lower case) -> (asset code, identity abbreviation).
FRANCHISES = {"49ers": ("25", "SF"), "bears": ("05", "CHI"), "bengals": ("06", "CIN"), "bills": ("03", "BUF"),
              "broncos": ("08", "DEN"), "browns": ("30", "CLE"), "buccaneers": ("27", "TB"),
              "cardinals": ("00", "ARZ"), "chargers": ("24", "SD"), "chiefs": ("13", "KC"), "colts": ("11", "IND"),
              "cowboys": ("07", "DAL"), "dolphins": ("14", "MIA"), "eagles": ("21", "PHI"), "falcons": ("01", "ATL"),
              "giants": ("18", "NYG"), "jaguars": ("12", "JAX"), "jets": ("19", "NYJ"), "lions": ("09", "DET"),
              "packers": ("10", "GB"), "panthers": ("04", "CAR"), "patriots": ("16", "NE"), "raiders": ("20", "OAK"),
              "rams": ("23", "STL"), "ravens": ("02", "BAL"), "redskins": ("29", "WAS"), "saints": ("17", "NO"),
              "seahawks": ("26", "SEA"), "steelers": ("22", "PIT"), "texans": ("37", "HOU"), "titans": ("28", "TEN"),
              "vikings": ("15", "MIN")}
# Standard-time UTC offsets of the venues used (every moment is between November and February).
UTC_OFFSET = {"AZ": -7, "ET": -5, "CT": -6, "MT": -7, "PT": -8}
TITLE_LIMIT, GOAL_RANGE, HISTORY_RANGE = 27, (46, 86), (320, 445)
DASHES = ("\u2014", "\u2013", "\u2012", "\u2015")
PARTICIPANT_COLUMNS = ("passer", "receiver", "rusher", "kicker", "punter", "interception", "sack", "half_sack_1",
                       "half_sack_2", "solo_tackle_1", "solo_tackle_2", "assist_tackle_1", "assist_tackle_2",
                       "tackle_for_loss_1", "qb_hit_1", "qb_hit_2", "pass_defense_1", "pass_defense_2",
                       "forced_fumble_player_1", "fumbled_1", "fumble_recovery_1", "punt_returner",
                       "kickoff_returner", "td", "blocked", "tackle_with_assist_1")
JERSEY_TOKEN = re.compile(r"(?<![\w-])(\d{1,2})-([A-Z][A-Za-z']*\.[A-Za-z][A-Za-z'. -]*?)(?=[ ,;)\].]|$)")


class BuildError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise BuildError(message)


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def compact_json(value, indent: int = 0, width: int = 150) -> str:
    """Deterministic JSON: a value that fits on one line stays on one line; otherwise one member per line."""
    flat = json.dumps(value, ensure_ascii=True, sort_keys=isinstance(value, dict))
    scalars = isinstance(value, list) and all(not isinstance(v, (list, dict)) for v in value)
    if not isinstance(value, (list, dict)) or scalars or len(flat) + indent <= width:
        return flat
    pad = " " * (indent + 1)
    if isinstance(value, list):
        return "[\n" + ",\n".join(pad + compact_json(v, indent + 1, width) for v in value) + "\n" + " " * indent + "]"
    return "{\n" + ",\n".join(pad + json.dumps(k) + ": " + compact_json(value[k], indent + 1, width)
                               for k in sorted(value)) + "\n" + " " * indent + "}"


def ascii_name(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.replace("\u2019", "'").split())


def fit_name(text: str) -> tuple[str, bool]:
    """A name the 15-character buffer accepts. Hyphenated names keep the first part and the next initial."""
    text = ascii_name(text)
    text = "".join(c for c in text if c.isalnum() or c in " '-.")
    if len(text) <= 15:
        return text, False
    if "-" in text:
        head, tail = text.split("-", 1)
        candidate = f"{head}-{tail[0]}."
        if len(candidate) <= 15:
            return candidate, True
    if " " in text:
        parts = text.split(" ")
        candidate = " ".join(parts[:-1])[:13].rstrip() + " " + parts[-1][0] + "."
        if len(candidate) <= 15:
            return candidate, True
    return text[:14] + ".", True


# ------------------------------------------------------------------------------------------ inputs
class Inputs:
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.used: dict[str, str] = {}
        self._cache: dict = {}

    def path(self, name: str) -> Path:
        path = self.folder / name
        require(path.is_file(), f"missing input {path}")
        if name not in self.used:
            self.used[name] = sha_file(path)
        return path

    def exists(self, name: str) -> bool:
        return (self.folder / name).is_file()

    def rows(self, name: str) -> list[dict]:
        if name not in self._cache:
            self._cache[name] = rm.read_csv(self.path(name))
        return self._cache[name]

    def pbp(self, season: int, game_ids: set[str]) -> dict[str, list[dict]]:
        key = ("pbp", season)
        got = self._cache.setdefault(key, {})
        missing = set(game_ids) - set(got)
        if missing:
            with io.TextIOWrapper(gzip.open(self.path(f"play_by_play_{season}.csv.gz"), "rb"), encoding="utf-8",
                                  newline="") as handle:
                for row in csv.DictReader(handle):
                    if row["game_id"] in missing:
                        got.setdefault(row["game_id"], []).append(row)
            for game_id in missing:
                require(game_id in got, f"{game_id}: not in play_by_play_{season}")
        return {g: got[g] for g in game_ids}


# ------------------------------------------------------------------------------------------ retail
class Retail:
    """The user's retail game: main roster (reference, colleges, identities) and the historic files."""

    def __init__(self, source: Path):
        self.source = Path(source)
        with rr._outer_image()(self.source) as archive:
            entry = archive.entries[5]
            raw = archive.read(entry.virtual_offset, entry.size)
            self.document = rr.RosterDocument(raw[32:])
            self.main_sha = sha_bytes(raw[32:])
            body = raw[32:]
            self.historic = self._historic(body, archive)
        self.colleges = list(self.document.colleges)
        self.identities = collections.defaultdict(list)
        self.by_last_birth = collections.defaultdict(list)
        for team in self.document.teams[:32]:
            for player in self.document.team_players(team.index):
                birth = player.record.birth_date
                key = (ascii_name(player.first).lower(), ascii_name(player.last).lower())
                identity = {"birth": birth.isoformat() if birth else "", "ratings": player.record.ratings(),
                            "hand": player.record.values.get("hand", 1), "position": player.record.position_name,
                            "retail_name": f"{ascii_name(player.first)} {ascii_name(player.last)}"}
                self.identities[key].append(identity)
                if identity["birth"]:
                    self.by_last_birth[(key[1], identity["birth"])].append(identity)

    @staticmethod
    def _historic(body: bytes, archive) -> dict[str, dict]:
        import struct
        import zlib

        def rel(at):
            return at + struct.unpack_from("<i", body, at)[0] - 1

        def utf16(at):
            end = at
            while body[end:end + 2] != b"\0\0":
                end += 2
            return body[at:end].decode("utf-16le")
        require(struct.unpack_from("<I", body, 0x98)[0] == 75, "retail historic list must hold 75 entries")
        table = rel(0x9C)
        by_id = {e.name_id: e for e in archive.entries}
        out = {}
        for index in range(75):
            at = table + 16 * index
            year = struct.unpack_from("<H", body, at)[0]
            kit = body[at + 2]
            code = body[at + 4:at + 12].decode("utf-16le").split("\0")[0]
            selector = utf16(rel(at + 12))
            filename = f"h-{code}-{year}-{selector}-{kit}.iff"
            identity = zlib.crc32(filename.upper().encode("utf-16le")) & 0xFFFFFFFF
            entry = by_id[identity]
            raw = archive.read(entry.virtual_offset, entry.size)
            document = rr.RosterDocument(raw[32:])
            players = []
            for player in document.team_players(0):
                v = player.record.values
                players.append({"first": player.first, "last": player.last, "position": player.record.position_name,
                                "depth_rank": v["depth_rank"], "depth_side": v["depth_side"], "jersey": v["jersey"],
                                "ratings": player.record.ratings()})
            out[filename] = {"selector": selector, "year": year, "kit": kit, "code": code, "players": players}
        return out

    def anchor(self, first: str, last: str, birth_date: str, position: str | None = None):
        """The same player in the retail 2004 rosters: exact name and birth date; or, when the name is unique there,
        the same position family and a birth year within three years (2K's own birth dates are sometimes wrong:
        Champ Bailey is 1980-02-14 in the retail roster, 1978-06-22 in reality); or the same last name, the exact
        birth date and the same position family under another first name (2K lists Ed Reed as Edward Reed)."""
        candidates = self.identities.get((first.lower(), last.lower()), [])
        exact = [h for h in candidates if h["birth"] == birth_date]
        if len(exact) == 1:
            return exact[0]
        if len(candidates) == 1 and position and birth_date[:4].isdigit() and candidates[0]["birth"][:4].isdigit():
            hit = candidates[0]
            if FAMILY.get(hit["position"]) == FAMILY.get(position) and abs(int(hit["birth"][:4]) - int(birth_date[:4])) <= 3:
                return {**hit, "loose": True}
        if position and birth_date:
            alias = [h for h in self.by_last_birth.get((last.lower(), birth_date), [])
                     if FAMILY.get(h["position"]) == FAMILY.get(position)]
            if len(alias) == 1:
                return {**alias[0], "alias": True}
        return None

    def college(self, name: str) -> str:
        aliases = {"LSU": "Louisiana State", "USC": "USC", "Southern California": "USC", "Miami (FL)": "Miami (FL)",
                   "Mississippi": "Mississippi", "Ole Miss": "Mississippi", "Central Florida": "Central Florida",
                   "UCF": "Central Florida", "BYU": "Brigham Young", "TCU": "Texas Christian", "SMU": "Southern Methodist",
                   "UCLA": "UCLA", "Pittsburgh": "Pittsburgh", "Pitt": "Pittsburgh", "N.C. State": "North Carolina St",
                   "North Carolina State": "North Carolina St", "Penn St.": "Penn State", "Ohio St.": "Ohio State",
                   "Michigan St.": "Michigan State", "Florida St.": "Florida State", "Oklahoma St.": "Oklahoma State",
                   "Kansas St.": "Kansas State", "Iowa St.": "Iowa State", "Oregon St.": "Oregon State",
                   "Washington St.": "Washington State", "Arizona St.": "Arizona State", "Mississippi St.": "Mississippi State",
                   "Boise St.": "Boise State", "Fresno St.": "Fresno State", "San Diego St.": "San Diego State",
                   "Colorado St.": "Colorado State"}
        name = ascii_name(name or "")
        for candidate in (name, aliases.get(name, "")):
            if candidate and self.colleges.count(candidate) == 1:
                return candidate
        return ""


# ------------------------------------------------------------------------------------------ moments
def clock_text(value: str) -> str:
    minutes, seconds = value.split(":")
    return f"{int(minutes)}:{int(seconds):02d}"


def weather_words(roof: str, weather: str, override: dict) -> tuple[str, int]:
    if "weather" in override:
        return override["weather"], int(override["temperature"])
    text = (weather or "").lower()
    if roof in ("dome", "closed"):
        return "clear", 70
    temp = None
    match = re.search(r"temp:\s*(-?\d+)", text)
    if match:
        temp = int(match.group(1))
    require(temp is not None or "temperature" in override, "no temperature in the source; give one in the spec")
    temp = int(override.get("temperature", temp))
    if "snow" in text:
        return ("heavy snow" if "heavy" in text else "flurries"), min(temp, 31)
    if "rain" in text or "shower" in text:
        return ("heavy rain" if "heavy" in text else "light rain"), max(temp, 33)
    return "clear", temp


def time_words(utc_text: str, zone: str, override: dict) -> str:
    if "time_of_day" in override:
        return override["time_of_day"]
    require(bool(utc_text), "no wall-clock time in the source; give time_of_day in the spec")
    moment = dt.datetime.strptime(utc_text[:19], "%Y-%m-%dT%H:%M:%S") + dt.timedelta(hours=UTC_OFFSET[zone])
    return "night" if moment.hour >= 17 or moment.hour < 5 else "afternoon" if moment.hour >= 14 else "day"


def ball_on(yrdln: str, teams: dict) -> str:
    yrdln = (yrdln or "").strip()
    if yrdln in ("50", "MID 50") or yrdln.endswith(" 50"):
        return "50"
    side, yard = yrdln.split()
    require(1 <= int(yard) <= 49, f"bad yard line {yrdln}")
    return f"{IDENTITY[side]} {int(yard)}"


def moment_from_pbp(spec: dict, rows: list[dict], teams: dict) -> dict:
    by_id = {int(float(r["play_id"])): i for i, r in enumerate(rows)}
    require(spec["start_play_id"] in by_id, f"{spec['id']}: play {spec['start_play_id']} not in {spec['game_id']}")
    i = by_id[spec["start_play_id"]]
    row = rows[i]
    home, away = row["home_team"], row["away_team"]
    require({IDENTITY[home], IDENTITY[away]} == {teams[spec["home"]]["abbreviation"], teams[spec["away"]]["abbreviation"]},
            f"{spec['id']}: team keys do not match the game")
    kickoff = row["play_type"] == "kickoff"
    # nflverse puts the receiving team in posteam on a kickoff; the retail convention stores the kicking team
    offense = row["defteam"] if kickoff else row["posteam"]
    require(offense in (home, away), f"{spec['id']}: start play has no offense")
    side = "home" if offense == home else "away"
    other = "away" if side == "home" else "home"
    own, opp = (row["defteam_score"], row["posteam_score"]) if kickoff else (row["posteam_score"], row["defteam_score"])
    score = {side: int(float(own)), other: int(float(opp))}
    prev = rows[i - 1] if i > 0 else None
    half_start = prev is None or (prev["qtr"] != row["qtr"] and row["qtr"] in ("3", "5"))
    if half_start:
        timeouts = {"home": 3, "away": 3}
    else:
        timeouts = {"home": int(float(prev["home_timeouts_remaining"])), "away": int(float(prev["away_timeouts_remaining"]))}
    final = {"away": int(rows[-1]["away_score"]), "home": int(rows[-1]["home_score"])}
    down = 0 if kickoff else int(float(row["down"]))
    distance = 10 if kickoff else int(float(row["ydstogo"]))
    spot = f"{IDENTITY[offense]} 30" if kickoff else ball_on(row["yrdln"], teams)
    weather, temperature = weather_words(row["roof"], row["weather"] or f"temp: {row['temp']}", spec.get("conditions", {}))
    return {"possession": side, "score_now": {"away": score["away"], "home": score["home"]}, "final_score": final,
            "quarter": int(row["qtr"]), "clock": clock_text(row["time"]), "down": down, "distance": distance,
            "ball_on": spot, "timeouts": {"away": timeouts["away"], "home": timeouts["home"]},
            "weather": weather, "time_of_day": time_words(row["time_of_day"], spec["zone"], spec.get("conditions", {})),
            "temperature": temperature, "stadium": spec.get("stadium") or row["game_stadium"] or row["stadium"],
            "nflverse": {"game_id": spec["game_id"], "play_id": spec["start_play_id"], "season": int(row["season"]),
                         "season_type": row["season_type"], "week": int(row["week"]), "roof": row["roof"],
                         "source_weather": row["weather"], "source_temp": row["temp"]}}


def check_text(moment: dict) -> None:
    for field in ("title", "date", "history", "goal", "stadium_note"):
        value = moment.get(field, "")
        require(isinstance(value, str), f"{moment['id']}: {field} must be text")
        require(value.isascii(), f"{moment['id']}: {field} must be plain ASCII")
        require(not any(d in value for d in DASHES), f"{moment['id']}: {field} has a long dash")
    require(moment["title"] == moment["title"].upper() and 1 <= len(moment["title"]) <= TITLE_LIMIT,
            f"{moment['id']}: title must be upper case, 27 characters or fewer")
    require(HISTORY_RANGE[0] <= len(moment["history"]) <= HISTORY_RANGE[1], f"{moment['id']}: history is {len(moment['history'])} characters")
    require(GOAL_RANGE[0] <= len(moment["goal"]) <= GOAL_RANGE[1], f"{moment['id']}: goal is {len(moment['goal'])} characters")
    parsed = dt.datetime.strptime(moment["date"], "%B %d, %Y")
    require(moment["date"] == f"{parsed:%B} {parsed.day}, {parsed.year}", f"{moment['id']}: date style")


# ------------------------------------------------------------------------------------------ teams
DEPTH_SIDES = {  # depth-chart position -> (2K5 position, side: 0 left, 1 right, None no side)
    "QB": ("QB", None), "RB": ("HB", None), "HB": ("HB", None), "TB": ("HB", None), "FB": ("FB", None),
    "WR": ("WR", None), "LWR": ("WR", 0), "RWR": ("WR", 1), "SWR": ("WR", None), "SE": ("WR", 0), "FL": ("WR", 1),
    "TE": ("TE", None), "LTE": ("TE", None), "RTE": ("TE", None),
    "LT": ("T", 0), "RT": ("T", 1), "T": ("T", None), "LG": ("G", 0), "RG": ("G", 1), "G": ("G", None), "C": ("C", None),
    "LE": ("DE", 0), "LDE": ("DE", 0), "RE": ("DE", 1), "RDE": ("DE", 1), "DE": ("DE", None),
    "LDT": ("DT", 0), "RDT": ("DT", 1), "DT": ("DT", None), "NT": ("DT", None),
    "SLB": ("OLB", 0), "LOLB": ("OLB", 0), "LLB": ("OLB", 0), "WLB": ("OLB", 1), "ROLB": ("OLB", 1), "RLB": ("OLB", 1),
    "OLB": ("OLB", None), "MLB": ("ILB", None), "LILB": ("ILB", 0), "RILB": ("ILB", 1), "ILB": ("ILB", None),
    "MIKE": ("ILB", None), "LB": ("OLB", None),
    "LCB": ("CB", 0), "RCB": ("CB", 1), "CB": ("CB", None), "NB": ("CB", None), "NCB": ("CB", None), "DB": ("CB", None),
    "FS": ("FS", None), "SS": ("SS", None), "S": ("SS", None), "K": ("K", None), "PK": ("K", None), "P": ("P", None),
    "EDGE": ("DE", None),
}
# Generic depth-chart slots: the player's own roster position (the depth chart's "position" column) decides.
GENERIC_SLOTS = {"LB": {"ILB": "ILB", "MLB": "ILB", "OLB": "OLB"}, "S": {"FS": "FS", "SS": "SS"},
                 "DB": {"CB": "CB", "FS": "FS", "SS": "SS"}}


DEFENSE_SLOTS = {"LT": ("DT", 0), "RT": ("DT", 1), "T": ("DT", None)}   # defensive tackles on some charts (2009 IND)
DL_SLOTS = {"LDT", "RDT", "DT", "LT", "RT", "T", "LE", "RE", "LDE", "RDE", "DE"}
LB_SLOTS = {"SLB", "WLB", "LOLB", "ROLB", "LLB", "RLB", "OLB", "MLB", "LILB", "RILB", "ILB", "MIKE", "LB"}


def resolve_slot(slot: str, roster_position: str, weight, formation: str = "", three_four: bool = False
                 ) -> tuple[str, int | None]:
    """2K5 position and side for a depth-chart slot.

    Defensive LT/RT are tackles; in a 3-4 front (an NT listed first) every other line slot is an end (DE),
    whatever the chart calls it (2011 SF lists its ends as LDT/RDT); an RB slot held by a fullback stays FB.
    """
    if formation == "Defense" and slot in DEFENSE_SLOTS:
        position, side = DEFENSE_SLOTS[slot]
    else:
        position, side = DEPTH_SIDES[slot]
    if formation == "Defense" and three_four and slot in DL_SLOTS:
        return "DE", side
    if slot in ("RB", "HB", "TB") and (roster_position or "").upper() == "FB":
        return "FB", None
    if slot in LB_SLOTS:
        # SLB/WLB/MLB name a role, not inside or outside in a 3-4: the player's own roster position decides
        own = (roster_position or "").upper()
        if own in ("ILB", "MLB"):
            return "ILB", side if position == "ILB" else None
        if own in ("OLB", "DE"):
            return "OLB", side if position == "OLB" else None
    if slot in GENERIC_SLOTS:
        mapped = GENERIC_SLOTS[slot].get((roster_position or "").upper())
        if mapped:
            return mapped, None
        if slot in ("S", "DB"):
            w = float(weight or 0)
            return ("CB" if slot == "DB" and w < 200 else "FS" if w < 208 else "SS"), None
    return position, side


def depth_chart_for(inputs: Inputs, season: int, club: str, week: int) -> dict[str, dict]:
    """gsis id -> the player's first offense/defense listing (or K/P) in that week's depth chart."""
    if season < 2001:
        return {}
    name = f"depth_charts_{season}.csv"
    out: dict[str, dict] = {}
    order = 0
    for row in inputs.rows(name):
        if row.get("club_code") not in club_codes(club) or str(row.get("week")) != str(week):
            continue
        formation = row.get("formation", "")
        position = (row.get("depth_position") or "").upper()
        if position not in DEPTH_SIDES:
            continue
        if formation == "Special Teams" and position not in ("K", "PK", "P"):
            continue
        pid = row.get("gsis_id", "")
        rank = int(row.get("depth_team") or 9)
        order += 1
        entry = {"depth_position": position, "rank": rank, "order": order, "formation": formation,
                 "roster_position": row.get("position", "")}
        old = out.get(pid)
        if old is None or (rank, order) < (old["rank"], old["order"]):
            out[pid] = entry
    # a 3-4 front lists a nose tackle and exactly three linemen first; a 4-3 that calls its tackle "NT" lists four
    starters_dl = [e for e in out.values() if e["rank"] == 1 and e["formation"] == "Defense"
                   and (e["depth_position"] in DL_SLOTS or e["depth_position"] == "NT")]
    three_four = any(e["depth_position"] == "NT" for e in starters_dl) and len(starters_dl) == 3
    for e in out.values():
        e["three_four"] = three_four
    return out


def roster_pool(inputs: Inputs, team_spec: dict) -> tuple[list[dict], str]:
    season, club, week = team_spec["season"], team_spec["nflverse"], team_spec["week"]
    keep_weekly = {"ACT", "INA"}
    if season >= 2002 and inputs.exists(f"roster_weekly_{season}.csv"):
        rows = [r for r in inputs.rows(f"roster_weekly_{season}.csv")
                if r["team"] in club_codes(club) and str(r["week"]) == str(week) and r["status"] in keep_weekly]
        require(rows, f"{team_spec['key']}: no weekly roster rows for {club} week {week}")
        return rows, f"roster_weekly_{season}.csv week {week} (ACT and INA)"
    rows = [r for r in inputs.rows(f"roster_{season}.csv") if r["team"] in club_codes(club) and r["status"] == "ACT"]
    require(rows, f"{team_spec['key']}: no season roster rows")
    return rows, f"roster_{season}.csv (ACT)"


def pbp_jerseys(rows: list[dict], club: str) -> tuple[dict[str, int], set[str]]:
    """Jersey numbers the play-by-play prints for this club, keyed by player id; and the ids who took part."""
    jerseys: dict[str, int] = {}
    played: set[str] = set()
    for row in rows:
        names = {}
        for column in PARTICIPANT_COLUMNS:
            pid, name = row.get(f"{column}_player_id", ""), row.get(f"{column}_player_name", "")
            team = row.get(f"{column}_team") or ""
            if column in ("passer", "receiver", "rusher", "kicker", "punter", "fumbled_1", "td"):
                team = team or (row["posteam"] if column not in ("td",) else "")
            if column in ("interception", "sack", "half_sack_1", "half_sack_2", "qb_hit_1", "qb_hit_2",
                          "pass_defense_1", "pass_defense_2", "tackle_for_loss_1"):
                team = team or row["defteam"]
            if pid and name:
                names.setdefault(name.replace(" ", ""), set()).add((pid, team))
                if team == club:
                    played.add(pid)
        for number, name in JERSEY_TOKEN.findall(row.get("desc", "")):
            hits = {pid for pid, team in names.get(name.replace(" ", ""), ()) if team == club}
            if len(hits) == 1:
                pid = hits.pop()
                jerseys.setdefault(pid, int(number))
    return jerseys, played


def season_value(stats: rm.SeasonStats, pid: str, position: str) -> float:
    return stats.production_for(pid, position)["value"] if stats else 0.0


def build_team(key: str, spec: dict, ctx) -> tuple[list[dict], dict]:
    inputs, retail = ctx["inputs"], ctx["retail"]
    team_spec = dict(spec, key=key)
    season, club = spec["season"], spec["nflverse"]
    pool, pool_source = roster_pool(inputs, team_spec)
    depth = depth_chart_for(inputs, season, spec.get("depth_club", club), spec["week"])
    if spec.get("starters"):
        # a sourced starting lineup (seasons without nflverse depth charts), in the spec with its source
        names = {ascii_name(r["full_name"]): (r.get("gsis_id") or f"name:{r['full_name']}|{r['birth_date']}") for r in pool}
        for order, (position, name) in enumerate(spec["starters"]["lineup"]):
            require(name in names, f"{key}: starter {name} is not in the roster pool")
            require(position in DEPTH_SIDES, f"{key}: unknown lineup position {position}")
            depth[names[name]] = {"depth_position": position, "rank": 1, "order": order, "formation": "lineup"}
    if spec.get("game_id"):
        game_rows = inputs.pbp(season, {spec["game_id"]})[spec["game_id"]]
        jerseys, played = pbp_jerseys(game_rows, club)
    else:
        jerseys, played = {}, set()
    stats = ctx["season_stats"](season)
    by_id = {}
    for row in pool:
        pid = row.get("gsis_id") or f"name:{row['full_name']}|{row['birth_date']}"
        by_id.setdefault(pid, row)
    season_rows = {(r.get("gsis_id") or f"name:{r['full_name']}|{r['birth_date']}"): r
                   for r in inputs.rows(f"roster_{season}.csv") if r["team"] in club_codes(club)}
    added = []
    for pid in sorted(played - set(by_id)):
        if pid in season_rows:
            by_id[pid] = season_rows[pid]
            added.append(pid)
    for name in spec.get("featured", []):
        hits = [pid for pid, r in by_id.items() if ascii_name(r["full_name"]) == name]
        if not hits:
            hits = [pid for pid, r in season_rows.items() if ascii_name(r["full_name"]) == name]
            require(len(hits) == 1, f"{key}: featured player {name} is not on the {season} roster")
            by_id[hits[0]] = season_rows[hits[0]]
            added.append(hits[0])
    honor_names = (spec.get("honors") or {}).get("players", {})
    honors = {pid: honor_names[ascii_name(r["full_name"])] for pid, r in by_id.items() if ascii_name(r["full_name"]) in honor_names}
    require(len(honors) == len(honor_names), f"{key}: an honored player is not in the pool")
    ctx["honors"] = honors
    players = []
    for pid, row in by_id.items():
        chart = depth.get(pid)
        if chart:
            position, side = resolve_slot(chart["depth_position"], chart.get("roster_position", ""), row.get("weight"),
                                          chart.get("formation", ""), chart.get("three_four", False))
            position_source = (f"starting lineup ({spec['starters']['source']}): {chart['depth_position']}"
                               if chart.get("formation") == "lineup" else
                               f"depth chart week {spec['week']}: {chart['depth_position']} {chart['rank']}")
        else:
            position, side = rm.map_position(row["position"], row.get("depth_chart_position", ""), row.get("weight")), None
            chart = {"rank": 9, "order": 10**6}
            position_source = f"roster position {row['position']}/{row.get('depth_chart_position', '')}"
        override = spec.get("positions", {}).get(ascii_name(row["full_name"]))
        if override:
            position, side, position_source = override, None, "spec override (documented in the spec)"
        order = chart["order"] - (10**5 if pid in honors and chart["rank"] >= 9 else 0)
        players.append({"pid": pid, "row": row, "position": position, "side": side, "rank": chart["rank"],
                        "order": order, "position_source": position_source,
                        "in_game": pid in played, "added": pid in added, "role_fill": None})
    # 53 exactly: drop the least-used players who neither played nor sit on the depth chart; add from the season roster
    def keep_score(p):
        return (p["in_game"] or ascii_name(p["row"]["full_name"]) in spec.get("featured", []), p["rank"] < 9,
                p["row"].get("status") == "ACT", season_value(stats, p["pid"], p["position"]), p["pid"])
    while len(players) > 53:
        counts = collections.Counter(p["position"] for p in players)
        lb = counts["OLB"] + counts["ILB"]
        removable = [p for p in players if counts[p["position"]] > MINIMUMS.get(p["position"], 0)
                     and not (p["position"] in ("OLB", "ILB") and lb <= LB_MINIMUM)]
        victim = min(removable, key=keep_score)
        players.remove(victim)
    if len(players) < 53:
        extra = [(pid, r) for pid, r in season_rows.items() if pid not in {p["pid"] for p in players}
                 and r["status"] in ("ACT", "RES", "INA", "PUP")]
        scored = []
        for pid, r in extra:
            position = rm.map_position(r["position"], r.get("depth_chart_position", ""), r.get("weight"))
            scored.append((-season_value(stats, pid, position), pid, r, position))
        for _, pid, r, position in sorted(scored)[:53 - len(players)]:
            players.append({"pid": pid, "row": r, "position": position, "side": None, "rank": 9, "order": 10**6,
                            "position_source": f"season roster {r['position']} (added to reach 53)",
                            "in_game": False, "added": True, "role_fill": None})
    require(len(players) == 53, f"{key}: {len(players)} players, need 53")
    fill_minimums(players, stats)
    order_depth(players, stats)
    rows, provenance = finish_rows(key, spec, players, jerseys, stats, ctx)
    info = {"pool": pool_source, "pbp_game": spec["game_id"],
            "scheme": "3-4" if any(e.get("three_four") for e in depth.values()) else "4-3" if depth else "unknown", "jerseys_from_pbp": sum(1 for p in provenance if p["jersey_source"] == "pbp"),
            "speed_sources": dict(sorted(collections.Counter(speed_source(p["ratings_basis"]) for p in provenance).items())),
            "players": provenance}
    return rows, info


def fill_minimums(players: list[dict], stats) -> None:
    for position, need in sorted(MINIMUMS.items(), key=lambda kv: POSITION_ORDER.index(kv[0])):
        while sum(1 for p in players if p["position"] == position) < need:
            counts = collections.Counter(p["position"] for p in players)
            donors = [p for p in players if p["position"] in DONORS[position]
                      and counts[p["position"]] > MINIMUMS.get(p["position"], 0)
                      and not (p["position"] in ("OLB", "ILB") and counts["OLB"] + counts["ILB"] <= LB_MINIMUM)]
            require(donors, f"no donor for {position}")
            rank_of_donor = {d: i for i, d in enumerate(DONORS[position])}

            def cost(p):
                weight = float(p["row"].get("weight") or 0)
                heavy = -weight if position in ("FB", "TE", "T", "G", "C", "DT", "DE") else weight
                return (rank_of_donor[p["position"]], -p["rank"], heavy, p["pid"])
            chosen = min(donors, key=cost)
            chosen["role_fill"] = f"{chosen['position']} -> {position} (retail minimum)"
            chosen["position"] = position
            chosen["side"] = None
            chosen["rank"] = 9
    lb = [p for p in players if p["position"] in ("OLB", "ILB")]
    require(len(lb) >= LB_MINIMUM, "fewer than three linebackers")


def order_depth(players: list[dict], stats) -> None:
    """depth: 1-based inside the position; for sided positions left starter, right starter, left 2nd, right 2nd."""
    groups = collections.defaultdict(list)
    for p in players:
        groups[p["position"]].append(p)
    for position, group in groups.items():
        group.sort(key=lambda p: (p["rank"], p["order"] if p["order"] < 0 else 0,
                                  0 if p["in_game"] or p["rank"] < 9 else 1, -season_value(stats, p["pid"], position),
                                  -int(float(p["row"].get("years_exp") or 0)), p["order"], p["pid"]))
        sided = position in ("T", "G", "DE", "DT", "OLB", "ILB", "CB", "WR")
        if not sided:
            for i, p in enumerate(group, 1):
                p["depth"] = i
            continue
        # pair by rank: within one depth rank, left before right before unsided (listing order breaks ties)
        ordered = []
        for rank in sorted({p["rank"] for p in group}):
            tier = [p for p in group if p["rank"] == rank]
            # explicit left/right first; players listed without a side (three WRs at rank 1, two "S") by production
            tier.sort(key=lambda p: (0 if p["side"] == 0 else 1 if p["side"] == 1 else 2,
                                     p["order"] if p["order"] < 0 else 0, 0 if p["in_game"] or rank < 9 else 1,
                                     -season_value(stats, p["pid"], position), p["order"], p["pid"]))
            ordered.extend(tier)
        for i, p in enumerate(ordered, 1):
            p["depth"] = i


def finish_rows(key, spec, players, jerseys, stats, ctx):
    retail, inputs = ctx["retail"], ctx["inputs"]
    players.sort(key=lambda p: (POSITION_ORDER.index(p["position"]), p["depth"]))
    used_numbers = collections.Counter()
    out_rows, provenance = [], []
    same_season = spec.get("retail_same_season")
    for p in players:
        row = p["row"]
        pbp_number = jerseys.get(p["pid"])
        listed = int(float(row["jersey_number"])) if row.get("jersey_number") not in (None, "", "NA") else None
        listed = listed if listed is not None and 1 <= listed <= 99 else None
        p["jersey"], p["jersey_source"] = (pbp_number, "pbp") if pbp_number else (listed, "roster") if listed else (None, "none")
    for p in players:
        if p["jersey"] is not None:
            used_numbers[p["jersey"]] += 1
    alternatives = ctx["season_numbers"](spec["season"], spec["nflverse"])
    for p in sorted(players, key=lambda q: (q["jersey_source"] != "pbp", q["depth"], q["pid"])):
        if p["jersey"] is not None and used_numbers[p["jersey"]] == 1:
            continue
        if p["jersey"] is not None and p["jersey_source"] == "pbp":
            continue
        if p["jersey"] is not None:
            used_numbers[p["jersey"]] -= 1
        other = [n for n in alternatives.get(p["pid"], ()) if used_numbers[n] == 0]
        if other:
            p["jersey"], p["jersey_source"] = other[0], "another week of the same season"
        else:
            free = next(n for n in range(1, 100) if used_numbers[n] == 0)
            p["jersey"], p["jersey_source"] = free, "invented_free_number"
        used_numbers[p["jersey"]] += 1
    for p in players:
        row = p["row"]
        full = ascii_name(row["full_name"])
        last = ascii_name(row["last_name"])
        first = full[:-len(last)].strip() if full.lower().endswith(" " + last.lower()) else full.partition(" ")[0]
        if not full.lower().endswith(" " + last.lower()):
            last = full.partition(" ")[2] or last
        display = ctx["display_names"].get(full)
        if display:
            first, last = display
        first, short_first = fit_name(first)
        last, short_last = fit_name(last)
        rr.validate_name(first)
        rr.validate_name(last)
        p["first"], p["last"] = first, last
        p["name_note"] = ("shortened to fit 15 characters" if (short_first or short_last) else
                          "display name from the spec (the name the player went by)" if display else "")
    # ratings: 2K's own retail file for the same team-season (by name, else position and depth), or the model
    if same_season:
        carry_retail_ratings(players, retail.historic[same_season])
        # players with no depth-chart or lineup rank: order them by the strength of 2K's slot they received
        for p in players:
            if p["rank"] >= 9:
                p["order"] = 10**6 - round(10 * slot_strength(p["position"], p["ratings"]))
        order_depth(players, stats)
        players.sort(key=lambda p: (POSITION_ORDER.index(p["position"]), p["depth"]))
    else:
        rows_for_model = []
        for p in players:
            r = p["row"]
            rows_for_model.append({"position": p["position"], "gsis_id": p["pid"] if not p["pid"].startswith("name:") else "",
                                   "weight": r.get("weight"), "birth_date": r.get("birth_date"),
                                   "years_pro": r.get("years_exp"), "draft_number": r.get("draft_number"),
                                   "depth": p["depth"], "first": p["first"], "last": p["last"]})
        reference = ctx["reference"]
        for p, model_row in zip(players, rows_for_model):
            hit = retail.anchor(ascii_name(p["first"]), ascii_name(p["last"]), p["row"].get("birth_date", ""), p["position"])
            anchor = hit["ratings"] if hit else None
            ratings, basis = rm.rate_player(model_row, stats, reference, anchor=anchor, honors=ctx.get("honors"))
            p["ratings"], p["rating_basis"] = ratings, basis
            p["retail_identity"] = (None if not hit else f"alias of retail {hit['retail_name']}" if hit.get("alias")
                                    else f"loose match of retail {hit['retail_name']}" if hit.get("loose") else "exact")
    for i, p in enumerate(players):
        r = p["row"]
        hit = retail.anchor(ascii_name(p["first"]), ascii_name(p["last"]), r.get("birth_date", ""), p["position"])
        lefty = (hit is not None and hit["hand"] == 0) or ascii_name(r["full_name"]) in ctx["left_handed"]
        hand = "Left" if lefty and p["position"] in ("QB", "K", "P") else "Right"
        college = retail.college(r.get("college", ""))
        weight = int(float(r.get("weight") or 0)) or 200
        height = int(float(r.get("height") or 0)) or 72
        years = max(0, min(31, int(float(r.get("years_exp") or 0))))
        values = {"pool": "primary", "index": i, "first": p["first"], "last": p["last"], "position": p["position"],
                  "jersey": p["jersey"], "college": college, **{k: p["ratings"][k] for k in rr.RATING_BYTE_ORDER},
                  "depth": p["depth"], "height": height, "weight": max(150, min(405, weight)),
                  "birth_date": r.get("birth_date") or "", "years_pro": years, "hand": hand}
        out_rows.append(values)
        provenance.append({"index": i, "gsis_id": p["pid"] if not p["pid"].startswith("name:") else "",
                           "source_name": ascii_name(r["full_name"]), "source_status": r.get("status", ""),
                           "position_source": p["position_source"], "role_fill": p["role_fill"],
                           "in_moment_game_pbp": p["in_game"], "added_from_season_roster": p["added"],
                           "jersey_source": p["jersey_source"], "name_note": p["name_note"],
                           "hand_basis": ("retail 2004 identity" if hit and hit["hand"] == 0 else "left-handed list")
                           if hand == "Left" else "default right",
                           "college_basis": "main college table" if college else "not in the table (template keeps its own)",
                           "retail_identity": p.get("retail_identity"),
                           "ratings_basis": p.get("rating_basis") or p.get("retail_slot")})
    return out_rows, provenance


def speed_source(basis) -> str:
    """Where a player's speed came from (the ratings model's ``speed_source``, or 2K's own retail slot)."""
    if isinstance(basis, dict) and basis.get("speed_source"):
        return basis["speed_source"]
    return "retail_same_season"


def slot_strength(position: str, ratings: dict) -> float:
    """The studio's documented OVR estimate (nfl2k5_roster_records.OVERALL_WEIGHTS) of a retail slot."""
    weights = rr.OVERALL_WEIGHTS.get(position) or {}
    total = sum(weights.values())
    return sum(ratings[k] * w for k, w in weights.items()) / total if total else 0.0


def carry_retail_ratings(players: list[dict], historic: dict) -> None:
    """2K's own ratings for this exact team-season, from the retail historic file.

    Order of evidence: (1) the slot 2K named after the player; (2) a placeholder slot that carries the player's
    jersey number, same position family; (3) the remaining slots of the same position, strongest (studio OVR
    estimate) to the player with the best depth; (4) the same family; (5) a compatible slot reused (a copy of the
    weakest same-position slot: such a player is a reserve beyond 2K's slot count). A slot of another family is never used. The retail (rank, side)
    word is the game's left/right chain encoding, not a plain depth order, so slot strength stands in for it.
    """
    nickname = None
    slots = list(enumerate(historic["players"]))
    taken: dict[int, int] = {}
    placeholders = {i for i, s in slots if s["first"].lower() == historic["selector"].lower()}

    def take(p, i, slot, basis):
        taken[i] = taken.get(i, 0) + 1
        ratings = dict(slot["ratings"])
        if slot["position"] != p["position"]:
            ratings.update(rm.style_bytes(p["position"], float(p["row"].get("weight") or 200), 0.3, None))
        p["ratings"] = ratings
        p["retail_slot"] = {"slot": i, "basis": basis, "slot_position": slot["position"],
                            "slot_name": f"{slot['first']} {slot['last']}", "slot_jersey": slot["jersey"]}
    for p in players:
        for i, slot in slots:
            if i not in taken and ascii_name(slot["first"]).lower() == p["first"].lower() and \
                    ascii_name(slot["last"]).lower() == p["last"].lower():
                take(p, i, slot, "retail slot named after the player")
                break
    for p in sorted(players, key=lambda q: (POSITION_ORDER.index(q["position"]), q["depth"])):
        if "ratings" in p:
            continue
        for i, slot in slots:
            if i not in taken and i in placeholders and slot["jersey"] == p["jersey"] and \
                    FAMILY[slot["position"]] == FAMILY[p["position"]]:
                take(p, i, slot, "retail placeholder slot with the player's jersey number")
                break
    for level in ("position", "family"):
        for p in sorted(players, key=lambda q: (POSITION_ORDER.index(q["position"]), q["depth"])):
            if "ratings" in p:
                continue
            open_slots = [(i, s) for i, s in slots if i not in taken and (
                s["position"] == p["position"] if level == "position" else FAMILY[s["position"]] == FAMILY[p["position"]])]
            if open_slots:
                i, slot = max(open_slots, key=lambda item: (slot_strength(item[1]["position"], item[1]["ratings"]), -item[0]))
                take(p, i, slot, f"strongest open retail slot of the same {level}")
    for p in players:
        if "ratings" in p:
            continue
        same = [(i, s) for i, s in slots if s["position"] == p["position"]] or \
               [(i, s) for i, s in slots if FAMILY[s["position"]] == FAMILY[p["position"]]]
        require(same, f"no retail slot of the {p['position']} family")
        # a player beyond 2K's slot count at his position is a reserve: copy the weakest compatible slot
        i, slot = min(same, key=lambda item: (slot_strength(item[1]["position"], item[1]["ratings"]), item[0]))
        take(p, i, slot, "weakest retail slot of the same position reused (copy)")
    require(all("ratings" in p for p in players), "retail slot assignment left a player without ratings")


# ------------------------------------------------------------------------------------------ build
def team_record(key: str, spec: dict, retail: Retail) -> dict:
    code, abbreviation = FRANCHISES[spec["selector"]]
    same = [f for f, h in retail.historic.items() if h["selector"] == spec["selector"] and h["year"] == spec["season"]]
    candidates = sorted((abs(h["year"] - spec["season"]), -h["year"], f) for f, h in retail.historic.items() if h["code"] == code)
    template = spec.get("template") or (candidates[0][2] if candidates else None)
    return {"selector": spec["selector"], "season": spec["season"], "asset_code": code, "nickname": spec["nickname"],
            "city": spec["city"], "abbreviation": abbreviation, "template": template,
            "retail_same_season": same[0] if same else None}


def generate(spec_path: Path, inputs_dir: Path, retail_dir: Path, out_dir: Path, forty_path: Path = FORTY_SOURCES) -> dict:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    forty_sources = rm.load_forty_sources(forty_path)
    inputs = Inputs(inputs_dir)
    retail = Retail(retail_dir)
    forty_by_name, counts = {}, collections.Counter()
    for row in inputs.rows("combine.csv"):
        if row.get("forty"):
            name = row["player_name"].lower()
            counts[name] += 1
            forty_by_name[name] = float(row["forty"])
    forty_by_name = {k: v for k, v in forty_by_name.items() if counts[k] == 1}
    reference_data = rm.build_reference(retail.document, forty_by_name=forty_by_name,
                                        source={"retail_main_roster_body_sha256": retail.main_sha,
                                                "combine": "nflverse combine.csv (CC-BY-4.0), exact-name matches"})
    reference = rm.Reference(reference_data)
    seasons: dict[int, rm.SeasonStats] = {}

    def season_stats(season: int):
        if season < 1999:
            return None
        if season not in seasons:
            kw = {"combine": inputs.path("combine.csv"), "players": inputs.path("players.csv"), "forty_sources": forty_sources}
            if inputs.exists(f"depth_charts_{season}.csv"):
                kw["depth_charts"] = inputs.path(f"depth_charts_{season}.csv")
            if inputs.exists(f"snap_counts_{season}.csv"):
                kw["snap_counts"] = inputs.path(f"snap_counts_{season}.csv")
            seasons[season] = rm.SeasonStats.from_files(season, inputs.path(f"stats_player_reg_{season}.csv.gz"),
                                                        inputs.path(f"roster_{season}.csv"), **kw)
        return seasons[season]
    def season_numbers(season: int, club: str) -> dict[str, list[int]]:
        """Every number a player wore for this club in the season's weekly rosters, most used first."""
        found = collections.defaultdict(collections.Counter)
        names = [f"roster_weekly_{season}.csv"] if inputs.exists(f"roster_weekly_{season}.csv") else []
        for name in names + [f"roster_{season}.csv"]:
            for row in inputs.rows(name):
                if row["team"] in club_codes(club) and row.get("jersey_number") not in (None, "", "NA") and row.get("gsis_id"):
                    number = int(float(row["jersey_number"]))
                    if 1 <= number <= 99:          # 0 is a missing value in old files and outside 2K5's 1..99
                        found[row["gsis_id"]][number] += 1
        return {pid: [n for n, _ in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))] for pid, c in found.items()}
    ctx = {"inputs": inputs, "retail": retail, "reference": reference, "season_stats": season_stats,
           "season_numbers": season_numbers,
           "left_handed": set(spec.get("left_handed", {}).get("names", [])),
           "display_names": {k: tuple(v) for k, v in spec.get("display_names", {}).get("names", {}).items()}}
    teams_out, manifest_teams, csv_files = {}, {}, {}
    for key in sorted(spec["teams"]):
        team_spec = spec["teams"][key]
        record = team_record(key, team_spec, retail)
        if record["retail_same_season"] and team_spec.get("ratings") != "model":
            team_spec = {**team_spec, "retail_same_season": record["retail_same_season"]}
        rows, info = build_team(key, team_spec, ctx)
        text = io.StringIO()
        writer = csv.DictWriter(text, CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        csv_files[f"{key}.csv"] = text.getvalue()
        teams_out[key] = record
        manifest_teams[key] = {**record, "nflverse_team": team_spec["nflverse"], "game_id": team_spec["game_id"],
                               "week": team_spec["week"], "ratings": ("2K's own retail ratings for this team-season"
                               if team_spec.get("retail_same_season") else f"ratings model {rm.MODEL_VERSION} on the {team_spec['season']} statistics"),
                               "csv_sha256": sha_bytes(csv_files[f"{key}.csv"].encode()), **info}
    moments = []
    for m in spec["moments"]:
        teams_known = {k: teams_out[k] for k in (m["away"], m["home"])}
        if "game_id" in m:
            rows = inputs.pbp(int(m["game_id"][:4]), {m["game_id"]})[m["game_id"]]
            situation = moment_from_pbp(m, rows, teams_known)
        else:
            situation = dict(m["situation"])
        out = {"id": m["id"], "title": m["title"], "date": m["date"], "history": m["history"], "goal": m["goal"],
               "stadium": situation.pop("stadium", None) or m["stadium"], "stadium_index": m["stadium_index"],
               "stadium_note": m.get("stadium_note", ""), "away": m["away"], "home": m["home"], "user_side": m["user_side"],
               **{k: situation[k] for k in ("possession", "score_now", "final_score", "quarter", "clock", "down",
                                             "distance", "ball_on", "timeouts", "weather", "time_of_day", "temperature")},
               "kits": m["kits"], "sources": m["sources"] + ([f"nflverse play_by_play_{situation['nflverse']['season']}: "
                                                              f"game_id {situation['nflverse']['game_id']}, play_id {situation['nflverse']['play_id']}"]
                                                             if "nflverse" in situation else []),
               "evidence": m.get("evidence", "situation read from nflverse play-by-play (PROVED OFFLINE from the source data)")}
        if m.get("notes"):
            out["notes"] = m["notes"]
        check_text(out)
        require(0 <= out["stadium_index"] <= 42, f"{m['id']}: stadium index")
        require(out["user_side"] in ("away", "home") and out["possession"] in ("away", "home"), f"{m['id']}: sides")
        moments.append(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    teams_dir = out_dir / TEAMS_DIR
    teams_dir.mkdir(parents=True, exist_ok=True)
    files = {MOMENTS_NAME: json.dumps({"schema": 1, "evidence": EVIDENCE, "moments": moments}, indent=2, ensure_ascii=True) + "\n",
             REFERENCE_NAME: compact_json(reference_data) + "\n",
             f"{TEAMS_DIR}/teams.json": json.dumps({"schema": 1, "evidence": EVIDENCE, "teams": teams_out}, indent=2, sort_keys=True) + "\n"}
    for name, text in csv_files.items():
        files[f"{TEAMS_DIR}/{name}"] = text
    manifest = {"schema": "nfl2k5.espn25.more_teams.manifest.v1", "evidence": EVIDENCE, "generator": "tools/nfl2k5_espn25_more_moments_build.py",
                "spec_sha256": sha_file(spec_path), "forty_sources_sha256": sha_file(forty_path), "ratings_model": rm.MODEL_VERSION,
                "sources": {"nflverse": {"url": "https://github.com/nflverse/nflverse-data/releases", "licence": "CC-BY-4.0",
                                         "attribution": "nflverse contributors", "files": dict(sorted(inputs.used.items()))},
                            "retail": {"main_roster_body_sha256": retail.main_sha,
                                       "note": "user-owned retail game input; not distributed"}},
                "teams": manifest_teams}
    files[f"{TEAMS_DIR}/manifest.json"] = compact_json(manifest) + "\n"
    for name, text in files.items():
        (out_dir / name).write_text(text, encoding="utf-8", newline="\n")
    return {"moments": len(moments), "teams": len(teams_out), "files": sorted(files)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--spec", type=Path, default=SPEC)
    parser.add_argument("--inputs", type=Path, default=DEFAULT_INPUTS)
    parser.add_argument("--retail", type=Path, default=DEFAULT_RETAIL)
    parser.add_argument("--out", type=Path, default=OUT_DATA)
    parser.add_argument("--forty-sources", type=Path, default=FORTY_SOURCES, help="cited 40 times (hand-curated input)")
    parser.add_argument("--check", action="store_true", help="regenerate in temporary storage and compare every byte")
    args = parser.parse_args(argv)
    if not args.check:
        print(json.dumps(generate(args.spec, args.inputs, args.retail, args.out, args.forty_sources), indent=1))
        return 0
    with tempfile.TemporaryDirectory(prefix="m2-moments-check-") as folder:
        result = generate(args.spec, args.inputs, args.retail, Path(folder), args.forty_sources)
        for name in result["files"]:
            fresh = (Path(folder) / name).read_bytes()
            shipped = args.out / name
            require(shipped.is_file() and shipped.read_bytes() == fresh, f"regeneration differs: {name}")
        shipped_csvs = {p.name for p in (args.out / TEAMS_DIR).iterdir()}
        fresh_csvs = {p.name for p in (Path(folder) / TEAMS_DIR).iterdir()}
        require(shipped_csvs == fresh_csvs, f"unexpected files in {TEAMS_DIR}: {sorted(shipped_csvs ^ fresh_csvs)}")
    print(f"all {len(result['files'])} generated files reproduce exactly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
