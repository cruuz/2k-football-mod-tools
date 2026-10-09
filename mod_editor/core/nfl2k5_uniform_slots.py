"""Uniform style slots per franchise: what the game offers, which slots history owns, and the 2026 alternates plan.

USA Xbox. Job u3s (beta 77, 2026-10-07). Read-only analysis plus the roster label edits; nothing here writes a disc.

What the game does (PROVED OFFLINE: the routines below run under Unicorn on the retail and the SOFTDRINK v0.5
``default.xbe`` with every team record of the disc, ``tools/b77/u3s_slots.py cycle``):

* A style is a uniform set index 0..14 per franchise. It keys the two kit packages ``<code><h|a><S>.iff`` and the
  style members of the three streamed aggregates (logos.cdf ``logo_ helm_a helm_h unif_a unif_h``, mini.cdf
  ``logo_s mini_h mini_a``, flipchip.cdf ``<code>_flipchip_00_h<S>``).
* The team record carries 14 (first, last) u16 year pairs for styles 1..14 at +0x15A and a default style byte at
  +0x192. ``FUN_000e2a90`` says a style exists when it is 0 or its pair is non-zero.
* Team Select and Controller Assign change a side's style only through the four handlers 0xE2FB0/0xE2F70 (home
  next/prev) and 0xE3090/0xE3050 (away): step to the next or previous existing style, never wrap. So a team offers
  0 and then every style whose pair is non-zero, in index order. A zero pair is skipped, so the table does not
  have to be a gapless prefix (a pair at 13 is offered after 11 when 12 is zero).
* ``FUN_000e3530`` names the style: 0 ``Current Uniform``; first == last ``%d Uniform``; last < 1900
  ``%d  Alternate %d`` (two spaces, the retail format); otherwise ``%d - %d Uniform``.
* The kit loader (0x615A0) builds ``"%s%c%d.iff"`` from the asset code, the h/a letter and
  ``FUN_000e2f20(team, slot)``: the slot stepped down to the nearest existing style.
* Team Select prefetches ``unif`` cards for the selected style and its neighbours (0x2C12C4) and ``helm`` cards
  for the neighbouring teams' default style byte, so every offered style needs its own three cards.
* The CPU never picks a style. Every game setup writes 0 to both slots (0x63A47, 0x77CA2, 0x134091 Pro Bowl,
  0x15DBA6 franchise game setup, 0x2C0AE2 Team Select, 0x2C535C, 0x2C548C, 0x2C560C). Only these set another
  value: 0x2C1780 (a historic team starts on its style byte), 0x20CBF8 (an Anniversary moment uses its SITU kit
  fields +0x58 away and +0x5C home) and 0x28FAA1 (a saved game restores its pair). So a CPU team wears style 0
  unless the player cycles it on Team Select or Controller Assign.

Which slots are safe to give a 2026 alternate (``census``/``free_slots``): style 0 is the 2026 primary set; a style
is owned by history when a historic team file (the 75 retail ones and the Anniversary moments' own files) has it as
its style byte, when a SITU moment side uses it as its kit, or when it is the franchise's spare style (job m1,
``nfl2k5_historic_styles``: the retail style-0 copy past the table). Every other style is free: a retail
``20xx Alternate`` set, a retail kit past the table with no pair (the Bengals' 6 and 7, the Jets' 7: art and kits
exist, the pair is zero), a retail era set, or a new index past the spare (needs new kit files and aggregate
members: not built here).

Franchise saves embed the roster arena with the team records, so a MyNFL save made before a relabel keeps the old
label text (it still loads the new art from the disc); a style enabled only in the new roster is not offered in an
older save. (INFERRED from the save layout; not run in game.)
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence

OWNER = "nfl2k5_uniform_slots"
TABLE = 0x15A                 # team record: 14 (first, last) u16 pairs for styles 1..14
STYLE_BYTE = 0x192            # team record: the default style
MAX_STYLE = 14
TEAM_SIZE = 0x1F4
ALTERNATE_YEAR = 2026         # the 2026 alternates read "2026  Alternate n" (job u7's Rams precedent)

# The 32 NFL franchises by asset code, with the 2026 abbreviation (data/nfl2k5_teams_2026/<abbr>.json).
FRANCHISES = {
    "00": "ARI", "01": "ATL", "02": "BAL", "03": "BUF", "04": "CAR", "05": "CHI", "06": "CIN", "07": "DAL",
    "08": "DEN", "09": "DET", "10": "GB", "11": "IND", "12": "JAX", "13": "KC", "14": "MIA", "15": "MIN",
    "16": "NE", "17": "NO", "18": "NYG", "19": "NYJ", "20": "LV", "21": "PHI", "22": "PIT", "23": "LAR",
    "24": "LAC", "25": "SF", "26": "SEA", "27": "TB", "28": "TEN", "29": "WAS", "30": "CLE", "37": "HOU",
}
# SITU rows name a franchise by its (historic) nickname.
SELECTOR_CODES = {
    "cardinals": "00", "falcons": "01", "ravens": "02", "bills": "03", "panthers": "04", "bears": "05",
    "bengals": "06", "cowboys": "07", "broncos": "08", "lions": "09", "packers": "10", "colts": "11",
    "jaguars": "12", "chiefs": "13", "dolphins": "14", "vikings": "15", "patriots": "16", "saints": "17",
    "giants": "18", "jets": "19", "raiders": "20", "eagles": "21", "steelers": "22", "rams": "23",
    "chargers": "24", "49ers": "25", "seahawks": "26", "buccaneers": "27", "oilers": "28", "titans": "28",
    "redskins": "29", "browns": "30", "texans": "37",
}
METHODS = ("repurpose", "enable_orphan", "append", "authored")


class UniformSlotsError(ValueError):
    """A plan touches a slot it does not own, or a disc does not have the expected layout."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise UniformSlotsError(message)


