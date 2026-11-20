"""Finn's Team Statistics grid and Boxscore editor for an Xbox franchise save (b81 R41: parity rows I2 and H7).

Read-only season table
----------------------
Every club record in the arena carries 31 season counters, 16-bit words between team ``+0x1AA`` and ``+0x1E8`` that
the game adds each played game's numbers into (merger ``0x134DD0``; games played ``+0x1DC``).  The stat id of every word
and the game's own box-score caption for it are in ``nfl2k5_franchise_save.TEAM_STAT_FIELDS`` and the receipt
``finn-facts/evidence/team-season-and-box/native-and-saved-fields.json``.  Finn's Team Statistics form shows the club
and 31 columns (his installed ``ENFDefaultTeamStatViewSettings.ini``); ``FINN_COLUMNS`` keeps his captions and order.
Totals and rates use the game's own formulas where it has one: total offense ``0xD0`` = passing + rushing yards (the
getter ``0xCB2D0`` returned the same 245 yards for SF), yards allowed ``0xDE``, third and fourth down rates ``0xDC`` /
``0xDD``, red-zone scoring rates ``0xE3`` / ``0xE7`` (field goals plus touchdowns over trips).  The two averages differ
from the game's in-game box score: its descriptors divide by pass attempts (stat ``0x23``) and carries (``0x03``), which
the season record does not keep, so this table divides by the season's pass plays and rushing plays.  Finn's own
rounding of his averages has not been executed.  Yard words are signed (the native readers sign-extend them; a club can
finish below zero); every other counter is unsigned.  Six more counters (stat ids 0xB8, 0x30, 0x40, 0x3F, 0x16, 0x17)
have no caption in the game or in Finn and are not shown.

The won-lost-tied record is counted the way the game's standings getters ``0xC7720`` / ``0xC7750`` / ``0xC7780`` count
it: over all 22 grid rows and 17 slots, each played cell (type 3) compares the sum of the home side's five quarter bytes
(``0xC5110``) with the away side's (``0xC5150``).

Box scores
----------
A played cell's ten quarter-score bytes sit at ``season block + 0x107A + 10 * (17 * row + slot)``: home Q1-Q4 and
overtime, then away Q1-Q4 and overtime (FACTS: all 16 Week 1 results of the signed played save agreed with the
simulation; the standings getters above read the halves that way).  ``set_box_score`` writes those ten bytes.  Because
the standings are counted from them, the game's records follow the edit.  By default the counters the game itself moves
with every game follow too (``plan_box_score`` lists them before anything is written; independent review rev-finn F2,
F3): both clubs' points scored, points allowed and games played (``+0x1D8`` / ``+0x1DA`` / ``+0x1DC``) are recounted
from all their box scores, playoffs included (in two postseason saves every club's stored totals equal the sums over
all its games); the win streak byte ``+0x1F1`` is recounted; and when a regular-season result changes, both head
coaches' season and career W-L-T move by one (the native Week 1 of the signed 2026 franchise moved exactly those, for
every club; evidence ``finn-r2/evidence/f3/``).  A counter that does not match the box scores before the edit is left
alone and named.  Yards and the other counters are left alone.  A playoff box score may change its quarters but not its
winner (the bracket has already moved the winner on); a regular-season change does not re-seed a bracket.

Every write is bounded, validated before any byte changes, and leaves every other byte of the save as it was.  Nothing
here has been watched in the game yet.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import io
import struct
from typing import Any, Sequence

from . import nfl2k5_franchise_save as fs

# team-relative u16 season counters this module writes (stat ids 0x5B / 0x5C, merged at 0x1350AC / 0x1350CA)
TEAM_POINTS_FOR = 0x1D8
TEAM_POINTS_AGAINST = 0x1DA
assert fs.TEAM_STAT_FIELDS[TEAM_POINTS_FOR] == 0x5B and fs.TEAM_STAT_FIELDS[TEAM_POINTS_AGAINST] == 0x5C

# yards words: the native season readers sign-extend them (FACTS: -12 passing + 5 rushing reads as -7 total offense)
SIGNED_STATS = frozenset({0x4C, 0x50, 0x46, 0x45})
QUARTERS = ("Q1", "Q2", "Q3", "Q4", "OT")
SCORE_MAX = 0xFF

# the game's box-score captions for the season words (native table at retail 0xAED668), by stat id
STAT_TITLES: dict[int, str] = {
    0x4C: "Passing yards", 0x50: "Rushing yards", 0x46: "Passing yards allowed", 0x45: "Rushing yards allowed",
    0x25: "Pass plays", 0x26: "Rushing plays", 0x0E: "First downs", 0x43: "Two-point attempts",
    0x52: "Two-point conversions", 0x27: "Third down attempts", 0x53: "Third down conversions",
    0x28: "Fourth down attempts", 0x54: "Fourth down conversions", 0xB3: "Times in the red zone",
    0xB2: "Red zone touchdowns", 0xB1: "Red zone field goals", 0xB6: "Opponent red zone trips",
    0xB5: "Red zone touchdowns allowed", 0xB4: "Red zone field goals allowed", 0x24: "Penalties",
    0x62: "Penalty yards", 0x42: "Turnovers", 0x64: "Points off turnovers", 0x5B: "Points scored",
    0x5C: "Points allowed",
}


@dataclass(frozen=True)
class StatColumn:
    """One column of Finn's Team Statistics grid: his key and caption, our words, and how it is computed."""

    key: str                    # Finn's column key in ENFDefaultTeamStatViewSettings.ini
    caption: str                # Finn's caption
    title: str                  # the plain-words heading tooltip
    kind: str                   # "count", "yards", "average" or "percent"
    # (an "average" is the Studio's own arithmetic: its heading reads "<caption> (Studio)")
    numerator: tuple[int, ...]  # stat ids added together
    denominator: tuple[int, ...] = ()
    note: str = ""


