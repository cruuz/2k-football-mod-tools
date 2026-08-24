#!/usr/bin/env python3
"""Read-only static probe of the NFL 2K5 franchise schedule tables.

Parses the Franchise1 SAVEGAME.DAT payload (720,044 bytes, sha256
0db746fe2c8ae2102fdd420863a5e5bcddec4b83ac3e234568824c337e4422a7 in the
pinned pre-draft xemu fixture) without touching signatures.  It never
writes game bytes: inputs are opened read-only and outputs go to report
files only.

Discovered layout (fixture-derived, see reports/gameplay_tuning/
nfl2k5_franchise_schedule_probe.json):

* 0x000000..0x0002e0 -- settings prefix (sliders 0x284..0x2DC, already
  mapped by nfl2k5_xbox_save_inventory.py).
* 0x0002e0 -- ASCII tag "ROST"; packed roster/player payload follows.
* 0x072a94 -- UPCOMING season schedule: 256 8-byte game records,
  [type=0x00][home][away][month][day][slot=0x04/0x05][hour][minute],
  16 games per team, weeks 1-17 (Sep 9 .. Jan 2 in the pinned fixture),
  followed at 0x073294 by an ascending u32 offset table.
* 0x0917ca -- PLAYED season schedule slot array: 378 8-byte slots
  beginning with four zero slots; first game record at 0x0917ea,
  [type=0x03][home][away][month][day][slot][hour][minute], filler
  slots 07 00 00 00 00 00 00 00 between weeks.  256 regular-season
  games plus a 12-record postseason tail: 4 wild-card, 4 divisional,
  2 conference, 1 championship game between two NFL teams (week 20 /
  0x14 in the game's internal numbering) and 1 all-star game using
  placeholder team ids 32/33.
* Kickoff time-of-day is the trailing (hour, minute) pair of every game
  record; hour is a 12-hour clock (0 encodes 12).  Primetime slots are
  8 <= hour <= 11 (8:30 PM Sunday night, 9:00 PM Monday night).  No
  separate per-game day/night enum byte exists in these tables; the
  XBE's Day/Afternoon/Night enum (default.xbe 0x00AF87F0) is the
  pregame UI setting, not a franchise-save field.
* Team index = alphabetical-by-nickname order (0=49ers .. 31=Vikings);
  ids 32/33 are conference all-star placeholders.
"""

from __future__ import annotations

import argparse
import calendar
import datetime
import hashlib
import json
import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fatx_dirent_rename import PARTITIONS, FatXVolume  # noqa: E402

FRANCHISE_SIZE = 720_044
FRANCHISE_SHA256 = (
    "0db746fe2c8ae2102fdd420863a5e5bcddec4b83ac3e234568824c337e4422a7"
)
TITLE_ID = "53450030"
FRANCHISE_DIR_ID = "256B40374FD6"
FILLER_SLOT = b"\x07" + b"\x00" * 7
RECORD_SIZE = 8
UPCOMING_TYPE = 0x00
PLAYED_TYPE = 0x03
UPCOMING_SLOT_VALUES = {0x04, 0x05}
PLAYED_REGULAR_SLOT_VALUE = 0x0A
PLAYED_POSTSEASON_SLOT_VALUE = 0x00
TEAM_NAMES = (
    "49ers", "Bears", "Bengals", "Bills", "Broncos", "Browns",
    "Buccaneers", "Cardinals", "Chargers", "Chiefs", "Colts", "Cowboys",
    "Dolphins", "Eagles", "Falcons", "Giants", "Jaguars", "Jets",
    "Lions", "Packers", "Panthers", "Patriots", "Raiders", "Rams",
    "Ravens", "Redskins", "Saints", "Seahawks", "Steelers", "Texans",
    "Titans", "Vikings",
)
TEAM_STADIUM_KEYS = (
    "s25", "s05", "s06", "s03", "s08", "s30", "s27", "s00", "s24",
    "s13", "s11", "s07", "s14", "s21", "s01", "s18", "s12", "s19",
    "s09", "s10", "s04", "s16", "s20", "s23", "s02", "s29", "s17",
    "s26", "s22", "s37", "s28", "s15",
)
DEFAULT_JSON = ROOT / "reports" / "gameplay_tuning" / (
    "nfl2k5_franchise_schedule_probe.json"
)
DEFAULT_TSV = ROOT / "reports" / "gameplay_tuning" / (
    "nfl2k5_franchise_schedule_probe.tsv"
)


