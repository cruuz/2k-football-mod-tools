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
the standings are counted from them, the game's records follow the edit.  The season counters do not: they are running
totals the game added when the game was played.  By default the edit also moves both clubs' points scored (``+0x1D8``)
and points allowed (``+0x1DA``) by the change, which keeps them equal to the sum of the club's box scores, as the
game's own saves are (all 32 clubs of a simulated SOFTDRINK 2026 regular season); yards and the other counters are left
alone.  A playoff box score may change its quarters but not its winner (the bracket has already moved the winner on),
and its season points are not moved (whether playoff games count in the season totals has not been checked).

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
               note="The season record keeps pass plays, not attempts, so this divides by pass plays."),
    _count("RUSH", "RUSH", 0x50, "yards"),
    StatColumn("AVGRUSH", "AVG RUSH", "Rushing yards per rushing play", "average", (0x50,), (0x26,),
               note="The season record keeps rushing plays, not carries, so this divides by rushing plays."),
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
    writer.writerow(["Team", "W-L-T", "GP"] + [column.caption for column in columns])
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


def set_box_score(save: fs.FranchiseSave, row: int, slot: int, home_quarters: Sequence[int],
                  away_quarters: Sequence[int], *, season_points: bool = True) -> dict[str, Any]:
    """Write one played game's quarter scores; refusals change nothing.

    ``season_points`` also moves both clubs' points scored / allowed by the change (regular season only)."""

    current = box_score(save, row, slot)
    home_q, away_q = _quarters(home_quarters, "home"), _quarters(away_quarters, "away")
    new = BoxScore(row, slot, current.home, current.away, home_q, away_q, current.postseason)   # type: ignore[arg-type]
    if current.postseason:
        fs._require(new.winner is not None, "a playoff game cannot end in a tie")
        fs._require(new.winner == current.winner,
                    "a playoff game keeps its winner: the bracket has already moved the winner on")
    for team in (current.home, current.away):
        fs._require(0 <= team < save.league_team_count, f"team {team} is not a league club")
    moves: list[tuple[int, int, int, int]] = []     # (offset, before, after, team)
    apply_points = season_points and not current.postseason
    if apply_points:
        home_delta = new.home_points - current.home_points
        away_delta = new.away_points - current.away_points
        for team, scored, allowed in ((current.home, home_delta, away_delta), (current.away, away_delta, home_delta)):
            base = save.team_offset(team)
            for rel, delta in ((TEAM_POINTS_FOR, scored), (TEAM_POINTS_AGAINST, allowed)):
                if delta:
                    before = save.u16(base + rel)
                    after = before + delta
                    fs._require(0 <= after <= 0xFFFF, f"{save.team_abbreviation(team)} season points would be {after}, "
                                                      "outside 0..65535; untick the season points option")
                    moves.append((base + rel, before, after, team))
    offset = _score_offset(save, row, slot)
    before_bytes = bytes(save.buffer[offset:offset + fs.SCORE_BYTES])
    # every check is done; the writes follow
    save.buffer[offset:offset + fs.SCORE_BYTES] = bytes(home_q + away_q)
    for at, _before, after, _team in moves:
        struct.pack_into("<H", save.buffer, at, after)
    after_box = box_score(save, row, slot)
    fs._require((after_box.home_quarters, after_box.away_quarters) == (home_q, away_q), "the box score did not read back")
    return {"operation": "set_box_score", "row": row, "slot": slot,
            "home": save.team_abbreviation(current.home), "away": save.team_abbreviation(current.away),
            "before": [current.away_points, current.home_points], "after": [new.away_points, new.home_points],
            "score_offset": offset, "score_bytes_before": before_bytes.hex(),
            "score_bytes_after": bytes(home_q + away_q).hex(),
            "season_points": [{"team": save.team_abbreviation(team), "offset": at, "before": before, "after": after}
                              for at, before, after, team in moves],
            "season_points_skipped": bool(season_points and current.postseason)}


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