def _count(key: str, caption: str, stat: int, kind: str = "count") -> StatColumn:
    return StatColumn(key, caption, STAT_TITLES[stat], kind, (stat,))


FINN_COLUMNS: tuple[StatColumn, ...] = (
    StatColumn("TYO", "TYO", "Total yards (offense)", "yards", (0x4C, 0x50),
               note="Passing plus rushing yards, the game's own total offense."),
    _count("PASS", "PASS", 0x4C, "yards"),
    StatColumn("AVGPASS", "AVG PASS", "Passing yards per pass play", "average", (0x4C,), (0x25,),
               note="Computed by the Studio: the season record keeps pass plays, not attempts, so this divides by "
                    "pass plays; Finn's own rounding is not known."),
    _count("RUSH", "RUSH", 0x50, "yards"),
    StatColumn("AVGRUSH", "AVG RUSH", "Rushing yards per rushing play", "average", (0x50,), (0x26,),
               note="Computed by the Studio: the season record keeps rushing plays, not carries, so this divides by "
                    "rushing plays; Finn's own rounding is not known."),
    StatColumn("TYD", "TYD", "Total yards allowed (defense)", "yards", (0x45, 0x46),
               note="Passing plus rushing yards allowed, the game's own yards allowed."),
    _count("DPA", "DPA", 0x46, "yards"),
    _count("DRA", "DRA", 0x45, "yards"),
    _count("FIRSTDOWNS", "1st", 0x0E),
    _count("THIRDATT", "3rd ATT", 0x27),
    _count("THIRDMD", "3rd MD", 0x53),
    StatColumn("THIRDPERCENT", "3rd %", "Third down conversion rate", "percent", (0x53,), (0x27,)),
    _count("FOURTHATT", "4th ATT", 0x28),
    _count("FOURTHMD", "4th MD", 0x54),
    StatColumn("FOURTHPERCENT", "4th %", "Fourth down conversion rate", "percent", (0x54,), (0x28,)),
    _count("RZA", "RZA", 0xB3),
    _count("RZTD", "RZTD", 0xB2),
    _count("RZFG", "RZFG", 0xB1),
    StatColumn("RZPERCENT", "RZ %", "Red zone scoring rate (touchdowns and field goals per trip)", "percent",
               (0xB1, 0xB2), (0xB3,)),
    _count("DRZ", "DRZ", 0xB6),
    _count("RZTA", "RZTA", 0xB5),
    _count("RZFGA", "RZFGA", 0xB4),
    StatColumn("RZSPERCENT", "RZS %", "Opponent red zone scoring rate", "percent", (0xB4, 0xB5), (0xB6,)),
    _count("PEN", "PEN", 0x24),
    _count("YD", "YD", 0x62),
    _count("TURNOVER", "TO", 0x42),
    _count("PTO", "PTO", 0x64),
    _count("TPS", "TPS", 0x5B),
    _count("TPSA", "TPSA", 0x5C),
    _count("PPLY", "PPLY", 0x25),
    _count("RPLY", "RPLY", 0x26),
)
assert len(FINN_COLUMNS) == 31 and len({c.key for c in FINN_COLUMNS}) == 31
# the stored words Finn's default view leaves out, offered after his columns
EXTRA_COLUMNS: tuple[StatColumn, ...] = (
    _count("TWOATT", "2PT ATT", 0x43),
    _count("TWOMD", "2PT MD", 0x52),
)
_SHOWN = {stat for column in FINN_COLUMNS + EXTRA_COLUMNS for stat in column.numerator + column.denominator}
assert _SHOWN <= set(fs.TEAM_STAT_FIELDS.values())