class ProbeError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProbeError(message)


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def hx(value: int, width: int = 8) -> str:
    return f"0x{value:0{width}x}"


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def sha256_argument(value: str) -> str:
    require(len(value) == 64 and all(c in "0123456789abcdef" for c in value),
            "sha256 argument must be 64 lowercase hex chars")
    return value


@dataclass
class GameRecord:
    offset: int
    kind: str
    home: int
    away: int
    month: int
    day: int
    slot: int
    hour: int
    minute: int
    round: str = "regular"
    week: int = 0

    @property
    def date(self) -> datetime.date:
        year = 2004 if self.month >= 8 else 2005
        return datetime.date(year, self.month, self.day)


def looks_like_game(raw: bytes, record_type: int) -> bool:
    return (
        len(raw) == RECORD_SIZE
        and raw[0] == record_type
        and raw[1] < 34
        and raw[2] < 34
        and raw[1] != raw[2]
        and 1 <= raw[3] <= 12
        and 1 <= raw[4] <= calendar.monthrange(2004, raw[3])[1]
        and raw[6] < 13
        and raw[7] < 60
    )


def decode_game(offset: int, raw: bytes, kind: str) -> GameRecord:
    return GameRecord(offset, kind, raw[1], raw[2], raw[3], raw[4],
                      raw[5], raw[6], raw[7])


def find_runs(payload: bytes, record_type: int, minimum_run: int) -> list[tuple[int, int]]:
    n = len(payload)

    def slot_ok(off: int) -> bool:
        raw = payload[off:off + RECORD_SIZE]
        if len(raw) != RECORD_SIZE:
            return False
        return (looks_like_game(raw, record_type)
                or raw == FILLER_SLOT
                or raw == b"\x00" * RECORD_SIZE)

    runs: list[tuple[int, int]] = []
    off = 0
    while off <= n - RECORD_SIZE:
        if slot_ok(off):
            start = off
            while off <= n - RECORD_SIZE and slot_ok(off):
                off += RECORD_SIZE
            count = (off - start) // RECORD_SIZE
            if count >= minimum_run:
                runs.append((start, count))
        else:
            off += 1
    return runs


def _home_away_balanced(games: list[GameRecord]) -> bool:
    per_team = [0] * 32
    home = [0] * 32
    for game in games:
        if game.home >= 32 or game.away >= 32:
            return False
        per_team[game.home] += 1
        per_team[game.away] += 1
        home[game.home] += 1
    return set(per_team) == {16} and set(home) == {8}


def parse_upcoming(payload: bytes) -> dict[str, Any]:
    candidates = find_runs(payload, UPCOMING_TYPE, 256)
    require(bool(candidates), "no upcoming schedule candidate runs")
    for start, count in candidates:
        if count != 256:
            continue
        games = []
        ok = True
        for index in range(count):
            off = start + index * RECORD_SIZE
            raw = payload[off:off + RECORD_SIZE]
            if not looks_like_game(raw, UPCOMING_TYPE) or raw[5] not in (
                    UPCOMING_SLOT_VALUES):
                ok = False
                break
            games.append(decode_game(off, raw, "upcoming_regular"))
        if ok and _home_away_balanced(games):
            weeks = assign_weeks(games)
            tail = start + count * RECORD_SIZE
            pointers = list(struct.unpack_from("<16I", payload, tail))
            return {
                "table_offset": hx(start),
                "record_count": count,
                "record_size": RECORD_SIZE,
                "record_layout":
                    "[type=0x00][home][away][month][day][slot][hour][minute]",
                "week_span": [min(weeks.values()), max(weeks.values())],
                "following_u32_offset_table": hx(tail),
                "following_u32_monotonic": pointers == sorted(pointers),
                "games": games,
                "weeks": weeks,
            }
    raise ProbeError("no upcoming schedule run satisfies the 256-game "
                     "16-per-team 8-home invariant")


