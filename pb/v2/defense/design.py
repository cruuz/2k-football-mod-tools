#!/usr/bin/env python3
"""SOFTDRINK defense v2: fronts, alignments and team schemes (DESIGN tables, all numbers in cm).

Authored frame (PROVED OFFLINE, see library.py): -x is the offense's strength (TE side) once 0x20B820 has matched
the offense's mirror bit; +x is the weak side. Depth z is yards off the ball toward the defense's goal (0 = on the
line). Linemen keep their native stance (3, hand down) and linebackers/defensive backs keep theirs (1, standing),
because the pack writer keeps each slot's stance byte from the native formation record.

Technique centres (one third of the engine's 5 ft line split per shade; guards at +-152, tackles at +-304, an inline
TE at -457): 0 = 0, 1 = 50, 2i = 100, 2 = 152, 3 = 205, 4i = 255, 4 = 304, 5 = 360, 7 = 410, 6 = 457, 9 = 515,
wide 5 (no TE) = 430, wide 9 = 560.

Every alignment below is checked by mod_editor/core/nfl2k5_defense_lint.py: no two defenders closer than 1.7 yd, no
standing defender inside the tackles within 2 yd of the ball unless the formation is a named pressure look (Mug).

Odd fronts (b776 de2, Noah's rule: EDGE players rush on base calls and drop only on a designed zone blitz): the OLB-kind
slots of a three-down formation are its edge rushers and stand on the edge in every formation.  Their coverage scripts are
retail scripts turned by pb/v2/defense/okie.py (an edge that dropped into the flat now rushes, its zone goes to the nearest
underneath defender); a call where one edge still covers must have a back blitzing in his place (DESIGNED), is capped at
about 12 percent of a menu and is pinned at CPU band 3.  A record listed on several odd formations that disagree about
which slot is the strong edge is throttled the same way, and a menu that is mostly such records gets exclusive calls.

Adding or changing a team package (P6): edit that team's Scheme in SCHEMES below.
  * family: 'even' (four-down Over line) or 'odd' (Wide line on a 4-3 roster; Okie on a 3-4 roster).
  * mug: True gives the team an extra "Nickel Mug" formation (passing downs only) when its book has play room.
  * package: concept labels from build.SPLIT_IN (e.g. 'Cover 6', 'Sim Pressure 3', 'Tampa 2'); each one is weighted
    x1.35 in that team's targets, so the team gets more calls of it than the shared core.
Then run `python3 pb/v2/defense/build.py --team XXX` (offense packs first: the defense pins the offense compile),
`python3 pb/v2/defense/diagrams.py <dir>` and tests/mod_editor/test_nfl2k5_defense_v2.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from library import TECH, gap_lane

YD = 91.44
# Kinds (low 5 bits of a category position code).
DE, DT, MLB, OLB, FS, SS, CB = 12, 13, 14, 15, 16, 17, 18
STRONG, WEAK = -1, +1


def t(name: str, side: int) -> int:
    return int(round(side * TECH[name]))


# ---------------------------------------------------------------------------------------------------------------
# Defensive line families: technique per slot role.  Roles: 'WE' weak end, 'SE' strong end, 'WT' weak tackle,
# 'ST' strong tackle (four-down books: slots 0..3 = DE2, DE, DT2, DT, retail order); odd books: 'WE' = DE2 (slot 1),
# 'SE' = DE (slot 2), 'N' = DT nose (slot 3).
# ---------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class LineFamily:
    name: str
    techs: dict            # role -> (technique, side)
    note: str


OVER = LineFamily('Over', {'WE': ('w5', WEAK), 'SE': ('5', STRONG), 'WT': ('1', WEAK), 'ST': ('3', STRONG)},
                  'Four-down Over: strong 5-technique end, strong 3-technique, weak 1-technique shade, wide-5 weak end.')
WIDE = LineFamily('Wide', {'WE': ('w9', WEAK), 'SE': ('7', STRONG), 'WT': ('3', WEAK), 'ST': ('4i', STRONG)},
                  'Four-down Wide (2-4-5 rush look with hands down): 7-technique strong end, strong 4i, weak 3, wide-9 '
                  'weak end; the Sam stands off the ball outside the tight end (b776 de2: an outside backer is never the '
                  'outermost man on the line, the ends are).')
BEAR = LineFamily('Bear', {'WE': ('5', WEAK), 'SE': ('5', STRONG), 'WT': ('0', WEAK), 'ST': ('3', STRONG)},
                  'Bear/46: both ends at 5-technique (the two outermost slots of the line, EDGE), nose over the centre, '
                  'strong 3-technique tackle; the outside backers stand off the line behind them.')
ODD = LineFamily('Okie', {'WE': ('4i', WEAK), 'SE': ('5', STRONG), 'N': ('0', STRONG)},
                 'Three-down Okie: weak 4i, 0-technique nose, strong 5-technique, standing edges outside both ends.')
# b779 dp1: team front families (DESIGN by coordinator lineage, pb/research/defense_profiles.json).  Four-down rosters:
UNDER = LineFamily('Under', {'WE': ('w5', WEAK), 'SE': ('5', STRONG), 'WT': ('3', WEAK), 'ST': ('1', STRONG)},
                   'Four-down Under (Spagnuolo / Golden / Campanile): weak 3-technique, strong 1-technique shade, strong '
                   '5-technique end, wide-5 weak end; the Sam stands off the ball over the tight end.')
WIDE9 = LineFamily('Wide 9', {'WE': ('w9', WEAK), 'SE': ('9', STRONG), 'WT': ('3', WEAK), 'ST': ('1', STRONG)},
                   'Four-down Wide 9 (Seattle / Saleh / Schwartz / Ryans / Glenn): both ends wide (weak wide 9, strong '
                   '9 outside the tight end), weak 3-technique, strong 1-technique shade.')
TITE4 = LineFamily('Tite', {'WE': ('w5', WEAK), 'SE': ('w5', STRONG), 'WT': ('4i', WEAK), 'ST': ('4i', STRONG)},
                   'Four-down Tite (Fangio / Staley / Gannon / Evero): both tackles in 4i shades, both ends wide 5; the '
                   'reduced interior that funnels runs to the split safeties.')
# Three-down (3-4 roster) families beside the Okie:
TITE3 = LineFamily('Tite', {'WE': ('4i', WEAK), 'SE': ('4i', STRONG), 'N': ('0', STRONG)},
                   'Three-down Tite: 4i-0-4i, standing edges outside both ends.')
EAGLE = LineFamily('Eagle', {'WE': ('3', WEAK), 'SE': ('3', STRONG), 'N': ('0', STRONG)},
                   'Three-down Double Eagle (the 3-0-3 "bear front" of the Flores / Belichick pressure trees): both '
                   'ends in 3-techniques, nose on the centre, standing edges outside.')
FOUR_DOWN = {'Over': None, 'Wide': None, 'Under': UNDER, 'Wide 9': WIDE9, 'Tite': TITE4}
THREE_DOWN = {'Okie': None, 'Tite': TITE3, 'Eagle': EAGLE}
MUG = LineFamily('Mug', {'WE': ('w9', WEAK), 'SE': ('9', STRONG), 'WT': ('4i', WEAK), 'ST': ('4i', STRONG)},
                 'Double-A mug pressure look: both tackles in 4i shades, ends wide, two linebackers walked into '
                 'the A gaps 1.1 yd off the ball.')


FOUR_DOWN.update({'Over': OVER, 'Wide': WIDE})
THREE_DOWN.update({'Okie': ODD})


def dl_x(family: LineFamily, role: str) -> int:
    tech, side = family.techs[role]
    return t(tech, side)


# ---------------------------------------------------------------------------------------------------------------
# Formation alignments.  Each builder gets the native slot kinds and returns {slot: (x, z)} for the slots it moves;
# slots it does not name (safeties, corners) keep their retail spots, which the coverage scripts' pre-snap 0x1B
# nodes already adjust (rotations, press, walk-outs).
# ---------------------------------------------------------------------------------------------------------------
def four_down_roles(kinds):
    """Retail four-down slot order: DE2 (+x), DE (-x), DT2 (+x), DT (-x) in slots 0..3."""
    assert [kinds[s] for s in range(4)] in ([DE, DE, DT, DT], [DE, DE, DT, DT]), kinds[:4]
    return {'WE': 0, 'SE': 1, 'WT': 2, 'ST': 3}


def line(family: LineFamily, roles: dict) -> dict:
    return {slot: (dl_x(family, role), 0) for role, slot in roles.items()}


def linebackers(kinds, first=4, last=6):
    return [s for s in range(first, last + 1) if kinds[s] in (MLB, OLB)]


def base_43(family: LineFamily, kinds) -> dict:
    """4-3 Over (even scheme) or 4-3 Wide (odd scheme on a 4-3 roster: Sam walked up for a five-man line)."""
    pos = line(family, four_down_roles(kinds))
    will, mike, sam = 4, 5, 6            # retail: OLB2 (+x), MLB, OLB (-x)
    if family is WIDE:
        pos[sam] = (-455, 320)                   # stands off the ball outside the tight end, 3.5 yd (never on the line)
        pos[mike] = (-40, 457)
        pos[will] = (275, 457)
    elif family is UNDER:
        pos[sam] = (-470, 320)                   # Under: Sam off the ball over the tight end, 3.5 yd
        pos[mike] = (40, 457)                    # Mike over the weak A gap (the 1-shade covers the strong A)
        pos[will] = (300, 503)                   # Will stacked behind the weak 3-technique, 5.5 yd
    elif family is WIDE9:
        pos[sam] = (-410, 411)                   # Wide 9: Sam inside the strong 9-technique end, 4.5 yd
        pos[mike] = (-30, 503)                   # Mike 5.5 yd: the wide ends leave the B gaps to the backers
        pos[will] = (250, 457)
    elif family is TITE4:
        pos[sam] = (-640, 365)                   # Tite: Sam outside the strong wide-5 end, 4 yd (a stacked edge)
        pos[mike] = (-90, 457)
        pos[will] = (180, 457)
    else:
        pos[sam] = (-430, 411)                   # Over: Sam off the ball over the tight end's inside eye
        pos[mike] = (-50, 457)                   # 10/20 alignment, strong A gap
        pos[will] = (260, 457)                   # weak B gap (30)
    return pos


def bear(family: LineFamily, kinds) -> dict:
    """Bear/46 short-yardage front.  Four-down books whose Bear shares fronts with the base family keep the shared
    tackle/end roles; the 3-0-3 interior comes from moving the weak end into the weak 3-technique and the weak
    tackle onto the centre."""
    roles = four_down_roles(kinds)
    pos = line(BEAR, roles)
    lbs = linebackers(kinds)
    # Retail Bear slots: 4 = OLB2/OLB (weak or walk-up), 5 = MLB or MLB2, 6 = OLB/MLB (strong).
    edge_w, mike, edge_s = lbs[0], lbs[1], lbs[2]
    pos[edge_s] = (-430, 274)                   # Sam 3 yd off the ball over the TE (never on the line: the ends are the edge men)
    pos[edge_w] = (330, 274)                    # Will 3 yd off the ball, outside the weak tackle's shoulder
    pos[mike] = (0, 411)
    pos[8] = (-300, 411)                        # strong safety down in the box (eighth man)
    pos[7] = (0, 1097)                          # free safety single high
    return pos


def nickel_even(family: LineFamily, kinds) -> dict:
    pos = line(family, four_down_roles(kinds))
    lbs = linebackers(kinds)
    will, mike = (lbs[0], lbs[1]) if len(lbs) >= 2 else (None, lbs[0])
    pos[mike] = (-60, 457)
    if will is not None:
        pos[will] = (230, 457)
    return pos


def dime_even(family: LineFamily, kinds) -> dict:
    pos = line(family, four_down_roles(kinds))
    lbs = linebackers(kinds)
    if lbs:
        pos[lbs[0]] = (40, 503)                 # lone backer, 5.5 yd
    return pos


def mug(kinds) -> dict:
    """Double-A mug (pressure call, nickel personnel): tackles in 4i shades, ends wide, two backers in the A gaps.
    LBs 80 cm off the centre (1.75 yd apart) and 1.1 yd deep: 2.2 yd from each 4i."""
    pos = line(MUG, four_down_roles(kinds))
    lbs = linebackers(kinds)
    a, b = lbs[0], lbs[1]
    pos[a] = (80, 100)
    pos[b] = (-80, 100)
    return pos


def odd_roles(kinds):
    """Retail odd order: slot 0 edge OLB, 1 DE2 (+x), 2 DE (-x), 3 DT nose."""
    assert kinds[1] == DE and kinds[2] == DE and kinds[3] == DT, kinds[:4]
    return {'WE': 1, 'SE': 2, 'N': 3}


def odd_front(kinds, *, base: bool, family: LineFamily = None) -> dict:
    family = family or ODD
    pos = line(family, odd_roles(kinds))
    weak_x = dl_x(family, 'WE')
    pos[0] = (max(weak_x + 265, t('4i', WEAK) + 265), 91)   # weak edge, standing, outside the weak end (wide 5 spot)
    # b776 de2: every OLB-kind slot after slot 0 is the STRONG EDGE (the 3-4 base's slot 6, the HOU/NE/PIT/SD nickel and
    # dime's slot 5, the 3-3's slot 4), and the position recode makes it an EDGE player.  It stands on the edge like the
    # base's, not inside as a third inside backer (it used to: nickel/dime put it at 5 yd, -2 yd, which is where the
    # drop-into-the-flat scripts wanted it and the opposite of Noah's rule).  Only MLB-kind slots are inside backers.
    for s in range(4, 7):
        if kinds[s] == OLB:
            pos[s] = (t('9', STRONG) - 65, 91)
    ilbs = [s for s in range(4, 7) if kinds[s] == MLB]
    if len(ilbs) >= 2:
        pos[ilbs[0]] = (183, 457)
        pos[ilbs[1]] = (-183, 457)
    elif ilbs:
        pos[ilbs[0]] = (0, 457)
    return pos


# ---------------------------------------------------------------------------------------------------------------
# Fronts: rush lanes per role.  Lanes are the engine's 17-entry lateral table (8 = centre, 76.2 cm per lane).
# Modes follow retail usage: 1 = base/read (retail "Base"), 2 = gap/penetrate (retail "Gap", "Pinch", odd fronts),
# 3 = contain (retail "Contain" edges), 5 = odd contain, 0 = two-gap hold (retail odd nose "Base Odd").
# A looping stunt defender carries a delay (retail twists use 0.1 s).
# ---------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class FrontCall:
    name: str
    family: str          # 'four' (four-down shared), 'odd', 'bear', 'mug', 'dime'
    lanes: dict          # role -> (mode, lane, delay)
    band: int            # CPU score band (bits 9-11); lower is called more
    note: str = ''


def four_down_fronts(family: LineFamily) -> list[FrontCall]:
    def own(role):
        tech, side = family.techs[role]
        return gap_lane(tech, side)
    WE, SE, WT, ST = (own(r) for r in ('WE', 'SE', 'WT', 'ST'))
    return [
        FrontCall('Base', 'four', {'WE': (1, WE, 0), 'SE': (1, SE, 0), 'WT': (1, WT, 0), 'ST': (1, ST, 0)}, 1,
                  'Each lineman reads his own gap (one-gap fits).'),
        FrontCall('Attack', 'four', {'WE': (2, WE, 0), 'SE': (2, SE, 0), 'WT': (2, WT, 0), 'ST': (2, ST, 0)}, 2,
                  'Same gaps, penetrating get-off.'),
        FrontCall('Slant Strong', 'four', {'WE': (2, WE - 2, 0), 'SE': (2, SE - 2, 0), 'WT': (2, WT - 2, 0),
                                           'ST': (2, ST - 2, 0)}, 2, 'Whole line slants one gap to the strength.'),
        FrontCall('Slant Weak', 'four', {'WE': (2, WE + 2, 0), 'SE': (2, SE + 2, 0), 'WT': (2, WT + 2, 0),
                                         'ST': (2, ST + 2, 0)}, 2, 'Whole line slants one gap away from the strength.'),
        FrontCall('Pinch', 'four', {'WE': (2, 11, 0), 'SE': (2, 5, 0), 'WT': (2, 9, 0), 'ST': (2, 7, 0)}, 3,
                  'Ends crash the B gaps, tackles the A gaps (run down).'),
        FrontCall('TE Stunt Weak', 'four', {'WE': (1, 10, 0.2), 'SE': (1, SE, 0), 'WT': (2, 13, 0), 'ST': (1, ST, 0)}, 2,
                  'Weak tackle penetrates outside, weak end loops inside behind him.'),
        FrontCall('ET Stunt Strong', 'four', {'WE': (1, WE, 0), 'SE': (2, 5, 0), 'WT': (1, WT, 0), 'ST': (1, 2, 0.2)}, 2,
                  'Strong end crashes inside, strong tackle loops to contain.'),
        FrontCall('Contain Rush', 'four', {'WE': (3, 16, 0), 'SE': (3, 0, 0), 'WT': (2, 11, 0), 'ST': (2, 5, 0)}, 3,
                  'Passing-down rush lanes: ends keep contain outside, tackles rush the B gaps.'),
        FrontCall('Wide Rush', 'four', {'WE': (2, 15, 0), 'SE': (2, 1, 0), 'WT': (2, 11, 0), 'ST': (2, 5, 0)}, 3,
                  'Ends speed-rush wide, tackles the B gaps.'),
        FrontCall('Double Twist', 'four', {'WE': (1, 10, 0.2), 'SE': (1, 6, 0.2), 'WT': (2, 13, 0), 'ST': (2, 3, 0)}, 3,
                  'Both tackles penetrate outside, both ends loop inside.'),
    ]


# b779 dp1: front-call styles.  A front group has room for about eight calls, so the ORDER decides which calls a book
# carries and the band (bits 9-11) how often the native lottery calls each (the coach-profile rings prefer the low
# bands too).  Every name below is one of the calls above; nothing new is authored.
FRONT_STYLE = {
    # Wide 9 / Seattle trees: speed off the edge, tackles penetrate, few line games.
    'speed': (('Wide Rush', 1), ('Attack', 1), ('Base', 2), ('Slant Strong', 2), ('Slant Weak', 2), ('ET Stunt Strong', 2),
              ('Contain Rush', 3), ('Pinch', 3), ('TE Stunt Weak', 3), ('Double Twist', 3)),
    # Pressure trees: line games and penetration.
    'games': (('Attack', 1), ('TE Stunt Weak', 1), ('ET Stunt Strong', 2), ('Double Twist', 2), ('Pinch', 2), ('Base', 2),
              ('Slant Strong', 2), ('Slant Weak', 3), ('Wide Rush', 3), ('Contain Rush', 3)),
    # Fangio / split-safety trees: read the run on the way to the QB, keep the rush lanes.
    'read': (('Base', 1), ('Contain Rush', 1), ('Slant Strong', 2), ('Slant Weak', 2), ('Attack', 2), ('ET Stunt Strong', 2),
             ('Pinch', 3), ('TE Stunt Weak', 3), ('Wide Rush', 3), ('Double Twist', 3)),
}
STYLE_OF = {'speed': ('ATL', 'CLE', 'TEN', 'SF', 'HOU', 'MIA', 'NYJ', 'DET'),
            'games': ('KC', 'TB', 'MIN', 'WAS', 'BUF', 'DEN', 'CHI', 'BAL', 'PIT', 'NE', 'IND', 'JAX', 'CIN', 'NYG', 'SEA',
                      'OAK'),
            'read': ('PHI', 'DAL', 'NO', 'CAR', 'GB', 'ARZ', 'STL', 'SD')}


def styled_fronts(calls: list[FrontCall], team: str) -> list[FrontCall]:
    """``calls`` reordered and re-banded for the team's front style (unchanged for a team without one)."""
    style = next((k for k, teams in STYLE_OF.items() if team in teams), None)
    if style is None:
        return calls
    by_name = {c.name: c for c in calls}
    out = [FrontCall(c.name, c.family, c.lanes, band, c.note) for name, band in FRONT_STYLE[style]
           if (c := by_name.get(name)) is not None]
    return out + [c for c in calls if c.name not in {x.name for x in out}]


