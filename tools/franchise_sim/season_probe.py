"""Run a seeded native NFL 2K5 regular season and read player stats from a supplied game and roster.

    python3 tools/franchise_sim/season_probe.py default.xbe roster.body season.json --seed 2501

This offline lab uses fresh-profile options, franchise team selection, coaching gameplans and the scheduler of the supplied USA game.
Only the progress display and acknowledgement of informational dialogs are substituted.
The output includes the closing rosters, every player's season totals, and weekly contributions credited to each club.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.nfl2k5_supersim_draft_fixture import Machine

STATS = {
    "games": 0, "rush_att": 1, "rush_yds": 2, "rush_td": 3, "pass_att": 6, "pass_cmp": 7,
    "pass_yds": 8, "pass_td": 9, "pass_int": 10, "sacked": 11, "rec": 12, "rec_yds": 13,
    "rec_td": 14, "tackles": 18, "sacks_raw": 19, "def_int": 20, "ff": 21, "targets": 50,
    "prs": 106, "qbh": 107, "pa": 108, "ha": 109, "sa": 110,
}
SIGNED_YARDS = {"rush_yds", "rec_yds", "pass_yds"}
POSITIONS = ("QB", "K", "P", "WR", "CB", "FS", "SS", "HB", "FB", "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE")
STATE = {"stage": 0xE576A4, "week": 0xE576B4, "end_week": 0xE576B0, "year": 0xE576B8}


def player_name(machine, address):
    pointer = machine.get(address)
    if not pointer:
        return ""
    return bytes(machine.uc.mem_read(pointer, 80)).decode("utf-16-le", errors="replace").partition("\0")[0]


def club_players(machine, team):
    club = machine.team_base + 500 * team
    for slot in range(machine.uc.mem_read(club + 0x11C, 1)[0]):
        player = machine.get(club + 4 * slot)
        if player:
            yield slot, player


def player_info(machine, player):
    raw = machine.uc.mem_read(player, 0x54)
    position = raw[0x35]
    return {"ptr": player, "pos": position, "pos_name": POSITIONS[position] if position < len(POSITIONS) else "?",
            "name": (player_name(machine, player + 0x10) + " " + player_name(machine, player + 0x14)).strip(),
            "depth": (struct.unpack_from("<H", raw, 0x28)[0] >> 10) & 7,
            "catch": raw[0x44], "pblock": raw[0x46], "prush": raw[0x48]}


def stat_line(machine, player):
    line = {}
    for name, field in STATS.items():
        word = machine.call(0x14EE40, ecx=player, edx=field) & 0xFFFF
        line[name] = word - 65536 if name in SIGNED_YARDS and word >= 32768 else word
    return line


def regular_stats(machine):
    previous = machine.get(0xBD7F98)
    machine.put(0xBD7F98, 0)
    players = []
    try:
        for team in range(32):
            for slot, player in club_players(machine, team):
                players.append({"team": team, "slot": slot, **player_info(machine, player), **stat_line(machine, player)})
    finally:
        machine.put(0xBD7F98, previous)
    return players


class SeasonParticipants:
    """Keep the season records of players who leave a club before the closing roster is read."""

    def __init__(self, machine):
        self.machine = machine
        self.weekly_clubs = {}
        self.players = {}
        self.totals = {}
        self.stints = {}
        # Each team enters this routine once per game when its player stats are merged.
        machine.uc.hook_add(machine.u.UC_HOOK_CODE, self.game, begin=0x134DD0, end=0x134DD0)

    def game(self, *_):
        team = self.machine.reg("ECX")
        if not 0 <= team < 32:
            raise RuntimeError(f"unexpected club in the native postgame merge: {team}")
        for _, player in club_players(self.machine, team):
            if self.weekly_clubs.setdefault(player, team) != team:
                raise RuntimeError(f"player {player:#x} appeared for two clubs during one week")

    def finish_week(self):
        # The getters return cumulative totals. Only this week's change belongs to the club observed above.
        previous_class = self.machine.get(0xBD7F98)
        self.machine.put(0xBD7F98, 0)
        try:
            if not self.weekly_clubs:
                raise RuntimeError("no postgame player records were observed this week")
            for player, team in self.weekly_clubs.items():
                if player not in self.players:
                    self.players[player] = player_info(self.machine, player)
                current = stat_line(self.machine, player)
                previous = self.totals.get(player, {})
                contribution = self.stints.setdefault((player, team), Counter())
                for name, total in current.items():
                    contribution[name] += total - previous.get(name, 0)
                self.totals[player] = current
        finally:
            self.machine.put(0xBD7F98, previous_class)
        self.weekly_clubs.clear()

    def results(self):
        return {
            "all_participants": [{**self.players[p], **total} for p, total in sorted(self.totals.items())],
            "team_participants": [{"team": team, **self.players[p], **total}
                                  for (p, team), total in sorted(self.stints.items())],
        }


def run(payload, body, *, seed, quarters, weeks, user_team=0, include_participants=True):
    machine = Machine(payload, trace_writes=False)
    game_roster = machine.ARENA + 0x300
    size = len(body) - 0x40
    machine.uc.mem_write(game_roster, body)
    machine.put(0xB72804, game_roster)
    machine.put(0xB72808, size if size in (0xB0000, 0xCA000) else 0x91000)
    machine.put(0xB7280C, size)
    machine.fixup_roster(game_roster + 0x40)
    machine.configure_fresh_franchise(seed=seed, quarter_minutes=quarters)
    sliders = {name: machine.f32(va) for name, va in
               (("injury", 0xE60204), ("fumble", 0xE60208), ("interception", 0xE6020C))}
    machine.call(0x13EE10, budget=2_000_000_000)
    machine.finish_franchise_team_selection(user_team)
    gameplans = [machine.call(0xC6CF0, ecx=i) for i in range(32)]
    if gameplans != [0xE41CE0 + 0x24 * i for i in range(32)]:
        raise RuntimeError("franchise did not register all 32 coaching gameplans")
    machine.leaf(0x177990, lambda: machine.ret(pop=4), reason="progress display")
    machine.leaf(0x14E520, lambda: machine.ret(), reason="acknowledge informational dialog")

    def decision(*_):
        raise RuntimeError(f"unexpected decision dialog from {machine.get(machine.reg('ESP')):#x}")

    machine.uc.hook_add(machine.u.UC_HOOK_CODE, decision, begin=0x14E440, end=0x14E440)
    participants = SeasonParticipants(machine) if include_participants else None
    machine.uc.ctl_flush_tb()

    def state():
        return {key: machine.get(address) for key, address in STATE.items()}

    current = state()
    if current["stage"] != 8 or current["week"] != 0:
        raise RuntimeError(f"franchise did not start the regular season: {current}")
    for expected_week in range(1, min(weeks, current["end_week"]) + 1):
        machine.call(0x247D40, ecx=machine.ARENA + 0x1A0000, budget=20_000_000_000)
        current = state()
        if current["stage"] != 8 or current["week"] != expected_week:
            raise RuntimeError(f"unexpected state after regular-season week {expected_week}: {current}")
        if participants is not None:
            participants.finish_week()
        print(f'Week {expected_week}/{current["end_week"]}', file=sys.stderr, flush=True)

    scores = []
    for week in range(current["week"]):
        for slot in range(17):
            fixture = week * 17 + slot
            entry = machine.uc.mem_read(0xE57C40 + 8 * fixture, 8)
            if entry[0] == 3:
                points = machine.uc.mem_read(0xE587F0 + 10 * fixture, 10)
                scores.append({"week": week, "home_team": entry[1], "away_team": entry[2],
                               "home": sum(points[:5]), "away": sum(points[5:])})
    return {"seed": seed, "ql": quarters, "weeks": current["week"], "state": current,
            "xbe_sha256": hashlib.sha256(payload).hexdigest(), "roster_sha256": hashlib.sha256(body).hexdigest(),
            "sliders": sliders, "user_team": user_team, "registered_gameplans": len(gameplans),
            "players": regular_stats(machine), "scores": scores, **(participants.results() if participants else {})}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xbe", type=Path)
    parser.add_argument("roster_body", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seed", type=int, default=2501)
    parser.add_argument("--ql", type=int, choices=range(1, 16), default=15)
    parser.add_argument("--weeks", type=int, choices=range(1, 20), default=19)
    parser.add_argument("--user-team", type=int, choices=range(32), default=0,
                        help="franchise club controlled by the user while games are simulated (0-31)")
    args = parser.parse_args()
    result = run(args.xbe.read_bytes(), args.roster_body.read_bytes(), seed=args.seed, quarters=args.ql,
                 weeks=args.weeks, user_team=args.user_team)
    args.output.write_text(json.dumps(result) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