def parse_played(payload: bytes) -> dict[str, Any]:
    candidates = find_runs(payload, PLAYED_TYPE, 268)
    require(bool(candidates), "no played schedule candidate runs")
    for start, count in candidates:
        if not 268 <= count <= 600:
            continue
        games: list[GameRecord] = []
        fillers = 0
        zero_slots = 0
        ok = True
        for index in range(count):
            off = start + index * RECORD_SIZE
            raw = payload[off:off + RECORD_SIZE]
            if raw == FILLER_SLOT:
                fillers += 1
            elif raw == b"\x00" * RECORD_SIZE:
                zero_slots += 1
            elif looks_like_game(raw, PLAYED_TYPE) and raw[5] in (
                    PLAYED_REGULAR_SLOT_VALUE, PLAYED_POSTSEASON_SLOT_VALUE):
                kind = ("played_regular"
                        if raw[5] == PLAYED_REGULAR_SLOT_VALUE
                        else "played_postseason")
                games.append(decode_game(off, raw, kind))
            else:
                ok = False
                break
        if not ok:
            continue
        regular = [g for g in games if g.kind == "played_regular"]
        postseason = sorted(
            (g for g in games if g.kind == "played_postseason"),
            key=lambda g: (g.month, g.day))
        if len(regular) != 256 or len(postseason) != 12:
            continue
        if not _home_away_balanced(regular):
            continue
        label_postseason(postseason)
        weeks = assign_weeks(regular)
        return {
            "table_offset": hx(start),
            "slot_count": count,
            "game_count": len(games),
            "filler_slots": fillers,
            "zero_slots": zero_slots,
            "record_layout":
                "[type=0x03][home][away][month][day][slot][hour][minute]",
            "games": games,
            "postseason": postseason,
            "weeks": weeks,
        }
    raise ProbeError("no played schedule run satisfies the 256+12 game "
                     "postseason invariant")


def assign_weeks(games: list[GameRecord]) -> dict[int, int]:
    anchors: dict[int, datetime.date] = {}
    for game in games:
        date = game.date
        if date.weekday() in (3, 4, 5):
            anchor = date + datetime.timedelta(days=6 - date.weekday())
        else:
            anchor = date - datetime.timedelta(days=(date.weekday() + 1) % 7)
        anchors[game.offset] = anchor
    ordered = sorted(set(anchors.values()))
    return {game.offset: ordered.index(anchors[game.offset]) + 1
            for game in games}


def label_postseason(postseason: list[GameRecord]) -> None:
    rounds = (["wild_card"] * 4 + ["divisional"] * 4 + ["conference"] * 2)
    specials = postseason[10:]
    for game, round_name in zip(postseason[:10], rounds):
        game.round = round_name
        game.week = {"wild_card": 17, "divisional": 18,
                     "conference": 19}[round_name]
    sb = []
    for game in specials:
        if game.home < 32 and game.away < 32:
            game.round = "super_bowl"
            game.week = 20
            sb.append(game)
        else:
            game.round = "all_star"
            game.week = 21
    require(len(sb) == 1, "expected exactly one NFL-vs-NFL championship game")


def kickoff_info(game: GameRecord) -> dict[str, Any]:
    hour = game.hour if game.hour != 0 else 12
    label = f"{hour}:{game.minute:02d} PM"
    primetime = 8 <= game.hour <= 11
    slot = "standard"
    if (game.hour, game.minute) == (8, 30):
        slot = "sunday_night"
    elif (game.hour, game.minute) == (9, 0):
        slot = "monday_or_thursday_night"
    elif (game.hour, game.minute) in ((4, 5), (4, 15)):
        slot = "late_doubleheader"
    elif (game.hour, game.minute) == (12, 30):
        slot = "thanksgiving_early"
    return {"hour_field": game.hour, "minute_field": game.minute,
            "display": label, "primetime": primetime, "slot": slot}


def team_name(team_id: int) -> str:
    if team_id < 32:
        return TEAM_NAMES[team_id]
    return {32: "AFC-all-star", 33: "NFC-all-star"}[team_id]


def region_map(payload: bytes) -> list[dict[str, Any]]:
    regions = [
        {"offset": hx(0x000000), "size": 0x2E0,
         "label": "settings_prefix_sliders_0x284_0x2DC",
         "confidence": "proved",
         "evidence": "nfl2k5_xbox_save_inventory.json settings_prefix_join_proved"},
        {"offset": hx(0x0002E0), "size": 0x72A94 - 0x2E0,
         "label": "ROST_tagged_packed_roster_and_player_payload",
         "confidence": "partial", "evidence": "ASCII tag ROST at 0x2E0"},
        {"offset": hx(0x072870), "size": 0x72A94 - 0x72870,
         "label": "sentinel_float_fill_before_upcoming_schedule",
         "confidence": "observed", "evidence": "e6 01 c5 c4 float fill"},
        {"offset": hx(0x073294), "size": 0x80,
         "label": "ascending_u32_offset_table_after_upcoming_schedule",
         "confidence": "observed", "evidence": "monotonic u32 LE values"},
        {"offset": hx(0x075C00), "size": 0x07A000 - 0x075C00,
         "label": "utf16_string_pool_stadiums_teams_coaches",
         "confidence": "proved",
         "evidence": "stadium keys s00-s59 and Super Bowl 2005 strings"},
        {"offset": hx(0x07A000), "size": 0x0917E2 - 0x07A000,
         "label": "utf16_string_pool_colleges_and_player_names",
         "confidence": "observed", "evidence": "college/player name pairs"},
        {"offset": hx(0x0914DC), "size": 0x22,
         "label": "team_order_array_0..31_then_FF",
         "confidence": "observed", "evidence": "identity permutation"},
        {"offset": hx(0x09239A), "size": 0x09323C - 0x09239A,
         "label": "unknown_sparse_low_value_matrix",
         "confidence": "unknown",
         "evidence": "0/3/7-heavy byte matrix after played schedule"},
    ]
    for region in regions:
        require(int(region["offset"], 16) + region["size"] <= len(payload),
                f"region {region['label']} exceeds payload")
    return regions


