#!/usr/bin/env python3
"""Ruling 2 (b81-retail-free-art): the provenance class and the measured base content of every data row that stores
texels, for the release gate to judge.

  python3 tools/b81_uniforms/texel_rows.py "<released v0.9 disc>" "<retail disc>"   -> packaging/nfl2k5_texel_rows.json

(the retail disc is read only for rows whose rules read the user's own retail textures, ``retail:`` donors, exactly as
the build does; without it those rows are recorded unmeasured)

Class, by the provenance of the texture the row edits (coordinator's ruling 2):
  i    the base ships whole in the package as the project's own art (a retail-free catalog with a provenance record);
  ii   the base is derived at build time from the user's retail disc, or its provenance cannot be established: the row
       must not carry base content;
  iii  the row's texels are wholly new art (on a region cleared by rule, or a pattern by rule), with the record why.
No kit or glyph texture ships whole as project art (the catalogs hold none), so every row is class ii unless it is a
class iii row named below with its reason. A class ii row is measured on the texture the build holds at its step (the
released v0.9 disc: no earlier step of beta 81 touches these chunks; every input is checked against before_sha256):
  edge_overlap   shipped texels on the base's edges over the base's edges in their box (limit 0.25)
  base_equal     shipped texels whose colour equals the base's at that texel
  follows_base   the shipped colours follow the base's shading (a recolour that keeps it): luminance correlation
                 >= 0.9 over at least 32 shipped texels where the base varies
A row whose input is not on the disc (an earlier step of the same build writes it) is recorded unmeasured, unless
B81_TEXEL_INPUTS names a Studio build of the branch base (b81-uniform-pass2, 11/24): then such a row is measured on the
input that build holds at the row's chunk, when it is exactly the row's before pin (the sleeves the swoosh step sw1 writes
before the uniform pass: 07H0, 26H0, 26A0, 09H9, 09A9). The release check refuses a class ii row that fails any of these or
is unmeasured."""
from __future__ import annotations

import hashlib
import os
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(ROOT / 'tools/b77'), str(ROOT / 'tools/b81_uniforms')]
from mod_editor.core import nfl2k5_bump_texture_writer as bw  # noqa: E402
from mod_editor.core import nfl2k5_glyph_fixes_2026 as gf  # noqa: E402
from mod_editor.core import nfl2k5_kit_fixes_2026 as kf  # noqa: E402
import kitfix_convert as kc  # noqa: E402
import glyph_derive as gd  # noqa: E402
import modern_art_png_catalog as catalog  # noqa: E402
RELEASE = catalog._release(ROOT)

OUT = ROOT / 'packaging/nfl2k5_texel_rows.json'
SCHEMA = 'nfl2k5_texel_rows/v1'
EDGE_OVERLAP_LIMIT = 0.25
# Ruling 1 (coordinator, 2026-11-20): art drawn by the project's own code from the project's own shape definition, over
# a region cleared by rule, may ship where it lands on the old mark. Only rows whose tool and shape source are recorded
# in retail-free/REVIEW_ME.md section 14 are named here; the test keeps this list from growing.
RULING_1 = {
    "data/nfl2k5_kit_fixes_2026_b81u.json": {
        f"{sel}:2:tset": ("Bengals pants strokes: drawn by work/fix/R2C/tools/cinpaint.py on the player model from the "
                          "geometry read off the 2026 White Bengal photographs (strokes.py, inkband2.py) and order R2-C "
                          "item 1; the old marks are cleared by rule (clear) first")
        for sel in ("06H0", "06A0", "06H5", "06A5", "06H6", "06A6")} | {
        # added by ruling (coordinator, 2026-11-20 19:4x, the lane's question 2, answer (a)); examined on its own
        "29A0:1:tset": ("Commanders road shoulder swoosh, added to this list by ruling: retail 29H0 and 29A0 carry no "
                        "swoosh; the shape is the project's own swoosh from its 29H0 sleeve art, laid on the body by "
                        "work/fix/R2C/tools/waspaint.py through the game jersey mesh; it sits where the project's own "
                        "v0.9 swoosh was, which a clear rule removes; its colours blend white with the kit burgundy. "
                        "Measured (retail-free/REVIEW_ME.md section 18): the swoosh texels' edge overlap 0.047 against "
                        "the retail torso and 0.165 against the base the build holds at this step, none equal to either. "
                        "The row's collar shield is drawn from data/nfl2k5_espn25_fields/source/nfl_2008.png "
                        "(class iii family b81u-collar-shield-undersized)")},
}