def stat_word(season: fs.TeamSeason, stat: int) -> int:
    """One season counter as the game reads it (yards sign-extended)."""

    word = season.stats.get(stat, 0)
    return word - 0x10000 if stat in SIGNED_STATS and word >= 0x8000 else word


def column_value(season: fs.TeamSeason, column: StatColumn) -> int | float | None:
    """The number in one cell: a count, a total, or a rate (None when its denominator is zero)."""

    top = sum(stat_word(season, stat) for stat in column.numerator)
    if not column.denominator:
        return top
    bottom = sum(stat_word(season, stat) for stat in column.denominator)
    if bottom == 0:
        return None
    if column.kind == "percent":
        return round(100.0 * top / bottom, 1)
    return round(top / bottom, 1)


def format_value(value: int | float | None, column: StatColumn) -> str:
    if value is None:
        return "-"
    if column.kind == "percent":
        return f"{value:.1f}%"
    if column.kind == "average":
        return f"{value:.1f}"
    return str(value)


@dataclass(frozen=True)
class TeamStatRow:
    team: int
    abbreviation: str
    games_played: int
    record: tuple[int, int, int]            # wins, losses, ties as the standings count them
    values: dict[str, int | float | None]   # column key -> value

    @property
    def record_text(self) -> str:
        return "-".join(str(n) for n in self.record)


def standings(save: fs.FranchiseSave) -> dict[int, tuple[int, int, int]]:
    """Wins, losses and ties per team the way 0xC7720 / 0xC7750 / 0xC7780 count them from the grid."""

    out = {team: [0, 0, 0] for team in range(save.league_team_count)}
    for game in save.games():
        if not game.played or game.scores is None:
            continue
        home, away = sum(game.scores[0]), sum(game.scores[1])
        for team, mine, theirs in ((game.home, home, away), (game.away, away, home)):
            if team in out:
                out[team][0 if mine > theirs else 1 if mine < theirs else 2] += 1
    return {team: (w, l, t) for team, (w, l, t) in out.items()}


def league_table(save: fs.FranchiseSave, columns: Sequence[StatColumn] = FINN_COLUMNS + EXTRA_COLUMNS
                 ) -> list[TeamStatRow]:
    """One row per league club (32 on a real save), in team-table order."""

    records = standings(save)
    rows = []
    for season in save.team_seasons():
        rows.append(TeamStatRow(season.index, season.abbreviation, season.games_played,
                                records.get(season.index, (0, 0, 0)),
                                {column.key: column_value(season, column) for column in columns}))
    return rows