def build_report(payload: bytes, source: str) -> dict[str, Any]:
    require(len(payload) == FRANCHISE_SIZE,
            f"franchise payload is {len(payload)} bytes, not {FRANCHISE_SIZE}")
    upcoming = parse_upcoming(payload)
    played = parse_played(payload)
    rows = []
    for game in upcoming["games"]:
        info = kickoff_info(game)
        rows.append({
            "table": "upcoming", "offset": hx(game.offset),
            "round": "regular", "week": upcoming["weeks"][game.offset],
            "date": game.date.isoformat(),
            "home": team_name(game.home), "away": team_name(game.away),
            "home_id": game.home, "away_id": game.away,
            "kickoff": info["display"], "slot": info["slot"],
            "primetime": info["primetime"],
            "hour_field": info["hour_field"], "minute_field": info["minute_field"],
        })
    for game in played["games"]:
        info = kickoff_info(game)
        round_name = getattr(game, "round", "regular")
        week = (played["weeks"][game.offset] if round_name == "regular"
                else game.week)
        rows.append({
            "table": "played", "offset": hx(game.offset),
            "round": round_name, "week": week,
            "date": game.date.isoformat(),
            "home": team_name(game.home), "away": team_name(game.away),
            "home_id": game.home, "away_id": game.away,
            "kickoff": info["display"], "slot": info["slot"],
            "primetime": info["primetime"],
            "hour_field": info["hour_field"], "minute_field": info["minute_field"],
        })
    sb = [r for r in rows if r["round"] == "super_bowl"]
    return {
        "schema": "nfl2k5_franchise_schedule_probe/v1",
        "read_only": True,
        "inputs": {"source": source, "payload_size": len(payload),
                   "sha256": sha256(payload),
                   "matches_pinned_predraft_fixture":
                       sha256(payload) == FRANCHISE_SHA256},
        "summary": {
            "upcoming_table_offset": upcoming["table_offset"],
            "upcoming_games": upcoming["record_count"],
            "upcoming_week_span": upcoming["week_span"],
            "played_table_offset": played["table_offset"],
            "played_slots": played["slot_count"],
            "played_games": played["game_count"],
            "postseason_rounds": {
                "wild_card": 4, "divisional": 4, "conference": 2,
                "super_bowl": 1, "all_star": 1,
            },
            "super_bowl_game": sb[0] if sb else None,
            "kickoff_field_offsets": "record+6 (hour), record+7 (minute)",
            "primetime_rule": "8 <= hour <= 11 (8:30 SNF / 9:00 MNF; 12-hour clock)",
            "hour_encoding": "12-hour clock; 0 encodes 12",
        },
        "upcoming_table": {k: v for k, v in upcoming.items()
                           if k not in ("games", "weeks")},
        "played_table": {k: v for k, v in played.items()
                         if k not in ("games", "postseason", "weeks")},
        "regions": region_map(payload),
        "games": rows,
    }


def schedule_tsv(report: dict[str, Any]) -> bytes:
    columns = ["table", "offset", "round", "week", "date", "home", "away",
               "kickoff", "slot", "primetime", "hour_field", "minute_field"]
    lines = ["\t".join(columns)]
    for row in report["games"]:
        lines.append("\t".join(str(row[c]) for c in columns))
    return ("\n".join(lines) + "\n").encode()