# Ruling 2 class iii: families whose texels are wholly new art drawn by the project's own code from the project's own
# shapes (recorded in retail-free/REVIEW_ME.md section 15), placed where the row clears the old mark by rule (or where
# the new art covers it). A row qualifies only if every one of its fixes is in this list (or in RULING_1) and its texels
# hold no erasure (no texel set to the field colour over an old mark); texels where the new art happens to equal the
# old mark are recorded (base_equal), as ruling 1 allows for the Bengals strokes.
CLASS_III = {
    "b81u-collar-shield-undersized": "league collar shield drawn from the repo's data/nfl2k5_espn25_fields/source/"
                                     "nfl_2008.png (catalogued) at 12 x 16, silver border by rule",
    "b81u-DEN-broncos-wordmark": "BRONCOS drawn from nothing by code (7 letters 6 x 6, 2-texel stems, one colour)",
    "b81u-NO-60th-patch-real-size": "60th anniversary patch drawn by code at 21 x 33 from the club's patch design",
    "b81u-HOU-memorial-patch-missing": "memorial oval drawn by code (navy oval, light rim, a row of marks)",
    "b81u-PHI-eagles-step-edges": "18 half-blend texels (#808080) added in the inner corners of the two steps",
    "b81u-MIA-sleeve-logo-oversized": "Dolphins sleeve logo drawn from the repo's data/nfl2k5_scorebug_assets/logos/"
                                      "mia.png (the mod's own logo) at its 2026 size",
    "b81u-NYG-chest-ny-vs-true-shield": "chest ny drawn from the repo's NYG logo at 12 x 10 beside the redrawn shield",
    "b81u-BUF-nickel-city-shield": "the league shield drawn from the repo's shield art below the collar point",
    "b81u-CAR-alt-second-shield-and-pants-panther": "the standard league shield drawn from the repo's shield art",
    "b81u-SF-home-pants-stripe-narrow": "pants stripe drawn by rule at the widths read off 2026 photographs",
    "b81u-TB-home-pants-stripe-order-width": "pants stripe drawn by rule in the real order and widths (decision 5)",
    "b81u-TB-road-pants-stripe-width": "pants stripe drawn by rule in the real order and widths (decision 5)",
    "b81u-LAR-road-pants-no-sol-band": "sol band and white band drawn by rule at their 2026 place and width",
    "b81u-MIN-road-pants-stripe-reversed-widths": "pants stripe drawn by rule at its real widths",
    "b81u-BUF-road-sleeve-stripes": "sleeve stripes drawn by rule to the real set",
    "b81u-BUF-home-sleeve-stripes": "sleeve stripes drawn by rule to the real set",
    # families whose base-derived part is now a build-time rule (nfl2k5_kit_rule_recolour: ramp, scale, map, move,
    # cols) and whose remaining texels are the authored art named here
    "b81u-chest-wordmark-vs-true-shield": "chest wordmark moved by rule (move); only the drawn collar shield ships",
    "b81u-ATL-chest-lettering-overlaps-full-height-number": "lettering moved by rule (move); only the drawn shield ships",
    "b81u-TEN-titans-wordmark-width": "TITANS narrowed by rule (cols); only the drawn shield ships",
    "b81u-09A9-base-kits4": "base recolour by rule (ramp); only authored art ships",
    "b81u-09H9-base-kits4": "base recolour by rule (ramp); only authored art ships",
    "b81u-DET-dtd-chest-wordmark-small": "DETROIT drawn italic by code (Noah's decision 6)",
    "b81u-DET-dtd-pants-stripe": "band and wedge drawn by code on the player model (order R2-C item 2)",
    "b81u-MIN-home-pants-stripe-hairline": "pants stripe drawn by rule at its real width",
    "b81u-MIN-home-purple-socks": "socks recoloured by rule (ramp)",
    "b81u-14A0-swoosh-colour": "swoosh recoloured by rule (ramp)",
    "b81u-26H4-panels-kits4": "26H0's panels copied by rule (stamp of the pinned donor + a colour-pair map); only the "
                              "drawn collar shield ships",
    # b81-uniform-pass2 fold-in (the approved home/road kits, 11/24): the uniform lanes' authored pictures put in retail-free
    # form (work/rf in the lane folder): old marks cleared by rule (clear), recolours of the base as rules (ramp, map,
    # cols, move), only the drawn texels below ship. "Read on the texture" marks a drawing whose placement or an edge
    # blend was taken from the texture the painter worked on; the shapes themselves are the tools' own.
    **{f"b81p2-{club}-collar-{kind}": (
        "collar drawn by work/A/tools/paint_collar.py on the posed model (V point, sides and neck opening from ratios read "
        "off the 2026 photographs, the model's neck-insert island), 8x supersampled, 4 coverage levels, in the kit's flat "
        "collar colour; the old band cleared by rule; read on the texture: where the V meets the old band its sides run "
        "into a line fitted to the band's outer edge, and the edge texels of the project's own collar shield are "
        "re-blended over the new colour") for club, kind in (("CAR", "v"), ("NO", "v"), ("NYJ", "v"), ("PHI", "v"),
                                                              ("WAS", "v"), ("NYJ", "white"), ("PIT", "white"),
                                                              ("TB", "white"), ("TB", "red"))},
    "b81m-BUF-road-collar-band": "collar band (royal, red inner edge) drawn by work/BUF/tools/bufcollar.py by distance "
                                 "from the neck opening at 4x, 4 blend steps; the old one-texel lines cleared by rule",
    **{f"b81p2-{fam}": ("sleeve stripes drawn as rings round the arm by work/BC/tools/paint_bands.py on the posed model "
                        "(band widths from the 2026 photographs), the swoosh from the exact pass's outline "
                        "(surf.swoosh_outline), 5 coverage levels; the old stripes and swoosh cleared by rule")
       for fam in ("DAL-sleeve-stripes", "CLE-sleeve-stripes-home", "CLE-sleeve-stripes-road")},
    **{f"b81p2-NE-shoulder-stripe-{k}": ("shoulder stripe set drawn as one shape along the model's armhole seam by "
                                         "work/BC/tools/paint_ne.py (2.8 cm stripes, ends at posed heights read off the "
                                         "photographs), 4 coverage levels; the old pieces cleared by rule")
       for k in ("breaks", "over-back")},
    **{f"b81p2-LAR-horn-{k}": ("shoulder horn drawn as one shape on the posed body by work/BC/tools/paint_lar.py (widths, "
                               "tip and curl from the 2026 photographs), 5 coverage levels; the old horn and the blue "
                               "back-yoke bars cleared by rule") for k in ("home", "road")},
    "b81x-LAC-bolt-place-size": "shoulder bolt drawn by b81-uniform-exact work/tools/paint_lac.py: the art lane's "
                                "measured bolt polygon (lacbolt.BOLT_GOLD) laid along the sleeve seam at 38 cm; the old "
                                "marks cleared to the flat cloth colour by rule",
    "b81m-LAC-pants-bolt": "pants bolt drawn by b81-uniform-marks work/LAC/tools/lacbolt.py (the same measured bolt "
                           "polygon) down the outer leg on the model; the old bolt cleared to the flat cloth by rule",
    "b81x-SEA-shoulder-shape": "sleeve cap and shoulder patch drawn by b81-uniform-exact work/tools/paint_sea.py from "
                               "shapes defined on the body (measured on the 2026 photographs, laid out in the Design "
                               "Lab); the old marks cleared by rule",
    "b81x-SEA-band": "chest band, collar feather strips and SEAHAWKS wordmark drawn by b81-uniform-exact "
                     "work/tools/paint_sea.py from shapes defined on the body; the old marks cleared by rule",
    "b81x-SEA-feather-band": "side stripe with twelve feathers drawn by b81-uniform-exact work/tools/paint_sea_pants.py; "
                             "the old stripe cleared by rule",
    "b81m-DAL-navy-sleeve-star": "five-point star drawn by S/work/DAL/tools/dal_sleeve.py (pentagram, tip radius 3.98 cm, "
                                 "white border and navy keyline widths from the photographs) at 4x, 4 blend steps",
    "b81m-DAL-navy-sleeve-band-depth": "band drawn by S/work/DAL/tools/dal_sleeve.py white / grey / white at the "
                                       "photographed proportions; read on the texture: its path and depth are the part "
                                       "0.119..0.833 of the old band's footprint (distance fields at 4x)",
    "b81m-HOU-road-shoulder-horn": "shoulder horn drawn by S/work/HOU/tools/hou_horn.py (paths and widths from the "
                                   "photographs) at 4x, 4 coverage levels; the old band cleared to white by rule",
    **{f"b81m-HOU-pants-stripe-{k}": ("side stripe drawn by S/work/HOU/tools/hou_pants.py: red 5 + navy 20 texels from "
                                      "row 36-40 to the standard hem row (uvpos/std_hem.npy); the old stripe back to the "
                                      "cloth by rule") for k in ("width", "red-edge")},
    **{f"b81m-MIN-{k}": ("side stripe drawn by S/work/MIN/tools/min_pants.py (paintlib pants_stripe: band edges at fixed "
                         "cm round the model's leg, widths from the photographs), 4 blend steps; the old stripe cleared "
                         "by rule") for k in ("home-pants-stripe-front-purple", "home-pants-stripe-width",
                                               "road-pants-stripe-width", "road-pants-stripe-gap")},
    "b81m-TEN-road-pants-stripe": "side stripe drawn by S/work/TEN/tools/ten_road_pants.py (27 texels: red, white, navy "
                                  "line, a band with four ribs, to the standard hem row); read on the texture: the band "
                                  "takes one pants colour per row from the painter's picture",
    **{f"b81m-WAS-pants-stripe-{k}": ("side stripe drawn by S/work/WAS/tools/restripe.py in the kit's flat colours on "
                                      "straight columns to the cuff line; read on the texture: the last row above the "
                                      "cuff line keeps the coverage the old picture had there") for k in ("order", "width")},
    **{f"b81m-CLE-pants-stripe-{k}": ("side stripe drawn by b81-uniform-marks work/CLE/tools/clepaint.py: three touching "
                                      "13-texel bands, 4 blend steps; read on the texture: the hem row per column and "
                                      "(30A0) the cloth beside the old stripe") for k in ("gaps", "width")},
    "b81m-CLE-home-pants-colour": "cloth white -> orange keeping each texel's shade, the maker's mark and the hem edge "
                                  "by rule (ramps); nothing of it ships as texels",
    "b81m-NO-road-sleeve-fleur-solid": "fleur drawn by S/work/NO/tools/no_road_fleur.py from the repo's "
                                       "data/nfl2k5_scorebug_assets/logos/no.png at 8x (outline, white band, black core); "
                                       "read on the texture: size and place are round 2's boxes, which ruling 1 found to "
                                       "be the old fleur's height and centre; the old fleur cleared by rule",
    "b81u-NO-sleeve-fleur-squat": "round 2's fleur size (19 x 28 / 18 x 29 texels), kept by the row's drawn fleur",
    "b81p2-DET-dtd-neutral-grey": "Defend the Den base recolour retargeted to neutral grey by rule (ramp); only the "
                                  "authored art ships",
    **{f"b81m-{k}": "the maker's mark recoloured at each texel's own coverage by rule (ramp); none of it ships as texels"
       for k in ("ARI-pants-swoosh-colour", "ATL-pants-swoosh-colour", "LAR-pants-swoosh-colour",
                 "NO-pants-swoosh-white", "SF-pants-swoosh-colour", "MIA-pants-mark-colour")},
}
# documents whose rows still storing texels are known to hold base content whatever the measures say: the b81-art
# helmet rows the fill rule does not yet reproduce are shell shading filled from the texels around a piece, or marks
# redrawn from game art (helpers/fill/REVIEW_ME.md)
# Ruling 2 class iii, named per row (the helmet document's rows carry the cleanup's defect names, which the fill rule now
# does at build time, so the families above cannot name their drawn part): rows whose stored texels are only the
# project's own drawing, placed after the rule cleared the old mark. Measured like the families: no erasure may remain.
_KEYLINE = ("keyline drawn by the art lane's keyline.py from the league project's 2026 logo file (its de-keylined "
            "outline colour at the registered placement, anti-aliased with the logo file's own coverage against the "
            "shell colour); the old logo ink and the vents are cleared by the fill rule first")
