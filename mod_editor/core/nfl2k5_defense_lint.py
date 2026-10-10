"""Defensive formation linter for NFL 2K5 PLAY books (beta 77, GOAL P5).

Checks every defensive formation (types 4-7) of a PLAY resource, or one authored formation, against alignment rules
that all 32 retail team books satisfy:

* ``DEF_SPACING``: no two defenders closer than 1.7 yd (retail team books: 2.21 yd minimum).
* ``DEF_MIDDLE_STANDING``: no standing (stance 1) linebacker or back inside the tackles within 2 yd of the ball,
  unless the formation is a named pressure look (its name contains "Mug" or "Double A"). Retail has none.
* ``DEF_PRESSURE_AS_BASE``: a named pressure look must not be the only formation of its personnel group (the CPU
  would then call it on every snap against that personnel; the v0.5 "Nickel Mug").
* ``DEF_NO_EDGE``: each side of the ball needs a defender on the line (within 1.2 yd) outside the tackle; a front
  with nobody outside the tackle on one side is lopsided (the v0.5 "Tite Look").
* ``DEF_ACROSS_LINE``: nobody lines up in the offensive backfield.

Positions are centimetres (+x = offense's right, z = depth off the ball toward the defense's goal). Pure Python, no
game data is bundled; the caller supplies the resource or the formation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Iterable, Sequence

from . import nfl2k5_play_codec as codec

YD = codec.YD_CM
MIN_SPACING_CM = 1.7 * YD
TACKLE_X_CM = 304.8                 # retail offensive tackles at +-304 cm
MIDDLE_DEPTH_CM = 2.0 * YD
EDGE_DEPTH_CM = 1.2 * YD
STANDING = 1
DL_KINDS = frozenset({12, 13})
PRESSURE_WORDS = ('mug', 'double a')
SCHEMA = 'nfl2k5_defense_lint/v1'
ERROR_CODES = frozenset({'DEF_SPACING', 'DEF_MIDDLE_STANDING', 'DEF_PRESSURE_AS_BASE', 'DEF_NO_EDGE',
                         'DEF_ACROSS_LINE'})

# Technique centres in cm (one third of the engine's 5 ft line split per shade): label, |x| centre.
TECHNIQUES = (('0', 0), ('1', 50), ('2i', 100), ('2', 152), ('3', 205), ('4i', 255), ('4', 304), ('5', 360),
              ('7', 410), ('6', 457), ('9', 515), ('wide 9', 600))


@dataclass(frozen=True)
class LintFinding:
    code: str
    message: str
    formation_index: int | None = None
    formation: str = ''
    slots: tuple[int, ...] = ()

    @property
    def severity(self) -> str:
        return 'error' if self.code in ERROR_CODES else 'warning'

    def to_json(self) -> dict:
        return dict(code=self.code, severity=self.severity, message=self.message,
                    formation_index=self.formation_index, formation=self.formation, slots=list(self.slots))


@dataclass
class DefenseFormation:
    name: str
    positions: Sequence[tuple[float, float]]
    codes: Sequence[int]
    stances: Sequence[int]
    index: int | None = None
    category_index: int | None = None
    type_code: int = 5


def is_pressure_name(name: str) -> bool:
    low = name.lower()
    return any(w in low for w in PRESSURE_WORDS)


def technique(x_cm: float) -> str:
    """Nearest technique label for a lineman at lateral x (side-agnostic)."""
    ax = abs(x_cm)
    label = min(TECHNIQUES, key=lambda t: abs(t[1] - ax))[0]
    if ax > 640:
        label = 'wide'
    return label


def formation_findings(f: DefenseFormation, *, sole_in_category: bool = False) -> list[LintFinding]:
    out: list[LintFinding] = []
    pts = [(float(x), float(z)) for x, z in f.positions]
    kinds = [c & 31 for c in f.codes]
    label = lambda s: codec.position_label(f.codes[s])
    for a in range(11):
        if pts[a][1] < -15:
            out.append(LintFinding('DEF_ACROSS_LINE', f'{label(a)} (slot {a}) lines up {(-pts[a][1]) / YD:.1f} yd in '
                                   'the offensive backfield', f.index, f.name, (a,)))
        for b in range(a + 1, 11):
            d = math.hypot(pts[a][0] - pts[b][0], pts[a][1] - pts[b][1])
            if d < MIN_SPACING_CM:
                out.append(LintFinding('DEF_SPACING', f'{label(a)} (slot {a}) and {label(b)} (slot {b}) are '
                                       f'{d / YD:.2f} yd apart (minimum 1.7 yd)', f.index, f.name, (a, b)))
    middle = [s for s in range(11) if kinds[s] not in DL_KINDS and f.stances[s] == STANDING
              and abs(pts[s][0]) < TACKLE_X_CM and 0 <= pts[s][1] <= MIDDLE_DEPTH_CM]
    pressure = is_pressure_name(f.name)
    if middle and not pressure:
        out.append(LintFinding('DEF_MIDDLE_STANDING', 'standing defender(s) inside the tackles within 2 yd of the '
                               'ball: ' + ', '.join(f'{label(s)} at ({pts[s][0] / YD:+.2f}, {pts[s][1] / YD:.2f}) yd'
                                                    for s in middle) + ' (only a named Mug pressure look may do this)',
                               f.index, f.name, tuple(middle)))
    if pressure and sole_in_category:
        out.append(LintFinding('DEF_PRESSURE_AS_BASE', f'"{f.name}" is a pressure look but the only formation of its '
                               'personnel group, so the CPU would call it on every snap against that personnel',
                               f.index, f.name, tuple(middle)))
    if 4 <= f.type_code <= 5:
        for side, word in ((-1, 'left (-x)'), (1, 'right (+x)')):
            edge = [s for s in range(11) if pts[s][0] * side >= TACKLE_X_CM and pts[s][1] <= EDGE_DEPTH_CM]
            if not edge:
                out.append(LintFinding('DEF_NO_EDGE', f'nobody on the line outside the {word} tackle', f.index,
                                       f.name, ()))
    return out


def resource_formations(resource: bytes) -> list[DefenseFormation]:
    from . import nfl2k5_play_library as lib
    from . import nfl2k5_playbook_inspector as insp
    book = insp.parse_playbook_resource(resource)
    body = resource[insp.RESOURCE_HEADER_SIZE:]
    out = []
    for formation in book.formations:
        rec = lib.formation_record(body, formation.index)
        if not 4 <= rec.type_code <= 7:
            continue
        cat = lib.formation_category(body, formation.index)
        out.append(DefenseFormation(formation.name.strip(), [(s.x[0], s.z[0]) for s in rec.slots],
                                    lib.category_positions(body, cat), [s.stance for s in rec.slots],
                                    formation.index, cat, rec.type_code))
    return out


def lint_formations(formations: Iterable[DefenseFormation]) -> list[LintFinding]:
    formations = list(formations)
    per_category: dict[int | None, int] = {}
    for f in formations:
        per_category[f.category_index] = per_category.get(f.category_index, 0) + 1
    out = []
    for f in formations:
        out.extend(formation_findings(f, sole_in_category=per_category.get(f.category_index, 0) == 1))
    return out


def lint_resource(resource: bytes) -> list[LintFinding]:
    return lint_formations(resource_formations(resource))


def front_diagram(f: DefenseFormation, width: int = 61) -> str:
    """ASCII picture of a defensive formation over a five-man offensive line (one column per 0.5 yd)."""
    rows: dict[int, list[str]] = {}
    half = width // 2

    def put(x_cm: float, z_cm: float, text: str) -> None:
        col = half + int(round(x_cm / (YD / 2)))
        row = int(round(z_cm / YD))
        line = rows.setdefault(row, [' '] * width)
        for i, ch in enumerate(text):
            if 0 <= col + i < width:
                line[col + i] = ch

    for s, (x, z) in enumerate(f.positions):
        if abs(x) <= 16 * YD and z <= 14 * YD:
            put(x - YD / 4, z, _short(f.codes[s], f.stances[s]))
    oline = [' '] * width
    for x in (-304.8, -152.4, 0.0, 152.4, 304.8):
        col = half + int(round(x / (YD / 2)))
        oline[col] = 'O'
    lines = [''.join(rows[r]).rstrip() for r in sorted(rows, reverse=True)]
    lines.append(''.join(oline).rstrip() + '   <- offensive line (C, G, T)')
    return '\n'.join(lines)


def _short(code: int, stance: int) -> str:
    kind = code & 31
    return {12: 'E', 13: 'T', 14: 'M', 15: 'B', 16: 'F', 17: 'S', 18: 'C'}.get(kind, '?') + ('' if stance != STANDING
                                                                                            or kind in DL_KINDS else '')