ODD_STYLE = {'games': (('Okie Attack', 1), ('Slant Strong', 1), ('Slant Weak', 2), ('Pinch', 2), ('Okie', 2), ('Contain', 3)),
             'read': (('Okie', 1), ('Contain', 1), ('Slant Strong', 2), ('Slant Weak', 2), ('Okie Attack', 2), ('Pinch', 3)),
             'speed': (('Okie Attack', 1), ('Contain', 2), ('Okie', 2), ('Slant Strong', 2), ('Slant Weak', 2), ('Pinch', 3))}


def styled_odd_fronts(team: str) -> list[FrontCall]:
    calls = odd_fronts()
    style = next((k for k, teams in STYLE_OF.items() if team in teams), None)
    if style is None:
        return calls
    by_name = {c.name: c for c in calls}
    return [FrontCall(n, by_name[n].family, by_name[n].lanes, b, by_name[n].note) for n, b in ODD_STYLE[style]]


def odd_fronts() -> list[FrontCall]:
    return [
        FrontCall('Okie', 'odd', {'WE': (1, 12, 0), 'SE': (1, 4, 0), 'N': (0, 8, 0)}, 1,
                  'Nose two-gaps the centre, the ends read the tackles.'),
        FrontCall('Okie Attack', 'odd', {'WE': (2, 11, 0), 'SE': (2, 3, 0), 'N': (2, 7, 0)}, 2, 'One-gap penetration.'),
        FrontCall('Slant Strong', 'odd', {'WE': (2, 9, 0), 'SE': (2, 1, 0), 'N': (2, 7, 0)}, 2, 'Line slants to the strength.'),
        FrontCall('Slant Weak', 'odd', {'WE': (2, 13, 0), 'SE': (2, 5, 0), 'N': (2, 9, 0)}, 2, 'Line slants away from the strength.'),
        FrontCall('Pinch', 'odd', {'WE': (2, 9, 0), 'SE': (2, 5, 0), 'N': (2, 8, 0)}, 3, 'All three inside (run down).'),
        FrontCall('Contain', 'odd', {'WE': (5, 16, 0), 'SE': (5, 0, 0), 'N': (0, 8, 0)}, 3, 'Retail odd contain lanes.'),
    ]