AUTHORED_ROWS = {
    "data/nfl2k5_kit_fixes_2026_b81.json": {
        **{f"{sel}:{chunk}:txtr": _KEYLINE for sel, chunk in (("02A0", 12), ("02H0", 12), ("25A0", 12), ("25H0", 12),
                                                               ("25A7", 12), ("25H7", 12), ("25A0", 11), ("25H0", 11))},
        **{f"{sel}:12:txtr": _KEYLINE + "; the logo interior drawn from the home kit's 2026 logo (league project art, "
                                        "refine.interior)" for sel in ("02A2", "02H2")},
        **{f"{sel}:12:txtr": ("the raven mark drawn by the art lane's realmark.py from the Wikimedia Commons diagram "
                              "'Baltimore Ravens Uniforms (2026).png', scaled to the shell; the old ink and the vents "
                              "are cleared by the fill rule first") for sel in ("02A3", "02H3")},
    },
}


REFUSE_DOCUMENTS = {}  # documents refused whole (the helmet document left it in round 3: its rows are build-time rules,
                       # the drawn ones named in AUTHORED_ROWS, every other stored texel judged as class ii)
# rows whose remaining texels are known to come from game art even though the measures pass: refused by name
REFUSE = {}          # rows refused outright by name (29A0:1 left this list by ruling: RULING_1)


