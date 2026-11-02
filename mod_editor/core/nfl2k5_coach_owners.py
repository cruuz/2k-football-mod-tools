"""Owner patience and the coach hiring pool for the coaching carousel (job c5-owners, beta 80). DATA + DESIGN, UNWITNESSED.

Nothing here touches the game. The carousel (job c6) fires and hires head coaches for CPU clubs at Advance to offseason;
this module is the sourced input it reads and the reference for the decision it ports to native code.

Two data files (both read through the loaders below, both checked by ``validate_*``):

* ``data/nfl2k5_owners_2026.json`` (schema ``nfl2k5_coach_owners/v1``): for each of the 32 clubs the owner (name, since
  when, how he came to own the club), the club's real head coach history since 1999 (every change, with the season
  record that preceded it), and ``fire_scale_q8``, the club's owner multiplier on the league-wide firing hazard. The
  hazard itself is a table (``model.base_permille``) fitted to the same history. Every figure is derived from pinned
  sources listed in the file's ``sources`` (nflverse ``games.csv`` at a fixed commit, a fixed Wikipedia revision for the
  owners, the repo's own sourced 2026 head coaches); nothing is a hand-set rating.
* ``data/nfl2k5_coach_pool_2026.json`` (schema ``nfl2k5_coach_pool/v1``): the real people a CPU club may hire from:
  the 2026 defensive coordinators and recent head coaches without a head coach job, each with its sources.

The decision (integers only, so the native port can match it bit for bit)::

    G   = wins + losses + ties of the season just played, by the coach being judged
    idx = ((2*wins + ties) * 17 + G) // (2*G)             # record on a 17-game scale, 0..17, rounds half up
    b   = 0 if n <= 1 else 1 if n == 2 else 2             # n = seasons with this club including the one just played
    p   = base_permille[b][idx]
    p   = (p * owner_q8 * league_q8 + 32768) >> 16        # both factors are Q8: 256 = 1.0
    p   = min(p, 1000)
    fire = (draw % 1000) < p                               # draw = any uniform 32-bit random number

Changes counted are changes of the OPENING-DAY head coach from one season to the next (a coach fired in week 12 and the
interim who finishes the year count as one change, taken against the full season's record), because that is what a game
that fires only at Advance to offseason can reproduce. The older "coach at the end of the season" count of the r2 research
is kept in ``crosscheck_r2`` for comparison.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import struct
from typing import Iterable, Mapping

OWNERS_SCHEMA = "nfl2k5_coach_owners/v1"
POOL_SCHEMA = "nfl2k5_coach_pool/v1"
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DEFAULT_OWNERS = DATA_DIR / "nfl2k5_owners_2026.json"
DEFAULT_POOL = DATA_DIR / "nfl2k5_coach_pool_2026.json"

GAMES_SCALE = 17            # record_index() puts every season on a 17-game scale
TENURE_BUCKETS = 3          # first season with the club, second, third or later
SEASON_FIRST, SEASON_LAST = 1999, 2025        # decisions are made after each of these seasons (the last picks the 2026 coach)
HEX64 = re.compile(r"^[0-9a-f]{64}$")
ASCII_NAME = re.compile(r"^[A-Za-z][A-Za-z.'\- ]*$")
CLUBS = ("ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
         "LAC", "LAR", "LV", "MIA", "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS")


class CoachOwnersError(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise CoachOwnersError(message)


# ---------------------------------------------------------------------------------------------------------------------
# The decision
# ---------------------------------------------------------------------------------------------------------------------
def record_index(wins: int, losses: int, ties: int = 0) -> int:
    """The season record on a 17-game scale (0..17), rounding half up: 8-8-1 and 9-8 both give 9; 4-12 gives 4."""
    games = wins + losses + ties
    _require(games > 0 and min(wins, losses, ties) >= 0, "a record needs at least one game and no negative counts")
    return min(GAMES_SCALE, ((2 * wins + ties) * GAMES_SCALE + games) // (2 * games))


def tenure_bucket(seasons: int) -> int:
    """0 for a first-season coach, 1 for a second-season coach, 2 for everybody else."""
    return 0 if seasons <= 1 else 1 if seasons == 2 else 2


def fire_permille(model: Mapping, owner_q8: int, wins: int, losses: int, ties: int, seasons: int) -> int:
    """Chance, in thousandths, that this owner dismisses this coach after this season (integer math, see the module text)."""
    base = model["base_permille"][tenure_bucket(seasons)][record_index(wins, losses, ties)]
    p = (base * int(owner_q8) * int(model.get("league_q8", 256)) + 32768) >> 16
    return min(p, 1000)


def decide(permille: int, draw: int) -> bool:
    """True when a uniform random integer says dismiss: ``draw % 1000 < permille``."""
    return draw % 1000 < permille


NATIVE_VERSION = 1
NATIVE_SIZE = 4 + 2 * TENURE_BUCKETS * (GAMES_SCALE + 1) + 2 * 32


def pack_native(doc: Mapping) -> bytes:
    """The decision tables as the carousel's native code reads them: little-endian u16 values,

    ``version (1), league_q8, base_permille[3][18] (row = tenure bucket), owner_q8[32]`` indexed by the club's retail team
    index (``clubs[*].team_index``, the order of the coach table in the roster). 176 bytes. ``unpack_native`` is the inverse.
    """
    model = doc["model"]
    owner_by_index = {c["team_index"]: c["fire_scale_q8"] for c in doc["clubs"]}
    values = [NATIVE_VERSION, model["league_q8"]]
    values += [v for row in model["base_permille"] for v in row]
    values += [owner_by_index[i] for i in range(32)]
    return struct.pack("<%dH" % len(values), *values)


def unpack_native(blob: bytes) -> dict:
    _require(len(blob) == NATIVE_SIZE, "a native owner table is %d bytes" % NATIVE_SIZE)
    values = struct.unpack("<%dH" % (NATIVE_SIZE // 2), blob)
    _require(values[0] == NATIVE_VERSION, "unknown native owner table version")
    per_row = GAMES_SCALE + 1
    rows = [list(values[2 + i * per_row:2 + (i + 1) * per_row]) for i in range(TENURE_BUCKETS)]
    return {"model": {"base_permille": rows, "league_q8": values[1]}, "owner_q8_by_team_index": list(values[2 + TENURE_BUCKETS * per_row:])}


class Lcg:
    """A 64-bit linear congruential generator (Knuth's MMIX constants), top 32 bits out: the same stream on every
    platform and Python version, which the stored calibration relies on. The game's own generator replaces it in the
    carousel; only the distribution matters there."""

    A = 6364136223846793005
    C = 1442695040888963407
    MASK = (1 << 64) - 1

    def __init__(self, seed: int):
        self.state = (int(seed) * 2862933555777941757 + 3037000493) & self.MASK
        for _ in range(4):
            self.u32()

    def u32(self) -> int:
        self.state = (self.state * self.A + self.C) & self.MASK
        return self.state >> 32


# ---------------------------------------------------------------------------------------------------------------------
# The league simulation used for the stored calibration (and re-run by the tests)
# ---------------------------------------------------------------------------------------------------------------------
def simulate(doc: Mapping, seed: int, replications: int, burn_in: int, seasons: int, league_q8: int | None = None) -> dict:
    """Run the firing rule on 32 simulated clubs whose season records replay real ones, and return the calibration aggregates.

    Each simulated club carries its own owner (the table's ``fire_scale_q8`` for that slot) and, per replication, replays the
    actual win-loss-tie sequence of a randomly chosen real club from a random start (``calibration.records``, 1999-2025,
    wrapping around), so the records have the real league's spread, tails and persistence without an invented talent model.
    The rule decides after every season; a fired coach is replaced by a new one (tenure 1), a kept coach gains a season.
    ``burn_in`` seasons are discarded so the measured seasons start from a settled mix of tenures. Integer math throughout.
    """
    model = dict(doc["model"])
    if league_q8 is not None:
        model["league_q8"] = int(league_q8)
    donors = [parse_records(line) for _club, line in sorted(doc["calibration"]["records"].items())]
    donors = [seq for seq in donors if len(seq) == SEASON_LAST - SEASON_FIRST + 1]       # Houston (2002 on) cannot donate
    _require(donors, "the calibration needs the real club records")
    length = len(donors[0])
    owners = [int(c["fire_scale_q8"]) for c in doc["clubs"]]
    rng = Lcg(seed)
    changes_per_offseason: list[int] = []
    fired_pcts: list[float] = []
    fired_tenures: list[int] = []
    fired_by_tenure = [0] * TENURE_BUCKETS
    seen_by_tenure = [0] * TENURE_BUCKETS
    after_winning = 0
    decisions = 0
    for _ in range(replications):
        picks = [(donors[rng.u32() % len(donors)], rng.u32() % length, 1 + rng.u32() % 4) for _club in owners]
        tenure = [t for _seq, _off, t in picks]
        for season in range(burn_in + seasons):
            measured = season >= burn_in
            changed = 0
            for i, (seq, offset, _t) in enumerate(picks):
                w, l, t = seq[(offset + season) % length]
                p = fire_permille(model, owners[i], w, l, t, tenure[i])
                fired = decide(p, rng.u32())
                if measured:
                    decisions += 1
                    bucket = tenure_bucket(tenure[i])
                    seen_by_tenure[bucket] += 1
                    if fired:
                        changed += 1
                        fired_by_tenure[bucket] += 1
                        pct = (2 * w + t) / (2 * (w + l + t))
                        fired_pcts.append(pct)
                        fired_tenures.append(tenure[i])
                        after_winning += pct > 0.5
                tenure[i] = 1 if fired else tenure[i] + 1
            if measured:
                changes_per_offseason.append(changed)
    fired_pcts.sort()
    fired_tenures.sort()
    n = len(fired_pcts)
    offseasons = replications * seasons
    return {
        "offseasons": offseasons,
        "decisions": decisions,
        "changes": n,
        "changes_per_offseason": round(n / offseasons, 3),
        "fewest_in_an_offseason": min(changes_per_offseason),
        "most_in_an_offseason": max(changes_per_offseason),
        "median_fired_win_pct": round(_median(fired_pcts), 3),
        "share_fired_after_a_winning_season": round(after_winning / n, 3),
        "median_tenure_when_fired": _median(fired_tenures),
        "fired_rate_by_tenure": [round(fired_by_tenure[b] / seen_by_tenure[b], 3) for b in range(TENURE_BUCKETS)],
    }


def parse_records(line: str) -> list[tuple[int, int, int]]:
    """``"10-6-0 8-8-0 ..."`` -> [(wins, losses, ties), ...], one entry per season in order."""
    out = []
    for item in line.split():
        w, l, t = (int(x) for x in item.split("-"))
        out.append((w, l, t))
    return out


def _median(sorted_values: list) -> float:
    n = len(sorted_values)
    mid = n // 2
    return sorted_values[mid] if n % 2 else (sorted_values[mid - 1] + sorted_values[mid]) / 2


# ---------------------------------------------------------------------------------------------------------------------
# Loading and validating
# ---------------------------------------------------------------------------------------------------------------------
def load_owners(path: Path | str = DEFAULT_OWNERS) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_owners(data)
    return data


def load_pool(path: Path | str = DEFAULT_POOL) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_pool(data)
    return data


def cited_urls(doc: Mapping) -> set[str]:
    """Every https URL a document cites outside its pinned ``sources`` block (those carry a SHA-256 instead)."""
    found: set[str] = set()

    def walk(node, depth=0):
        if isinstance(node, dict):
            for key, value in node.items():
                if depth == 0 and key in ("sources", "url_checks"):
                    continue
                walk(value, depth + 1)
        elif isinstance(node, list):
            for item in node:
                walk(item, depth + 1)
        elif isinstance(node, str) and node.startswith("https://"):
            found.add(node)

    walk(doc)
    return found


def _check_urls(doc: Mapping) -> None:
    """Every cited URL was fetched (HTTP 200) and the page contained the words that make it a source for what it is cited for."""
    checks = doc.get("url_checks", {})
    for url in cited_urls(doc):
        result = checks.get(url)
        _require(isinstance(result, dict) and result.get("http") == 200 and result.get("page_contains") and result.get("checked"),
                 f"{url} was not checked")


def _check_sources(sources: Mapping, wanted: Iterable[str]) -> None:
    _require(isinstance(sources, dict) and sources, "sources must be a non-empty mapping")
    for key in wanted:
        _require(key in sources, f"source {key!r} is missing")
    for key, pin in sources.items():
        _require(isinstance(pin, dict) and str(pin.get("url", "")).startswith("https://"),
                 f"source {key}: a pinned https URL is required")
        if "sha256" in pin:
            _require(HEX64.match(pin["sha256"]) is not None, f"source {key}: sha256 must be 64 lowercase hex digits")


def validate_owners(doc: Mapping) -> None:
    _require(doc.get("schema") == OWNERS_SCHEMA, "unknown owners schema")
    _require(doc.get("base_year") == 2026, "base year must be 2026")
    _check_sources(doc.get("sources", {}), ("nflverse_games", "wikipedia_owners"))
    model = doc.get("model", {})
    base = model.get("base_permille")
    _require(isinstance(base, list) and len(base) == TENURE_BUCKETS
             and all(isinstance(row, list) and len(row) == GAMES_SCALE + 1 for row in base),
             f"base_permille must be {TENURE_BUCKETS} rows of {GAMES_SCALE + 1} numbers")
    for row in base:
        _require(all(type(v) is int and 0 <= v <= 1000 for v in row), "base_permille values are integers 0..1000")
        _require(all(a >= b for a, b in zip(row, row[1:])), "a better record never raises the firing chance")
    _require(type(model.get("league_q8")) is int and 64 <= model["league_q8"] <= 1024, "league_q8 must be a Q8 integer")
    clubs = doc.get("clubs", [])
    _require([c.get("team") for c in clubs] == sorted(CLUBS), "clubs must be the 32 clubs in alphabetical order")
    indexes = set()
    for club in clubs:
        team = club["team"]
        _require(type(club.get("team_index")) is int and 0 <= club["team_index"] < 32, f"{team}: bad team_index")
        indexes.add(club["team_index"])
        _require(type(club.get("fire_scale_q8")) is int and 64 <= club["fire_scale_q8"] <= 1024,
                 f"{team}: fire_scale_q8 must be a Q8 integer between 64 and 1024")
        owner = club.get("owner", {})
        _require(str(owner.get("name", "")).strip() and type(owner.get("since")) is int, f"{team}: owner needs a name and a year")
        _require(owner.get("source") in doc["sources"], f"{team}: owner has no listed source")
        history = club.get("history", {})
        _require(history.get("decisions", 0) > 0 and history.get("changes", -1) >= 0, f"{team}: history counts")
        current = history.get("current", {})
        _require(str(current.get("name", "")).strip() and str(current.get("source", "")).startswith("https://"),
                 f"{team}: current head coach needs a name and a source URL")
        _require(club.get("sources") and all(s in doc["sources"] for s in club["sources"]), f"{team}: sources must be listed")
        _require(history["changes"] == len(history.get("changes_log", [])), f"{team}: changes_log must list every change")
    _require(indexes == set(range(32)), "team_index must be a permutation of 0..31")
    _check_urls(doc)


def validate_pool(doc: Mapping) -> None:
    _require(doc.get("schema") == POOL_SCHEMA, "unknown pool schema")
    _require(doc.get("base_year") == 2026, "base year must be 2026")
    _check_sources(doc.get("sources", {}), ("nflverse_games",))
    seen = set()
    for person in doc.get("candidates", []):
        pid = person.get("id")
        _require(re.fullmatch(r"[a-z][a-z0-9\-]*", str(pid)) and pid not in seen, f"candidate id {pid!r} is not unique")
        seen.add(pid)
        for field in ("first", "last"):
            _require(ASCII_NAME.match(str(person.get(field, ""))) is not None, f"{pid}: {field} must be plain letters")
        _require(len(person["first"]) + len(person["last"]) <= 24, f"{pid}: the name does not fit a coach string")
        _require(person.get("side") in ("offense", "defense", "special"), f"{pid}: side")
        _require(person.get("kind") in ("coordinator", "former_head_coach"), f"{pid}: kind")
        sources = person.get("sources")
        _require(isinstance(sources, list) and sources, f"{pid}: at least one source is required")
        for src in sources:
            _require(str(src.get("url", "")).startswith("https://") and src.get("what"), f"{pid}: a source needs a URL and what it shows")
        _require(person.get("status") in ("employed", "available"), f"{pid}: status")
    _check_urls(doc)