def bear_fronts(full: bool = False) -> list[FrontCall]:
    calls = [
        FrontCall('Bear Plug', 'bear', {'WE': (2, 13, 0), 'SE': (2, 3, 0), 'WT': (0, 8, 0), 'ST': (2, 5, 0)}, 0,
                  '3-0-3 attack the B gaps, nose holds the centre.'),
        FrontCall('Bear Pinch', 'bear', {'WE': (2, 11, 0), 'SE': (2, 5, 0), 'WT': (2, 8, 0), 'ST': (2, 7, 0)}, 1,
                  'Everyone inside, edges own the C gaps.'),
        FrontCall('Bear Slant', 'bear', {'WE': (2, 11, 0), 'SE': (2, 1, 0), 'WT': (2, 7, 0), 'ST': (2, 3, 0)}, 1,
                  'Slant to the strength.'),
    ]
    if full:
        calls += [
            FrontCall('Bear Base', 'bear', {'WE': (1, 13, 0), 'SE': (1, 3, 0), 'WT': (1, 8, 0), 'ST': (1, 5, 0)}, 1,
                      'Read the B gaps, nose two-gaps.'),
            FrontCall('Bear Slant Weak', 'bear', {'WE': (2, 15, 0), 'SE': (2, 5, 0), 'WT': (2, 9, 0), 'ST': (2, 7, 0)}, 2,
                      'Slant away from the strength.'),
            FrontCall('Bear Contain', 'bear', {'WE': (3, 16, 0), 'SE': (3, 0, 0), 'WT': (2, 8, 0), 'ST': (2, 5, 0)}, 3,
                      'Contain lanes for the ends.'),
            FrontCall('Bear Twist', 'bear', {'WE': (1, 10, 0.2), 'SE': (2, 3, 0), 'WT': (2, 11, 0), 'ST': (2, 5, 0)}, 2,
                      'Weak end loops behind the nose, nose slants to the weak B gap.'),
            FrontCall('Bear Fire', 'bear', {'WE': (2, 13, 0), 'SE': (2, 3, 0), 'WT': (2, 9, 0), 'ST': (2, 7, 0)}, 2,
                      'All four penetrate their gaps.'),
        ]
    return calls