# class iii patterns by rule (no base content): named per document and row
PATTERNS = {
    "data/nfl2k5_classic_teams/kits.json": {
        "-": ("the Sarasota Seamen jersey mesh (b778-ss1, drawn from the SOFTDRINKTV video references): a dot mesh "
              "on every second column in the kit's own colour, the same 3,489 points for both kits; no base texel"),
    },
}


# fix 1 (coordinator's ruling (b), 2026-11-21): documents this lane never touched, shipped in v0.9. Their small polygons,
# pieces and boxes are texel data now; their inputs exist only inside a build (earlier steps write them), so they are
# listed as class iii, named per row family from the row's own note, plainly "shipped in v0.9, not measured". The point
# is to freeze them: each row's shape data is hashed in the catalog, so the gate refuses any change. A second capturing
# build to measure them is in retail-free/LATER.md (not for beta 81).
FROZEN_V09 = {
    "data/nfl2k5_kit_fixes_2026.json": "the 2026 home/away kit pass (uf1, b772)",
    "data/nfl2k5_kit_fixes_2026_alts.json": "the 2026 alternate kits (uf2, b772-b773)",
    "data/nfl2k5_kit_fixes_2026_ku1.json": "the Chiefs kit pass (ku1, b776)",
    "data/nfl2k5_moment_kits.json": "the 25th Anniversary moment kits' vector art (b775)",
    "data/nfl2k5_classic_teams/kits.json": "the classic teams' kits (b778-ss1)",
    "data/nfl2k5_uniform_alternates_2026_u3b.json": "the u3b alternate uniforms' remix boxes (b777)",
}
# measured anyway on request (coordinator, item 4): the Bills cracked-ice lines against the retail sleeve of the slot
FROZEN_MEASURED = {
    ("data/nfl2k5_kit_fixes_2026_alts.json", sel + ":3:tset"): (
        "measured against the retail 03A9/03H9 sleeve: the ten cracked-ice line polygons cover 236 texels, edge overlap "
        "0.0 (the retail sleeve holds no buffalo there; retail-free/buffalo/)") for sel in ("03A9", "03H9")}
