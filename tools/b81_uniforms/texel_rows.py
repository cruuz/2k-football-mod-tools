#!/usr/bin/env python3
"""Ruling 2 (b81-retail-free-art): the provenance class and the measured base content of every data row that stores
texels, for the release gate to judge.

  python3 tools/b81_uniforms/texel_rows.py "<released v0.9 disc>"      -> packaging/nfl2k5_texel_rows.json

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
A row whose input is not on the disc (an earlier step of the same build writes it) is recorded unmeasured. The release
check refuses a class ii row that fails any of these or is unmeasured."""
from __future__ import annotations

import hashlib
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
        for sel in ("06H0", "06A0", "06H5", "06A5", "06H6", "06A6")},
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
}
# documents whose rows still storing texels are known to hold base content whatever the measures say: the b81-art
# helmet rows the fill rule does not yet reproduce are shell shading filled from the texels around a piece, or marks
# redrawn from game art (helpers/fill/REVIEW_ME.md)
REFUSE_DOCUMENTS = {
    "data/nfl2k5_kit_fixes_2026_b81.json": ("a helmet piece repainted from the shell's own shading or a mark redrawn "
                                            "from game art, not yet a build-time rule"),
}
# rows whose remaining texels are known to come from game art even though the measures pass: refused by name
REFUSE = {
    "data/nfl2k5_kit_fixes_2026_b81u.json": {
        "29A0:1:tset": ("the road shoulder swoosh is the 29H0 sleeve swoosh art (a texture the build makes from the retail "
                        "disc) redrawn on the body by work/fix/R2C/tools/waspaint.py; its texels still ship"),
    },
}


# class iii patterns by rule (no base content): named per document and row
PATTERNS = {
    "data/nfl2k5_classic_teams/kits.json": {
        "-": ("the Sarasota Seamen jersey mesh (b778-ss1, drawn from the SOFTDRINKTV video references): a dot mesh "
              "on every second column in the kit's own colour, the same 3,489 points for both kits; no base texel"),
    },
}


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


def kit_line(row, raw):
    c = kf._chunk_for(raw, row['chunk'])
    span = raw[c.offset:c.end_offset]
    if sha(span) != row['before_sha256']:
        return dict(measured=False)
    base = kc.level0(span, row)
    donors = {}
    for k, pin in sorted((row.get('donors') or {}).items()):
        k = str(k)
        if k.startswith('retail:'):
            return dict(measured=False)                 # a donor from the retail disc: measured by the rule's own tests
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
    disc = Path(sys.argv[1])
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
                elif owner in PATTERNS.get(relative, {}):
                    line.update(cls='iii', reason=PATTERNS[relative][owner])
                else:
                    line.update(cls='ii', reason='the base is built from the user\'s retail disc at build time')
                    if row is not None:
                        raw = package(row['selector'])
                        line.update(glyph_line(row, raw) if 'derive' in row else kit_line(row, raw))
                    else:
                        line.update(measured=False)
                    line['passes'] = bool(line.get('measured') and line['edge_overlap'] <= EDGE_OVERLAP_LIMIT
                                          and line['base_equal'] == 0 and not line['follows_base'])
                out[owner] = line
            rows_out[relative] = out
    document = dict(schema=SCHEMA, limit=EDGE_OVERLAP_LIMIT, rows=rows_out,
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