def mug_fronts() -> list[FrontCall]:
    return [
        FrontCall('Mug Wide', 'mug', {'WE': (2, 15, 0), 'SE': (2, 1, 0), 'WT': (2, 11, 0), 'ST': (2, 5, 0)}, 0,
                  'Ends rush wide, tackles the B gaps; the A gaps belong to the mugged backers.'),
        FrontCall('Mug Contain', 'mug', {'WE': (3, 16, 0), 'SE': (3, 0, 0), 'WT': (2, 11, 0), 'ST': (2, 5, 0)}, 1,
                  'Contain lanes for the ends.'),
    ]


def dime_fronts() -> list[FrontCall]:
    return [
        FrontCall('Speed Rush', 'dime', {'WE': (2, 15, 0), 'SE': (2, 1, 0), 'WT': (2, 11, 0), 'ST': (2, 5, 0)}, 0,
                  'Third-down rush: ends wide, tackles B gaps.'),
        FrontCall('Dime Twist', 'dime', {'WE': (1, 10, 0.2), 'SE': (2, 1, 0), 'WT': (2, 13, 0), 'ST': (2, 5, 0)}, 1,
                  'Weak tackle-end twist.'),
    ]


# ---------------------------------------------------------------------------------------------------------------
# Team schemes (2026 coordinators from pb/research/defense_profiles.json; rates are their sourced 2025 baselines).
# 'mug': the coordinator's documented double-A / sim-pressure identity, offered only as a named passing-down call.
# 'package': signature calls added on top of the shared core (P6).
# ---------------------------------------------------------------------------------------------------------------
@dataclass
class Scheme:
    family: str                 # 'even' or 'odd'
    mug: bool = False
    package: tuple = ()
    note: str = ''
    line4: str = ''             # b779 dp1: four-down front family (FOUR_DOWN key); '' = Over (even) / Wide (odd)
    line3: str = 'Okie'         # b779 dp1: three-down front family (THREE_DOWN key)
    disguise: float = 0.3       # b779 dp1: share of single-high calls shown from a two-high shell (DESIGN, lineage)