# ----------------------------------------------------------------------------------------------- the game's rules

def style_label(style: int, first: int = 0, last: int = 0) -> str:
    """The label FUN_000e3530 shows for a style (PROVED OFFLINE against the game's own formatter)."""
    if style == 0:
        return "Current Uniform"
    if first == last or first == 0:
        return f"{last} Uniform"
    if last < 1900:
        return f"{first}  Alternate {last}"
    return f"{first} - {last} Uniform"


def team_pairs(record: bytes, offset: int = 0) -> list[tuple[int, int]]:
    """The 14 (first, last) pairs of a team record (styles 1..14)."""
    return [struct.unpack_from("<HH", record, offset + TABLE + 4 * k) for k in range(MAX_STYLE)]


def style_exists(pairs: Sequence[tuple[int, int]], style: int) -> bool:
    """FUN_000e2a90."""
    return style == 0 or (1 <= style <= MAX_STYLE and tuple(pairs[style - 1]) != (0, 0))


def offered_styles(pairs: Sequence[tuple[int, int]]) -> list[int]:
    """The order Team Select and Controller Assign step through (0xE2FB0 from 0 until it stops)."""
    return [0] + [s for s in range(1, MAX_STYLE + 1) if style_exists(pairs, s)]


def loaded_style(pairs: Sequence[tuple[int, int]], slot: int) -> int:
    """FUN_000e2f20: the kit index the loader uses for a requested slot."""
    while slot > 0 and not style_exists(pairs, slot):
        slot -= 1
    return slot


def offered_labels(pairs: Sequence[tuple[int, int]]) -> list[tuple[int, str]]:
    return [(s, style_label(s, *(pairs[s - 1] if s else (0, 0)))) for s in offered_styles(pairs)]


def is_retail_alternate(pair: tuple[int, int]) -> bool:
    first, last = pair
    return first != last and first != 0 and last < 1900


# ----------------------------------------------------------------------------------------------- the disc census

@dataclass
class Franchise:
    code: str
    abbreviation: str
    team_index: int                       # record ordinal in the main roster (alphabetical by nickname)
    pairs: list[tuple[int, int]]          # the main roster's table (what current teams offer)
    retail_pairs: list[tuple[int, int]] | None = None
    kits: dict[int, tuple[int, int]] = field(default_factory=dict)        # style -> (h size, a size)
    retail_kits: set[int] = field(default_factory=set)                    # styles with kits on the retail disc
    members: dict[int, int] = field(default_factory=dict)                 # style -> aggregate members present (of 9)
    owners: dict[int, list[str]] = field(default_factory=dict)            # style -> reasons it must stay

    @property
    def table_styles(self) -> list[int]:
        return [s for s in range(1, MAX_STYLE + 1) if style_exists(self.pairs, s)]