def self_test() -> None:
    hour_cases = [(1, 0, "1:00 PM", False), (4, 15, "4:15 PM", False),
                  (8, 30, "8:30 PM", True), (9, 0, "9:00 PM", True),
                  (0, 30, "12:30 PM", False), (12, 30, "12:30 PM", False)]
    for hour, minute, display, primetime in hour_cases:
        game = GameRecord(0, "upcoming_regular", 0, 1, 9, 12, 4, hour, minute)
        info = kickoff_info(game)
        require(info["display"] == display and info["primetime"] == primetime,
                f"kickoff_info mismatch for {hour}:{minute}")
    raw = bytes([PLAYED_TYPE, 18, 3, 1, 30, 0, 4, 0])
    require(looks_like_game(raw, PLAYED_TYPE), "championship record rejected")
    specials = [decode_game(0, raw, "played_postseason"),
                decode_game(8, bytes([PLAYED_TYPE, 32, 33, 2, 6, 0, 4, 0]),
                            "played_postseason")]
    tail = [decode_game(16 + i * 8,
                        bytes([PLAYED_TYPE, i, i + 1, 1, 8 + i // 2, 0, 1, 0]),
                        "played_postseason") for i in range(10)] + specials
    label_postseason(tail)
    require(tail[10].round == "super_bowl" and tail[10].week == 20,
            "super bowl labeling failed")
    require(tail[11].round == "all_star", "all-star labeling failed")
    require(tail[0].round == "wild_card" and tail[9].round == "conference",
            "postseason round labeling failed")
    games = [decode_game(i * 8,
                         bytes([UPCOMING_TYPE, i % 32, (i + 1) % 32,
                                9, 12 + (i % 3), 4, 1, 0]),
                         "upcoming_regular") for i in range(3)]
    weeks = assign_weeks(games)
    require(sorted(set(weeks.values())) == [1], "week clustering failed")
    print("NFL2K5_FRANCHISE_SCHEDULE_PROBE_SELF_TEST_OK")


def load_franchise_from_image(image: Path) -> bytes:
    require(image.is_file() and not image.is_symlink(),
            "image must be a regular non-symlink file")
    with image.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        require(handle.tell() == 8 * 1024**3, "expected an 8 GiB raw image")
        volume = FatXVolume(handle, *PARTITIONS["E"])
        container = volume.resolve(["UDATA", TITLE_ID, FRANCHISE_DIR_ID])
        require(container.is_directory, "franchise container not a directory")
        entries = {e.name: e for e in
                   volume.read_directory(container.first_cluster)}
        require("SAVEGAME.DAT" in entries, "SAVEGAME.DAT missing")
        entry = entries["SAVEGAME.DAT"]
        chain = volume.cluster_chain(entry.first_cluster)
        payload = bytearray()
        remaining = entry.file_size
        for cluster in chain:
            handle.seek(volume.cluster_offset(cluster))
            chunk = handle.read(min(volume.bytes_per_cluster, remaining))
            payload.extend(chunk)
            remaining -= len(chunk)
        require(remaining == 0, "short SAVEGAME.DAT read")
        return bytes(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--savegame", type=Path,
                        help="extracted Franchise1 SAVEGAME.DAT")
    parser.add_argument("--image", type=Path,
                        help="raw 8 GiB Xbox HDD image (read-only)")
    parser.add_argument("--expected-sha256", type=sha256_argument,
                        help="pin the expected franchise payload hash")
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--tsv-out", type=Path, default=DEFAULT_TSV)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    require(bool(args.savegame) != bool(args.image),
            "supply exactly one of --savegame or --image")
    if args.savegame is not None:
        require(args.savegame.is_file() and not args.savegame.is_symlink(),
                "savegame must be a regular non-symlink file")
        payload = args.savegame.read_bytes()
        source = str(args.savegame)
    else:
        payload = load_franchise_from_image(args.image)
        source = str(args.image)
    if args.expected_sha256 is not None:
        require(sha256(payload) == args.expected_sha256,
                "franchise payload hash differs from expectation")
    report = build_report(payload, source)
    protected = {args.savegame, args.image}
    for out, blob, label in ((args.json_out, canonical_json(report), "JSON"),
                             (args.tsv_out, schedule_tsv(report), "TSV")):
        require(out not in protected, f"refusing to overwrite input {out}")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(blob)
    summary = report["summary"]
    print(
        "NFL2K5_FRANCHISE_SCHEDULE_PROBE_OK "
        f"upcoming@{summary['upcoming_table_offset']} "
        f"played@{summary['played_table_offset']} "
        f"games={summary['played_games']} "
        f"super_bowl={summary['super_bowl_game']['date']} "
        f"{summary['super_bowl_game']['home']}-vs-"
        f"{summary['super_bowl_game']['away']} "
        f"kickoff={summary['super_bowl_game']['kickoff']} "
        f"fixture={report['inputs']['matches_pinned_predraft_fixture']} "
        "read_only=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
