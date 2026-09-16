"""Authored football scheme data over beta-67's proved retail data levers.

Football descriptions are from general knowledge, without network research.
They are interpretations, not attributed coaching playbooks or game guarantees.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
import io
import json

from . import apf2k8_playcall_model as model
from . import apf2k8_splb_writer as splb
from . import apf2k8_team_tendency as tendency


@dataclass(frozen=True)
class Scheme:
    id: str
    name: str
    description: str
    run_percentage: int
    run_by_row: tuple[int, ...]
    personnel_preference: tuple[str, ...]
    category_rating_deltas: tuple[tuple[str, int], ...]
    formation_rating_deltas: tuple[int, int, int]
    run_row_deltas: tuple[int, ...]
    pass_row_deltas: tuple[int, ...]


def _scheme(key, name, description, run, rows, groups, ratings):
    return Scheme(key, name, description, run, rows, groups,
                  tuple((group, -1 if i < 2 else 0) for i, group in enumerate(groups)),
                  ratings, rows, tuple(100 - n for n in rows))


# Rows run from heavy/short (0) through spread/long (10). These are authored
# preferences; the game does not expose an independent CPU run slider per row.
SCHEMES = (
    _scheme("air_coryell", "Air Coryell", "Vertical passing with protected shots and a complementary run game.",
            42, (65, 62, 58, 53, 48, 43, 36, 29, 22, 16, 10), ("12", "21", "11"), (0, 0, -1)),
    _scheme("erhardt_perkins", "Erhardt-Perkins", "Multiple personnel, balanced runs and passes, adaptable presentation.",
            50, (72, 68, 64, 59, 54, 48, 42, 35, 28, 21, 14), ("12", "21", "11", "22"), (0, -1, 0)),
    _scheme("west_coast", "West Coast", "Timing passes and backs or tight ends as receiving options.",
            45, (68, 64, 60, 55, 49, 43, 38, 32, 26, 20, 14), ("21", "12", "11"), (0, -1, 0)),
    _scheme("west_coast_spread", "West Coast Spread", "Timing passes from wider personnel with a complementary run game.",
            40, (62, 59, 55, 49, 44, 38, 33, 27, 22, 17, 12), ("11", "10", "12"), (0, -1, -1)),
    _scheme("spread_to_run", "Spread-to-Run", "Spread personnel to open running space; preserve short-yardage options.",
            58, (78, 75, 71, 66, 60, 54, 47, 40, 32, 24, 16), ("11", "20", "10", "12"), (-1, -1, 0)),
    _scheme("wide_zone", "Wide Zone", "A zone-run emphasis with tight-end personnel and complementary passes.",
            57, (79, 76, 72, 67, 61, 54, 46, 38, 30, 22, 14), ("12", "21", "11"), (-1, 0, 1)),
    _scheme("power_gap", "Power/Gap", "Heavier personnel and a downhill running emphasis with passing complements.",
            62, (84, 81, 77, 72, 65, 58, 50, 42, 33, 24, 15), ("22", "23", "21", "12"), (-1, 0, 1)),
    _scheme("pro_spread", "Pro Spread", "Balanced pro passing and runs from three-receiver personnel.",
            48, (71, 67, 63, 58, 52, 46, 40, 33, 27, 20, 13), ("11", "12", "10", "21"), (0, -1, 0)),
)

LIMITS = (
    "Row weights feed the optional tendency cache, not the ordinary CPU category lottery.",
    "Run-by-row percentages are scheme intent; only the overall run percentage is a direct team slider.",
    "Category preference changes the mean of its formations' ratings; there is no separate stored category rating.",
    "Schemes select existing personnel and ratings; they do not add run concepts, routes, motion or blocking assignments.",
    "Tempo, snap count, weather ratio and coin-toss strategy have no proved authoring lever here.",
    "All in-game outcomes are UNWITNESSED.",
)


def get_scheme(scheme_id):
    for scheme in SCHEMES:
        if scheme.id == scheme_id:
            return scheme
    raise model.PlaycallError("Choose one of the eight offensive schemes")


def personnel_group(category):
    """Football notation: number of backs then tight ends, excluding the QB."""
    return str(sum(role in {"HB", "FB"} for role in category.roles)) + str(category.tight_ends)


def apply_scheme(book: bytes, master: bytes, rost: bytes, team: int, scheme_id: str):
    scheme = get_scheme(scheme_id)
    parsed = splb.parse_book(book, 0)
    categories = {c.id: c for c in model.category_table(master)}
    records = [r for r in parsed.records if r.populated and categories[r.category_index].row <= 10
               and r.formation_index < 151]
    if not records:
        raise model.PlaycallError("This book has no ordinary offensive formation; choose an offensive starting book")
    # Do not alias another team's tendency record through a shared +F8 pointer.
    target = tendency._record(rost, team)
    tables, _ = tendency.apf_roster.parse_root(rost)
    if any(i != team and tendency._record(rost, i) == target for i in range(tables[4].count)):
        raise model.PlaycallError("This team's tendency record is shared; use a roster with independent team tendencies")
    output = book
    edits = []
    available = sorted({personnel_group(categories[r.category_index]) for r in records})
    deltas = dict(scheme.category_rating_deltas)
    for form in dict.fromkeys(r.formation_index for r in records):
        record = next(r for r in records if r.formation_index == form)
        category = categories[record.category_index]
        group = personnel_group(category)
        category_delta = deltas.get(group, 1)
        before = splb.formation_ratings(output, form)
        after = tuple(max(1, min(7, value + category_delta + delta))
                      for value, delta in zip(before, scheme.formation_rating_deltas))
        output = splb.set_formation_ratings(output, form, after)
        if splb.formation_ratings(output, form) != after:
            raise model.PlaycallError("Scheme formation ratings failed readback")
        edits.append({"formation": form, "category": category.id, "personnel": group,
                      "category_delta": category_delta, "before": list(before), "after": list(after)})
    before_rows = tendency.row_weights(rost, team)
    after_rows = tuple(tuple(min(255, n + delta) for n, delta in zip(values, deltas_))
                       for values, deltas_ in zip(before_rows, (scheme.run_row_deltas, scheme.pass_row_deltas)))
    changed_rost = tendency.set_team_tendency(rost, team, scheme.run_percentage)
    changed_rost = tendency.set_row_weights(changed_rost, team, *after_rows)
    if tendency.row_weights(changed_rost, team) != after_rows:
        raise model.PlaycallError("Scheme row weights failed readback")
    receipt = {"scheme": asdict(scheme), "formations": edits, "available_personnel": available,
               "missing_preferred_personnel": [g for g in scheme.personnel_preference if g not in available],
               "run_percentage_before": tendency.team_tendency(rost, team),
               "run_percentage_after": tendency.team_tendency(changed_rost, team),
               "row_weights_before": before_rows, "row_weights_after": after_rows, "notes": LIMITS}
    # JSON round-trip gives the project recipe one portable representation.
    return output, changed_rost, json.loads(json.dumps(receipt))


@dataclass(frozen=True)
class Bucket:
    name: str
    down: int = 1
    distance: float = 10
    goal: float = 50
    period: int = 1
    clock: float = 900
    score: int = 0
    note: str = "Representative cold scrimmage; distance, jitter and urgency can change the row."
    picks: str = ""

    def situation(self):
        return model.Situation(self.down, self.distance, self.goal, self.period, self.clock, self.score, 3)


BUCKETS = (
    Bucket("Openers", note="No opener counter in the row selector; shares the down/distance row.", picks="15"),
    Bucket("1st and 10", picks="6"),
    Bucket("2nd and 2-3", 2, 2.5), Bucket("2nd and 4-6", 2, 5),
    Bucket("2nd and 7-10", 2, 8.5, note="9-11 yards on second down use the first-down calculation; not one exclusive row."),
    Bucket("2nd and 11+", 2, 15),
    Bucket("3rd and 2-3", 3, 2.5), Bucket("3rd and 4-6", 3, 5),
    Bucket("3rd and 7-10", 3, 8.5), Bucket("3rd and 11+", 3, 15),
    Bucket("4th down", 4, 2, note="Scrimmage representative only; separate punt/FG predicates can override it."),
    Bucket("Short yardage", 3, 1),
    Bucket("Red zone 25-21", goal=23, note="No distinct red-zone bucket in the ordinary row selector."),
    Bucket("Red zone 20-16", goal=18, note="No distinct red-zone bucket in the ordinary row selector."),
    Bucket("Red zone 15-11", goal=13, note="No distinct red-zone bucket in the ordinary row selector."),
    Bucket("Red zone 10 and in", goal=7, note="No distinct red-zone bucket; this uses first-and-10 at the seven, not goal-to-go."),
    Bucket("Goal line", 1, 1, 1, picks="2"),
    Bucket("2pt", 4, 2, 2, note="Proxy only: try phase can request row 19 or substitute down 4; not modeled by this scrimmage preview.", picks="2"),
    Bucket("Backed-up", goal=97, note="Field position can change formation weights; no dedicated backed-up row.", picks="4"),
    Bucket("After negative play", 2, 15, note="No named negative-play bucket; distance changes and learned history are separate inputs.", picks="5"),
    Bucket("Sudden change", note="No turnover/opener bucket; uses the current down, distance, clock and score.", picks="5"),
    Bucket("4-minute", period=4, clock=240, score=7, note="Clock/score affect native urgency and special calls; this cold preview omits those paths."),
    Bucket("2-minute", period=4, clock=120, score=-7, note="Clock/score affect native urgency and special calls; this cold preview omits those paths."),
)


def _cell(value):
    value = str(value)
    return "'" + value if value.startswith(("=", "+", "-", "@", "\t", "\r")) else value


def spreadsheet(book, master, run_percentage, *, team_name, scheme_id=None, preview_only=False):
    """CSV of actual staged book predictions, with separate coaching intent."""
    scheme = get_scheme(scheme_id) if scheme_id is not None else None
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(("Team", "Book", "Last applied scheme", "Bucket", "Requested picks (planning only)",
                     "Down", "Distance", "Yards to goal", "Quarter", "Seconds", "Score margin", "Engine row (proxy)",
                     "Neutral jitter rows", "Scheme intent run % (not a row override)", "Preview run %" if preview_only else "Stored team run %",
                     "Modeled adjusted run %", "Preferred personnel", "Personnel probabilities", "Formation probabilities",
                     "Play probabilities", "Limits"))
    name = splb.parse_book(book, 0).name
    for bucket in BUCKETS:
        s = bucket.situation()
        call = model.predict_offense(book, master, run_percentage / 100, s, seeds=256)
        rows = sorted({model.requested_offense_row(s, u) for u in (0, .5, 1)})
        def distribution(values):
            return "; ".join(f"{i}: {n} {p:.2%}" for i, n, p in values)
        values = (team_name, name, scheme.name if scheme else "None", bucket.name, bucket.picks,
                  s.down, s.distance_yards, s.yards_to_goal, s.period, s.clock_seconds, s.score_margin,
                  call.requested_row, "/".join(map(str, rows)), scheme.run_by_row[call.requested_row] if scheme else "",
                  run_percentage, round(100 * model.adjusted_run_share(run_percentage / 100, s), 2),
                  "/".join(scheme.personnel_preference) if scheme else "", distribution(call.categories),
                  distribution(call.formations), distribution(call.plays), " ".join((bucket.note, *LIMITS, *call.notes)))
        writer.writerow(tuple(_cell(v) for v in values))
    return stream.getvalue().encode("utf-8-sig")