SPLIT = ('Cover 6', 'Cover 4 Quarters', 'Cover 2 Invert', '2-Read Match')
PRESSURE = ('Cover 0 Blitz', 'Sim Pressure', 'Fire Zone 3', 'Cover 1 Blitz')
SCHEMES = {
    'ARZ': Scheme('odd', False, SPLIT, 'Rallis: Gannon split-safety family.', line4='Tite'),
    'ATL': Scheme('even', False, ('Cover 3 Buzz', 'Cover 1 Robber', 'Cover 4 Quarters'), 'Ulbrich: Saleh/Seattle 4-down.', line4='Wide 9'),
    'BAL': Scheme('odd', True, ('Sim Pressure', 'Cover 3 Match', 'Cover 6'), 'Weaver: Ravens pressure-disguise family.'),
    'BUF': Scheme('odd', True, ('Sim Pressure', 'Cover 1 Blitz', 'Cover 0 Blitz'), 'Leonhard: Pettine/Joseph pressure.', line3='Eagle'),
    'CAR': Scheme('odd', False, SPLIT, 'Evero: Fangio/Staley split coverage.', line4='Tite'),
    'CHI': Scheme('even', False, ('Cover 1 Blitz', 'Cover 0 Blitz', '2-Man Under'), 'Allen: Saints man pressure.'),
    'CIN': Scheme('even', False, ('Cover 3 Match', 'Cover 1 Robber', 'Cover 6'), 'Golden: multiple, low blitz.', line4='Under'),
    'CLE': Scheme('even', False, ('Cover 3 Buzz', 'Cover 1 Robber', 'Cover 4 Quarters'), 'Rutenberg: Saleh/Ulbrich 4-down.', line4='Wide 9'),
    'DAL': Scheme('odd', False, SPLIT, 'Parker: Fangio split coverage.', line4='Tite', line3='Tite'),
    'DEN': Scheme('odd', True, PRESSURE, 'Joseph: Phillips/Joseph pressure.'),
    'DET': Scheme('even', False, ('Cover 1 Blitz', '2-Man Under', 'Cover 1 Robber'), 'Sheppard: Glenn/Allen man.', line4='Wide 9'),
    'GB': Scheme('odd', False, SPLIT + ('Mug Pressure',), 'Gannon: Zimmer/Gannon split coverage.', line4='Tite'),
    'HOU': Scheme('even', False, ('Cover 3 Buzz', 'Cover 4 Quarters', 'Cover 2'), 'Burke: Ryans/Schwartz 4-down.', line4='Wide 9'),
    'IND': Scheme('even', False, ('Cover 6', 'Sim Pressure', 'Cover 4 Quarters'), 'Anarumo: multiple disguise.'),
    'JAX': Scheme('even', False, ('Cover 3 Match', 'Cover 2', 'Cover 6'), 'Campanile: Hafley/Flores multiple.', line4='Under'),
    'KC': Scheme('even', True, PRESSURE + ('QB Spy',), 'Spagnuolo: Jim Johnson pressure, one situational spy.', line4='Under'),
    'MIA': Scheme('even', False, ('Cover 3 Sky', 'Cover 2', 'Cover 4 Quarters'), 'Duggan: Hafley 4-down zone.', line4='Wide 9'),
    'MIN': Scheme('odd', True, ('Sim Pressure', 'Cover 0 Blitz', 'Cover 2', 'Cover 6'), 'Flores: Belichick pressure disguise.', line3='Eagle'),
    'NE': Scheme('odd', False, ('Cover 1 Robber', 'Cover 3 Match', 'Cover 2'), 'Kuhr: Vrabel/Bowen multiple.'),
    'NO': Scheme('odd', False, SPLIT, 'Staley: Fangio split coverage.', line4='Tite'),
    'NYG': Scheme('odd', False, ('Cover 3 Match', 'Cover 2', 'Sim Pressure'), 'Wilson: Ravens/Eagles multiple.'),
    'NYJ': Scheme('even', True, ('Cover 2', 'Cover 3 Match', 'Sim Pressure'), 'Duker: Glenn/Weaver multiple.', line4='Wide 9'),
    'OAK': Scheme('odd', False, ('Cover 3 Sky', 'Cover 4 Quarters', 'Cover 2'), 'Leonard: Graham/Ravens multiple.'),
    'PHI': Scheme('odd', False, SPLIT, 'Fangio: split coverage.', line4='Tite'),
    'PIT': Scheme('odd', False, ('Cover 3 Sky', 'Sim Pressure', 'Cover 4 Quarters'), 'Graham: Belichick multiple disguise.'),
    'SD': Scheme('odd', False, ('Cover 3 Match', 'Cover 2', 'Cover 6'), "O'Leary: Minter/Notre Dame multiple.", line3='Tite'),
    'SEA': Scheme('odd', False, ('Sim Pressure', 'Cover 2', 'Cover 3 Match'), 'Durde: Macdonald/Quinn multiple.'),
    'SF': Scheme('even', False, ('Cover 3 Buzz', 'Tampa 2', 'Cover 4 Quarters'), 'Morris: Tampa/Rams split coverage.', line4='Wide 9'),
    'STL': Scheme('odd', False, ('Cover 3 Sky', 'Cover 6', 'Cover 2'), 'Shula: Phillips/Staley/Morris multiple.', line4='Tite'),
    'TB': Scheme('odd', True, ('Cover 0 Blitz', 'Cover 1 Blitz', 'Fire Zone 3'), 'Bowles: Bowles/Arians pressure.', line3='Eagle'),
    'TEN': Scheme('even', False, ('Cover 3 Sky', 'Cover 4 Quarters', 'Cover 6'), 'Bradley: Seattle/Saleh 4-down.', line4='Wide 9'),
    'WAS': Scheme('odd', True, ('Sim Pressure', 'Cover 0 Blitz', 'Cover 2'), 'Jones: Flores/Zimmer disguise.', line3='Eagle'),
}