def csv_text(save: fs.FranchiseSave, columns: Sequence[StatColumn] = FINN_COLUMNS + EXTRA_COLUMNS) -> str:
    """The table as CSV (Team, W-L-T, GP and the columns), the numbers as shown."""

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["Team", "W-L-T", "GP"] + [column.caption + (" (Studio)" if column.kind == "average" else "")
                                               for column in columns])
    for row in league_table(save, columns):
        writer.writerow([row.abbreviation, row.record_text, row.games_played]
                        + [format_value(row.values[column.key], column) for column in columns])
    return buffer.getvalue()


# --------------------------------------------------------------------------------------------- box scores
@dataclass(frozen=True)
class BoxScore:
    row: int
    slot: int
    home: int
    away: int
    home_quarters: tuple[int, int, int, int, int]
    away_quarters: tuple[int, int, int, int, int]
    postseason: bool

    @property
    def home_points(self) -> int:
        return sum(self.home_quarters)

    @property
    def away_points(self) -> int:
        return sum(self.away_quarters)

    @property
    def winner(self) -> str | None:
        """"home", "away" or None for a tie."""

        if self.home_points == self.away_points:
            return None
        return "home" if self.home_points > self.away_points else "away"


def _score_offset(save: fs.FranchiseSave, row: int, slot: int) -> int:
    return save.season_block + fs.S_SCORES + save.cell(row, slot) * fs.SCORE_BYTES


def box_score(save: fs.FranchiseSave, row: int, slot: int) -> BoxScore:
    game = save.game(row, slot)
    fs._require(game.played and game.scores is not None, f"{game.row_name} game {slot + 1} has not been played")
    first, second = game.scores
    return BoxScore(row, slot, game.home, game.away, tuple(first), tuple(second),     # type: ignore[arg-type]
                    row >= save.regular_season_weeks)


def box_scores(save: fs.FranchiseSave) -> list[BoxScore]:
    return [box_score(save, game.row, game.slot) for game in save.games() if game.played]


def _quarters(values: Sequence[int], side: str) -> tuple[int, ...]:
    out = tuple(values)
    fs._require(len(out) == len(QUARTERS), f"{side}: give five numbers (Q1, Q2, Q3, Q4, OT), not {len(out)}")
    for name, value in zip(QUARTERS, out):
        fs._require(type(value) is int and 0 <= value <= SCORE_MAX,
                    f"{side} {name}: {value!r} is outside 0..{SCORE_MAX} (one byte a quarter)")
    return out


TEAM_GAMES_PLAYED = fs.TEAM_GAMES_PLAYED
WIN_STREAK = fs.TEAM_STREAK_BYTES[3]           # team +0x1F1: the club's current winning streak (all played games)
OUTCOME_FIELDS = {"W": ("season_wins", "wins"), "L": ("season_losses", "losses"), "T": ("season_ties", "ties")}
_OUTCOME_WORDS = {"W": "win", "L": "loss", "T": "tie"}


def _outcome(mine: int, theirs: int) -> str:
    return "W" if mine > theirs else "L" if mine < theirs else "T"


def _club_games(save: fs.FranchiseSave, team: int, replace: BoxScore | None) -> list[tuple[int, int, int, int]]:
    """(row, slot, points scored, points allowed) of every played game of ``team`` in grid order, with ``replace`` in
    place of the saved quarters of its own cell."""

    out = []
    for box in box_scores(save):
        if replace is not None and (box.row, box.slot) == (replace.row, replace.slot):
            box = replace
        if team == box.home:
            out.append((box.row, box.slot, box.home_points, box.away_points))
        elif team == box.away:
            out.append((box.row, box.slot, box.away_points, box.home_points))
    return sorted(out)


def _win_streak(games: Sequence[tuple[int, int, int, int]]) -> int:
    run = 0
    for _row, _slot, mine, theirs in games:
        run = run + 1 if mine > theirs else 0
    return run