# sw1 (coordinator's ruling): its warp masks are the destination footprints of sw1's warp of the project's donor
# swoosh (10H0:3), quadrilaterals of the warp grid clipped to the sleeve island; no colour
SW1_WARP = ("the destination footprint of sw1's warp of the project's donor swoosh (10H0:3): the warp grid's "
            "quadrilaterals clipped to the sleeve island, no colour (sw1 b777; the drawing is the project's swoosh)")


def frozen_reason(relative, owner, row):
    family = FROZEN_V09[relative]
    note = (row or {}).get("note") if isinstance(row, dict) else None
    text = f"shipped in v0.9, not measured: {family}" + (f": {note[:160]}" if isinstance(note, str) and note else "")
    extra = FROZEN_MEASURED.get((relative, owner))
    return text + ("; " + extra if extra else "")


def small_box_mask(ops, shape):
    """The union of every box under 16 texels in a row's operations (painting boxes and keep-outs together)."""
    m = np.zeros(shape, bool)
    for op in ops:
        for _key, b in RELEASE._boxes_in(op):
            if RELEASE._box_area(b) < RELEASE.SMALL:
                m[max(0, b[1]):max(0, b[3]), max(0, b[0]):max(0, b[2])] = True
    return m


def small_box_line(row, ops, raw):
    """The reviewer's per-row rule: the small boxes' edge overlap against the base the step holds (the released disc,
    where every b81u input is its before pin) and against the retail texture of the same slot."""
    c = kf._chunk_for(raw, row['chunk'])
    span = raw[c.offset:c.end_offset]
    base = kc.level0(span, row) if sha(span) == row['before_sha256'] else None
    if base is None:
        # a row pinned to an earlier step's output (the swoosh step's sleeves): its base is the texture that step
        # writes, read from a build of the branch base (B81_TEXEL_INPUTS), as kit_line reads it
        alt = INPUTS(row['selector'])
        if alt is not None and alt is not raw:
            ca = kf._chunk_for(alt, row['chunk'])
            alt_span = alt[ca.offset:ca.end_offset]
            if sha(alt_span) == row['before_sha256']:
                base = kc.level0(alt_span, row)
    shape = base.shape[:2] if base is not None else None
    retail = None
    source = RETAIL(row['selector'])
    if source is not None:
        try:
            rc = kf._chunk_for(source, row['chunk'])
            retail = kc.level0(source[rc.offset:rc.end_offset], row)
        except Exception:                                 # noqa: BLE001 - a slot the retail disc does not hold
            retail = None
    shape = shape or (retail.shape[:2] if retail is not None else None)
    if shape is None:
        return dict(small_box_texels=None, small_box_edge_base=None, small_box_edge_retail=None)
    m = small_box_mask(ops, shape)
    if not m.any():
        return {}
    out = dict(small_box_texels=int(m.sum()))
    out['small_box_edge_base'] = round(kc.edge_overlap(m, base), 4) if base is not None and base.shape[:2] == shape else None
    out['small_box_edge_retail'] = (round(kc.edge_overlap(m, retail), 4)
                                    if retail is not None and retail.shape[:2] == shape else None)
    return out


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(ops):
    return sha(json.dumps(ops, sort_keys=True, separators=(",", ":")).encode("ascii"))