# b779 dp1 (DESIGN by coaching lineage, INFERRED: no public 2025 pre-snap shell charting exists): the share of
# single-high calls a coordinator shows from a two-high shell before the snap.  The generator converts single-high
# records (their rotating safety's pre-snap walk-down becomes a post-snap rotation) until the book reaches it; the CPU
# coach-profile rings (mod_editor/core/nfl2k5_defense_rings.py) aim at the same share.
DISGUISE = {
    # Ravens / Belichick / Flores disguise trees: rotate late out of two-high shells.
    'SEA': .55, 'MIN': .55, 'WAS': .55, 'PIT': .5, 'IND': .5, 'BAL': .5, 'NYG': .45,
    # Fangio / Staley / Gannon split-safety trees: two-high looks that spin to one-high at the snap.
    'PHI': .45, 'DAL': .45, 'NO': .45, 'CAR': .45, 'GB': .45, 'ARZ': .45, 'STL': .4, 'SD': .45,
    # Pressure and multiple-front coordinators.
    'KC': .35, 'TB': .3, 'BUF': .35, 'DEN': .3, 'CHI': .3, 'NYJ': .3, 'NE': .35, 'OAK': .3, 'DET': .25,
    'CIN': .3, 'JAX': .3,
    # Seattle / Saleh four-down single-high trees: show the shell they play.
    'ATL': .2, 'CLE': .2, 'TEN': .2, 'SF': .25, 'HOU': .2, 'MIA': .25,
}
for _team, _share in DISGUISE.items():
    SCHEMES[_team].disguise = _share

# Formation situation ratings (bits 21-23 short, 24-26 medium, 27-29 long; PROVED OFFLINE 0x207EF0: curve over
# rating-2 in normal play, rating-1 on the long/short field when the offense is urgent; rating 1 is best).
SITUATION = {
    'base':   (2, 1, 2),     # early downs; 3rd-and-short shared with the Bear
    'bear':   (1, 4, 4),     # short yardage (only competes when it shares the 4-3 personnel group)
    'nickel': (1, 1, 1),
    'mug':    (4, 4, 1),     # long yardage only (3rd-and-7+, 2nd-and-long)
    'dime':   (4, 2, 1),
    'odd_nickel': (2, 1, 1),
    'odd_dime': (4, 2, 1),
}