def plan_box_score(save: fs.FranchiseSave, row: int, slot: int, home_quarters: Sequence[int],
                   away_quarters: Sequence[int], *, season_points: bool = True) -> dict[str, Any]:
    """What ``set_box_score`` would write, in bytes and in words, and what it leaves as it is; nothing is written.

    With ``season_points`` (the default) the counters the game itself moves with every played game follow the edit
    (review F2, F3; evidence finn-r2/evidence/f3/ and rev-finn/REVIEW.md):

    * both clubs' points scored, points allowed and games played (team +0x1D8 / +0x1DA / +0x1DC) are recomputed from
      ALL their box scores: in both postseason saves examined the stored totals equal the sums over every played
      game, playoffs included, for all 32 clubs;
    * a regular-season result that changes moves each head coach's season W-L-T (coach +0x26/+0x28/+0x2A) and career
      W-L-T (+0x20/+0x22/+0x24) by one: across the native Week 1 of the signed 2026 franchise every club's coach moved
      both by exactly that club's result, and the season fields equal the regular-season record in five saves; it is
      done only when the coach's season record equals the club's regular-season record from its box scores (he coached
      every game) and he heads no other club, otherwise he is left alone and the plan says so;
    * the club's win streak (team +0x1F1) is recomputed from its played games in grid order: it equals that run for all
      32 clubs in five saves and moved +1 / to 0 with every Week 1 result; only when the stored value equals the run
      before the edit.
    A playoff game keeps its winner, so no coach record or bracket depends on it; the Pro Bowl (teams 32 and 33) counts
    in no club's totals."""

    current = box_score(save, row, slot)
    home_q, away_q = _quarters(home_quarters, "home"), _quarters(away_quarters, "away")
    new = BoxScore(row, slot, current.home, current.away, home_q, away_q, current.postseason)   # type: ignore[arg-type]
    if current.postseason:
        fs._require(new.winner is not None, "a playoff game cannot end in a tie")
        fs._require(new.winner == current.winner,
                    "a playoff game keeps its winner: the bracket has already moved the winner on")
    words: list[dict[str, Any]] = []                # {"offset", "width", "before", "after", "kind", "team", "text"}
    changes: list[str] = []
    kept: list[str] = ["Yards and the other season numbers stay as the game added them."]
    clubs = [t for t in (current.home, current.away) if 0 <= t < save.league_team_count]
    if not season_points:
        kept.insert(0, "Season totals, the head coaches' records and the win streaks are not changed (the option is off).")
    elif not clubs:
        kept.insert(0, "Pro Bowl scores count in no club's season totals.")
    else:
        coaches = {c.index: c for c in save.coaches()}
        regular = row < save.regular_season_weeks
        for team in clubs:
            name = save.team_abbreviation(team)
            base = save.team_offset(team)
            before_games, after_games = _club_games(save, team, None), _club_games(save, team, new)
            totals = (sum(g[2] for g in after_games), sum(g[3] for g in after_games), len(after_games))
            for rel, value, label in ((TEAM_POINTS_FOR, totals[0], "points scored"),
                                      (TEAM_POINTS_AGAINST, totals[1], "points allowed"),
                                      (TEAM_GAMES_PLAYED, totals[2], "games played")):
                stored = save.u16(base + rel)
                fs._require(0 <= value <= 0xFFFF, f"{name} {label} would be {value}")
                if stored != value:
                    words.append({"offset": base + rel, "width": 2, "before": stored, "after": value, "kind": "team",
                                  "team": team, "text": f"{name} {label} {stored} -> {value}"})
            stored_streak = save.u8(base + WIN_STREAK)
            streak_before, streak_after = _win_streak(before_games), _win_streak(after_games)
            if streak_after != streak_before:
                if stored_streak == streak_before and streak_after <= 0xFF:
                    words.append({"offset": base + WIN_STREAK, "width": 1, "before": stored_streak,
                                  "after": streak_after, "kind": "streak", "team": team,
                                  "text": f"{name} win streak {stored_streak} -> {streak_after}"})
                else:
                    kept.append(f"{name}'s win streak stays {stored_streak}: it does not match the club's box scores "
                                f"({streak_before}), so the Studio cannot tell what the game counted.")
            if not regular:
                continue
            mine = [g for g in before_games if g[0] < save.regular_season_weeks]
            game_before = next(g for g in before_games if g[:2] == (row, slot))
            game_after = next(g for g in after_games if g[:2] == (row, slot))
            was, now = _outcome(*game_before[2:]), _outcome(*game_after[2:])
            if was == now:
                continue
            record = tuple(sum(1 for g in mine if _outcome(*g[2:]) == r) for r in "WLT")
            index = save.head_coach_index(team)
            coach = coaches.get(index) if index is not None else None
            if coach is None:
                kept.append(f"{name} has no head coach record to update.")
                continue
            season = tuple(coach.fields[f] for f in ("season_wins", "season_losses", "season_ties"))
            if season != record or tuple(coach.teams) != (team,):
                why = ("his season record does not match the club's box scores, so he did not coach every game"
                       if season != record else "his coach record also leads another club")
                kept.append(f"{coach.name}'s ({name}) records stay as they are: {why}.")
                continue
            offset = save._coach_offset(coach.index)
            for outcome, step in ((was, -1), (now, +1)):
                for field_name in OUTCOME_FIELDS[outcome]:
                    rel, _fmt = fs.COACH_FIELDS[field_name]
                    stored = save.u16(offset + rel)
                    value = stored + step
                    fs._require(0 <= value <= 0xFFFF, f"{coach.name}'s {field_name} would be {value}")
                    words.append({"offset": offset + rel, "width": 2, "before": stored, "after": value,
                                  "kind": "coach", "team": team, "text": ""})
            changes.append(f"{coach.name} ({name}): one {_OUTCOME_WORDS[was]} becomes a {_OUTCOME_WORDS[now]} "
                           f"in his season and career records")
        if regular and save.games(rows=range(save.regular_season_weeks, fs.GRID_ROWS)):
            kept.append("The playoff bracket stays as it is: it was set from the standings before this change.")
    changes = [w["text"] for w in words if w["text"]] + changes
    offset = _score_offset(save, row, slot)
    return {"current": current, "new": new, "score_offset": offset,
            "score_bytes_before": bytes(save.buffer[offset:offset + fs.SCORE_BYTES]),
            "score_bytes_after": bytes(home_q + away_q), "words": words, "changes": changes, "kept": kept}