def _situ_code(selector: str) -> str | None:
    return SELECTOR_CODES.get(selector.lower())


def census(disc: Path, retail: Path | None = None) -> dict[str, Franchise]:
    """Per franchise: its table, kits, aggregate members and every owner of a style, read from a disc image or an
    extracted game folder (``retail``: the retail source, to tell orphans and spares apart)."""
    from . import nfl2k5_historic_styles as hs
    from . import nfl2k5_espn25_more_moments as mm

    def read(path: Path):
        out = {}
        with hs.Source(path) as src:
            main = src.get(identity=hs.ROSTER_OUTER_ID)
            body = main[32:]
            records = hs.team_records(main)[:32]
            hashes = {}
            for aggregate in hs.AGGREGATES:
                hashes[aggregate["name"]] = set(hs.parse_record(src.get(identity=aggregate["record"]))[2])
            for index, (at, code) in enumerate(records):
                require(code in FRANCHISES, f"team record {index} has asset code {code!r}")
                f = Franchise(code, FRANCHISES[code], index, team_pairs(body, at))
                for s in range(MAX_STYLE + 1):
                    sizes = []
                    for side in "ha":
                        e = src.by_id.get(hs.name_id(f"{code}{side}{s}.iff"))
                        sizes.append(None if e is None else e.size)
                    if None not in sizes:
                        f.kits[s] = (sizes[0], sizes[1])
                    present = sum(hs.member_hash(p.format(c=code, s=s)) in hashes[a["name"]]
                                  for a in hs.AGGREGATES for p in a["members"])
                    if present:
                        f.members[s] = present
                out[code] = f
            historic = {}
            for d in mm._retail_descriptors(main):
                if src.has(d["filename"]):
                    historic[d["filename"]] = src.get(d["filename"])
            situ = src.get(identity=hs.SITU_OUTER_ID)
            rows = hs.situ_sides(situ)
            for _row, _side, selector, season, _kit, _field in rows:
                for code in out:
                    name = f"h-{code}-{season}-{selector}-9.iff"
                    if name not in historic and src.has(name):
                        historic[name] = src.get(name)
        return out, historic, rows

    franchises, historic, rows = read(Path(disc))
    if retail is not None:
        retail_franchises, _h, _r = read(Path(retail))
        for code, f in franchises.items():
            f.retail_pairs = retail_franchises[code].pairs
            f.retail_kits = set(retail_franchises[code].kits)
    for code, f in franchises.items():
        f.owners.setdefault(0, []).append("2026 primary set (style 0)")
        for s in f.table_styles:
            first, last = f.pairs[s - 1]
            if first == ALTERNATE_YEAR and last < 1900:
                f.owners.setdefault(s, []).append(f"2026 alternate already on the disc ({style_label(s, first, last)})")
    from . import nfl2k5_historic_styles as hs
    for name, raw in sorted(historic.items()):
        code, style = hs.historic_style(raw)
        if code in franchises:
            franchises[code].owners.setdefault(style, []).append(f"historic team file {name} (style byte)")
    for row, side, selector, season, kit, _field in rows:
        code = _situ_code(selector)
        if code in franchises:
            franchises[code].owners.setdefault(kit, []).append(
                f"Anniversary moment row {row + 1} {side} ({selector} {season}) kit")
    for code, f in franchises.items():
        if f.retail_kits:
            for s in sorted(set(f.kits) - f.retail_kits):
                f.owners.setdefault(s, []).append("m1 spare style (retail style-0 copy for historic teams)")
        if code == hs.EAGLES and f.retail_kits:
            f.owners.setdefault(hs.EAGLES_SPARE, []).append("m1 spare style (era 9 overwritten in place)")
    return franchises


def free_slots(f: Franchise) -> dict[str, list[int]]:
    """The styles a 2026 alternate may take, by class (in the order a plan should prefer them)."""
    owned = set(f.owners)
    table = set(f.table_styles)
    retail_kits = f.retail_kits or set(f.kits)
    alternates = [s for s in sorted(table - owned) if is_retail_alternate(f.pairs[s - 1])]
    eras = [s for s in sorted(table - owned) if not is_retail_alternate(f.pairs[s - 1])]
    orphans = [s for s in sorted(retail_kits - table - owned - {0}) if s in f.kits and f.members.get(s) == 9]
    append = [s for s in range(1, MAX_STYLE + 1) if s not in f.kits and s not in table and s not in owned]
    return {"retail_alternates": alternates, "orphans": orphans, "eras": eras, "append": append}