def lattice(ops):
    """A pattern by rule: every texel on one regular lattice (equal steps in x and y), one colour per operation."""
    pts = np.concatenate([np.asarray(op["points"], np.int64).reshape(-1, 2) for op in ops if op["op"] == "texels"])
    if len(pts) < 16 or any(op["op"] != "texels" for op in ops):
        return False
    for axis in (0, 1):
        v = np.unique(pts[:, axis])
        steps = np.unique(np.diff(v))
        if len(v) > 1 and (len(steps) != 1 or steps[0] < 2):
            return False
    return True


def follows(base, final, shipped):
    lum = lambda a: a[..., 0].astype(np.float64) * 299 + a[..., 1] * 587 + a[..., 2] * 114
    b, f = lum(base)[shipped], lum(final)[shipped]
    if len(b) < 32 or b.std() < 2000 or f.std() < 2000:
        return False
    return bool(np.corrcoef(b, f)[0, 1] >= 0.9)


PACKAGE = None          # set by main: selector -> package bytes on the disc
RETAIL = lambda selector: None          # set by main: selector -> package bytes on the retail disc
LOGO = lambda name: None                # set by main: logos.cdf slot bytes on the disc
INPUTS = lambda selector: None          # set by main from B81_TEXEL_INPUTS: package bytes on a build of the branch base