def set_box_score(save: fs.FranchiseSave, row: int, slot: int, home_quarters: Sequence[int],
                  away_quarters: Sequence[int], *, season_points: bool = True) -> dict[str, Any]:
    """Write one played game's quarter scores and, with ``season_points``, what ``plan_box_score`` lists; refusals
    change nothing."""

    plan = plan_box_score(save, row, slot, home_quarters, away_quarters, season_points=season_points)
    current, new, offset = plan["current"], plan["new"], plan["score_offset"]
    # every check is done; the writes follow
    save.buffer[offset:offset + fs.SCORE_BYTES] = plan["score_bytes_after"]
    for word in plan["words"]:
        struct.pack_into("<H" if word["width"] == 2 else "<B", save.buffer, word["offset"], word["after"])
    after_box = box_score(save, row, slot)
    fs._require((after_box.home_quarters, after_box.away_quarters) == (new.home_quarters, new.away_quarters),
                "the box score did not read back")
    def rows(kind: str) -> list[dict[str, Any]]:
        return [{"team": save.team_abbreviation(w["team"]), "offset": w["offset"], "before": w["before"],
                 "after": w["after"]} for w in plan["words"] if w["kind"] == kind]
    return {"operation": "set_box_score", "row": row, "slot": slot,
            "home": save.team_abbreviation(current.home), "away": save.team_abbreviation(current.away),
            "before": [current.away_points, current.home_points], "after": [new.away_points, new.home_points],
            "score_offset": offset, "score_bytes_before": plan["score_bytes_before"].hex(),
            "score_bytes_after": plan["score_bytes_after"].hex(),
            "season_points": rows("team"), "streaks": rows("streak"), "coaches": rows("coach"),
            "changes": plan["changes"], "kept": plan["kept"],
            "season_points_skipped": not season_points or not any(0 <= t < save.league_team_count
                                                                  for t in (current.home, current.away))}