# ----------------------------------------------------------------------------------------------- the plan

def validate_plan(plan: Mapping, franchises: Mapping[str, Franchise]) -> list[str]:
    """Every problem with a slot plan (``reports/u3s_SLOT_PLAN.json`` shape): an empty list means it is safe.

    Rules: a slot is used once; it is never owned by history (``owners``) unless the method is ``authored`` (a
    2026 alternate that already ships, the Rams' 10-12); ``repurpose`` needs an existing style with both kits and
    all nine members; ``enable_orphan`` needs both kits and nine members with a zero pair; ``append`` needs an
    index with no kits, no pair and no owner; labels are unique per team."""
    problems = []
    teams = plan.get("teams") or {}
    for code, f in franchises.items():
        entry = teams.get(f.abbreviation)
        if entry is None:
            problems.append(f"{f.abbreviation}: missing from the plan")
            continue
        seen, labels = set(), set()
        for a in entry.get("assignments") or []:
            style, method = a.get("style"), a.get("method")
            where = f"{f.abbreviation} style {style}"
            if type(style) is not int or not 1 <= style <= MAX_STYLE:
                problems.append(f"{where}: not a style 1..14")
                continue
            if method not in METHODS:
                problems.append(f"{where}: unknown method {method!r}")
                continue
            if style in seen:
                problems.append(f"{where}: used twice")
            seen.add(style)
            owners = [o for o in f.owners.get(style, []) if not o.startswith("2026 primary")]
            if method != "authored" and owners:
                problems.append(f"{where}: owned by {owners[0]}")
            exists = style_exists(f.pairs, style)
            has_art = style in f.kits and f.members.get(style) == 9
            if method == "repurpose" and not (exists and has_art):
                problems.append(f"{where}: repurpose needs an existing style with its kits and nine members")
            if method == "enable_orphan" and (exists or not has_art):
                problems.append(f"{where}: enable_orphan needs a zero pair with kits and nine members")
            if method == "append" and (exists or style in f.kits):
                problems.append(f"{where}: append needs an index with no pair and no kits")
            if method == "authored" and not (exists and has_art):
                problems.append(f"{where}: an authored alternate must exist on the disc")
            label = a.get("label_after") or style_label(style, *(a.get("pair") or (0, 0)))
            if label in labels:
                problems.append(f"{where}: label {label!r} used twice")
            labels.add(label)
            pair = a.get("pair")
            if pair is not None and not (isinstance(pair, (list, tuple)) and len(pair) == 2 and tuple(pair) != (0, 0)):
                problems.append(f"{where}: pair {pair!r} must be two non-zero-together numbers")
    return problems


def roster_team_entries(plan: Mapping, franchises: Mapping[str, Franchise], *,
                        methods: Iterable[str] = ("repurpose", "enable_orphan")) -> list[dict]:
    """The roster-edits ``teams`` entries (``nfl2k5_roster_records.apply_team_uniform_years``) for the plan's
    assignments of the given methods: each style's new year pair, and ``enable_styles`` for the orphans."""
    wanted = set(methods)
    out = []
    by_abbr = {f.abbreviation: f for f in franchises.values()}
    for abbr, entry in sorted((plan.get("teams") or {}).items()):
        f = by_abbr.get(abbr)
        if f is None:
            continue
        years, enable = {}, []
        for a in entry.get("assignments") or []:
            if a.get("method") not in wanted or a.get("pair") is None:
                continue
            years[str(a["style"])] = [int(a["pair"][0]), int(a["pair"][1])]
            if a["method"] == "enable_orphan":
                enable.append(int(a["style"]))
        if years:
            row = {"team_index": f.team_index, "uniform_years": years}
            if enable:
                row["enable_styles"] = sorted(enable)
            out.append(row)
    return out


def plan_pairs(f: Franchise, entry: Mapping, *, methods: Iterable[str] = METHODS) -> list[tuple[int, int]]:
    """The franchise's table after the plan (for the cycle emulation and the readable table)."""
    pairs = [tuple(p) for p in f.pairs]
    for a in entry.get("assignments") or []:
        if a.get("method") in set(methods) and a.get("pair") is not None:
            pairs[a["style"] - 1] = (int(a["pair"][0]), int(a["pair"][1]))
    return pairs