def kit_line(row, raw):
    c = kf._chunk_for(raw, row['chunk'])
    span = raw[c.offset:c.end_offset]
    if sha(span) != row['before_sha256']:
        alt = INPUTS(row['selector'])               # the input an earlier step of the build writes (B81_TEXEL_INPUTS)
        if alt is not None and alt is not raw:
            ca = kf._chunk_for(alt, row['chunk'])
            if sha(alt[ca.offset:ca.end_offset]) == row['before_sha256']:
                return dict(kit_line(row, alt), input='a build of the branch base (B81_TEXEL_INPUTS)')
        return dict(measured=False)
    base = kc.level0(span, row)
    donors = {}
    for k, pin in sorted((row.get('donors') or {}).items()):
        k = str(k)
        if k.startswith('logo:'):                       # the league logo as the image holds it (logos.cdf)
            slot = LOGO(k[len('logo:'):])
            if slot is None or sha(slot) != pin:
                return dict(measured=False)
            donors[k] = kf.logo_rgba(slot)
            continue
        if k.startswith('retail:'):                     # the user's own retail texture, as the build reads it
            other, at = k[len('retail:'):].split(':')
            source = RETAIL(other)
            if source is None:
                return dict(measured=False)
            d = kf._chunk_for(source, int(at))
            if sha(source[d.offset:d.end_offset]) != pin:
                return dict(measured=False)
            donors[k] = kf.texture_rgba(source[d.offset:d.end_offset])
            continue
        other, at = (k.split(':') if ':' in k else (None, k))
        source = raw if other is None else PACKAGE(other)
        d = kf._chunk_for(source, int(at))
        donors[k if other else int(at)] = kf.texture_rgba(source[d.offset:d.end_offset])
    final, _scope = kf.paint(base, row['ops'], donors)
    shipped = np.zeros(base.shape[:2], bool)
    for op in row['ops']:
        if op['op'] == 'texels':
            p = np.asarray(op['points']).reshape(-1, 2)
            shipped[p[:, 1], p[:, 0]] = True
        elif op['op'] == 'runs':
            for y, x0, cs in op['rows']:
                shipped[y, x0:x0 + len(cs) // 6] = True
    cols, cnt = np.unique(base[..., :3].reshape(-1, 3), axis=0, return_counts=True)
    field = cols[cnt.argmax()].astype(np.int64)
    far = np.abs(base[..., :3].astype(np.int64) - field).max(-1) >= 48
    erased = (shipped & _scope & (np.abs(final[..., :3].astype(np.int64) - field).max(-1) <= 8)
              & (far | kc.strong_edges(base)))
    return dict(measured=True, edge_overlap=round(kc.edge_overlap(shipped, base), 4),
                base_equal=int((shipped & (final[..., :3] == base[..., :3]).all(-1)).sum()),
                erasure=int(erased.sum()), follows_base=follows(base, final, shipped))


def glyph_line(row, raw):
    c = gf._chunk_for(raw, row['chunk'])
    span = raw[c.offset:c.end_offset]
    if row['kind'] != 'digit_derived' or sha(span) != row['before_sha256']:
        return dict(measured=False)
    base = gf.digit_level0(span)
    final = gf.derive_digit(base, row['derive'])
    shipped = gd.paint_positions(row['derive'], base.shape)
    same = base.shape == final.shape
    return dict(measured=True, edge_overlap=round(gd.edge_overlap(base, row['derive']), 4),
                base_equal=int((shipped & (final == base).all(-1)).sum()) if same else 0,
                follows_base=follows(base, final, shipped) if same else False)


def main():
    global RETAIL, LOGO, INPUTS
    disc = Path(sys.argv[1])
    inputs = Path(os.environ['B81_TEXEL_INPUTS']) if os.environ.get('B81_TEXEL_INPUTS') else None
    inputs_cache = {}

    def inputs_package(selector):
        if inputs is None:
            return None
        if selector not in inputs_cache:
            inputs_cache[selector] = kf.read_kits(inputs, [selector]).get(selector)
        return inputs_cache[selector]
    INPUTS = inputs_package
    retail = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    retail_cache, logo_cache = {}, {}

    def retail_package(selector):
        if retail is None:
            return None
        if selector not in retail_cache:
            retail_cache[selector] = kf.read_kits(retail, [selector]).get(selector)
        return retail_cache[selector]

    def logo_slot(name):
        if name not in logo_cache:
            logo_cache[name] = kf.read_logos(disc, [name]).get(name)
        return logo_cache[name]

    RETAIL, LOGO = retail_package, logo_slot
    section = catalog.paint_section(ROOT)
    rows_out = {}
    with bw._Image.open(disc, writable=False) as image:
        index = bw._parsed_index(image)
        entries = {bw.logical_name_for(e.name_id): e for e in index.entries}
        cache = {}

        global PACKAGE

        def package(selector):
            if selector not in cache:
                cache.clear()
                e = entries[selector + '.IFF']
                cache[selector] = image.read_segments(index.sub_extents(e, 0, e.size))
            return cache[selector]

        def other_package(selector):                    # a donor package, read without disturbing the cache
            e = entries[selector + '.IFF']
            return image.read_segments(index.sub_extents(e, 0, e.size))

        PACKAGE = other_package
        for relative in sorted(section):
            document = json.loads((ROOT / relative).read_text(encoding='utf-8'))
            owners = catalog.texel_rows(document)
            rows = {f"{r['selector']}:{r['chunk']}:{r.get('kind', '')}": r
                    for r in document.get('textures', []) if 'selector' in r and 'chunk' in r}
            out = {}
            for owner in sorted(owners, key=lambda k: (k.split(':')[0], k)):
                ops = owners[owner]
                line = dict(sha256=digest(ops))
                refused = REFUSE.get(relative, {}).get(owner) or REFUSE_DOCUMENTS.get(relative)
                named = RULING_1.get(relative, {}).get(owner)
                row = rows.get(owner)
                families = set(row.get('defects', ())) if row is not None else set()
                if refused:
                    line.update(cls='ii', reason=refused, passes=False, measured=True)
                elif named:
                    line.update(cls='iii', reason='ruling 1: ' + named)
                elif row is not None and families and families <= set(CLASS_III) and 'ops' in row:
                    measured = kit_line(row, package(row['selector']))
                    if measured.get('measured') and measured['erasure'] == 0:
                        # ruling 1's principle: art drawn by the project's code from its own shape over a region cleared
                        # by rule may land on the old mark; texels where it happens to equal the old mark are counted
                        line.update(cls='iii', reason='authored on a region cleared by rule: '
                                    + '; '.join(CLASS_III[f] for f in sorted(families)), **measured)
                    else:
                        line.update(cls='ii', reason='authored families, but an erasure is still stored as texels',
                                    passes=False, **measured)
                elif owner in AUTHORED_ROWS.get(relative, {}) and row is not None:
                    measured = kit_line(row, package(row['selector']))
                    if measured.get('measured') and measured['erasure'] == 0:
                        line.update(cls='iii', reason='authored on a region cleared by rule: '
                                    + AUTHORED_ROWS[relative][owner], **measured)
                    else:
                        line.update(cls='ii', reason='authored row, but unmeasured or an erasure is still stored',
                                    passes=False, **measured)
                elif owner in PATTERNS.get(relative, {}):
                    line.update(cls='iii', reason=PATTERNS[relative][owner] + (
                        "; " + frozen_reason(relative, owner, row) if relative in FROZEN_V09 else ""))
                elif relative in FROZEN_V09:
                    line.update(cls='iii', reason=frozen_reason(relative, owner, row), measured=False)
                elif relative == "data/nfl2k5_kit_fixes_2026_sw1.json" and all(op['op'] == 'warp' for op in ops):
                    line.update(cls='iii', reason=SW1_WARP, measured=False)
                else:
                    line.update(cls='ii', reason='the base is built from the user\'s retail disc at build time')
                    if row is not None:
                        raw = package(row['selector'])
                        line.update(glyph_line(row, raw) if 'derive' in row else kit_line(row, raw))
                    else:
                        line.update(measured=False)
                    line['passes'] = bool(line.get('measured') and line['edge_overlap'] <= EDGE_OVERLAP_LIMIT
                                          and line['base_equal'] == 0 and not line['follows_base'])
                if row is not None and 'selector' in row and 'chunk' in row and relative not in FROZEN_V09:
                    line.update(small_box_line(row, ops, package(row['selector'])))
                out[owner] = line
            rows_out[relative] = out
    # fix 1 of the re-check: the whole-document SHA-256 of every data JSON that edits textures (operations, texture pins,
    # shapes or texel data), as measured or classified here; the catalog pins exactly these
    # (tools/b77/modern_art_png_catalog.py refuses a document changed since)
    pinned = {}
    for path in sorted((ROOT / 'data').rglob('*.json')):
        data = path.read_bytes()
        try:
            parsed = json.loads(data.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            continue
        if RELEASE._edits_textures(parsed):
            pinned[path.relative_to(ROOT).as_posix()] = sha(data)
    document = dict(schema=SCHEMA, limit=EDGE_OVERLAP_LIMIT, rows=rows_out, documents=pinned,
                    about=("Ruling 2 classes of every data row that stores texels; class ii rows measured on the released "
                           "v0.9 disc by tools/b81_uniforms/texel_rows.py; the release check refuses a class ii row that "
                           "does not pass"))
    OUT.write_text(json.dumps(document, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    for relative, out in rows_out.items():
        ii = [v for v in out.values() if v['cls'] == 'ii']
        print(relative, 'rows', len(out), 'class iii', len(out) - len(ii), 'class ii', len(ii),
              'passing', sum(v['passes'] for v in ii), 'unmeasured', sum(not v.get('measured') for v in ii))


if __name__ == '__main__':
    main()