def swap_played_sides(save: fs.FranchiseSave, row: int, slot: int) -> dict[str, Any]:
    """Swap home and away of a PLAYED game and its score halves, so each club keeps its own points.

    The plain cell swap (``set_game``) moves only the two team bytes; on a played game that hands each club the other's
    score.  The two flag bytes (home known, away known) are swapped with the teams."""

    current = box_score(save, row, slot)
    game = save.game(row, slot)
    flags_at = save.season_block + fs.S_GRID_FLAGS + save.cell(row, slot) * 2
    flags = save.u16(flags_at)
    save.set_game(row, slot, home=current.away, away=current.home, allow_played=True)
    offset = _score_offset(save, row, slot)
    save.buffer[offset:offset + fs.SCORE_BYTES] = bytes(current.away_quarters + current.home_quarters)
    struct.pack_into("<H", save.buffer, flags_at, ((flags & 0xFF) << 8) | (flags >> 8))
    after = box_score(save, row, slot)
    fs._require((after.home, after.away, after.home_points, after.away_points)
                == (current.away, current.home, current.away_points, current.home_points), "the swap did not read back")
    return {"operation": "swap_played_sides", "row": row, "slot": slot, "kind": game.kind,
            "home": save.team_abbreviation(after.home), "away": save.team_abbreviation(after.away)}


def scores_csv_text(save: fs.FranchiseSave) -> str:
    """Every played game's box score as CSV (week, away, home, five quarters a side, finals)."""

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["Week", "Game", "Away", "Home"] + [f"Away {q}" for q in QUARTERS] + [f"Home {q}" for q in QUARTERS]
                    + ["Away final", "Home final"])
    for box in box_scores(save):
        writer.writerow([save.schedule_row_name(box.row).title(), box.slot + 1, save.team_abbreviation(box.away),
                         save.team_abbreviation(box.home), *box.away_quarters, *box.home_quarters,
                         box.away_points, box.home_points])
    return buffer.getvalue()


# --------------------------------------------------------------------------------------------- dead cap (b81 R2, F9)
# Finn's *Clear Cap Penalty* zeroes one u32 at team +0x19C.  The game keeps SEVEN u16 dead-cap amounts there, one a season,
# $1000 units, index 0 = this season (RE_FACTS section 4: the adder 0x13ED30 puts a released player's unamortised bonus in
# slot [year] for a human-controlled club only; the rollover 0x13ED70 shifts every slot down one and zeroes the last).  The
# core module calls these seven words ``record_ring`` / ``set_team_record_ring``, a wrong name that stays inside the pinned
# core file; this module only uses them.  Finn's u32 is slot 0 plus 65536 x slot 1, so his button clears this season and
# next season's amount and shows a wrong total when next season has dead money; here all seven seasons are cleared and listed.
DEAD_CAP_SEASONS = fs.TEAM_RECORD_RING_COUNT


def dead_cap(save: fs.FranchiseSave, team: int) -> tuple[int, ...]:
    """A club's dead-cap amount for each of the next seven seasons, $1000 units, this season first."""

    fs._require(type(team) is int and 0 <= team < save.league_team_count, f"team {team!r} is not a league club")
    return tuple(int(v) for v in save.team_season(team).record_ring)


def clear_dead_cap(save: fs.FranchiseSave, team: int) -> dict[str, Any]:
    """Zero all seven seasons of a club's dead cap; only those 14 bytes can change."""

    before = dead_cap(save, team)
    for slot in range(DEAD_CAP_SEASONS):
        if before[slot]:
            save.set_team_record_ring(team, slot, 0)
    after = dead_cap(save, team)
    fs._require(after == (0,) * DEAD_CAP_SEASONS, "the dead cap did not read back as zero")
    return {"operation": "clear_dead_cap", "team": team, "abbreviation": save.team_abbreviation(team),
            "before": list(before), "after": list(after)}
