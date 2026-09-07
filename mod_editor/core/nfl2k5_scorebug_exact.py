"""Broadcast-derived scorebug scene v1. EXPERIMENTAL / UNWITNESSED.

The reference is the real LV/HOU JPEG, never the older staged targets. This
module authors native scene inputs; it is not a renderer or a gameplay claim.
Coordinates map the entire broadcast to the game's active 640x448 viewport.
The existing fixed-span writer and its retail wrapper/scratch budget own IO.
"""
from __future__ import annotations

import struct

VERSION = "espn-broadcast-exact-v1"
RED_BIAS = -20
REFERENCE_SHA256 = 'f88b98687827c753882d8c5186eb186095510228b039c6d7a2e9e9d88e725e14'  # Filled from the supplied image by the evidence builder.
SOURCE_RAILS = (434, 942, 1488, 1054)
SOURCE_REGIONS = {
    "frame_rim": SOURCE_RAILS,
    "left_panel": (438, 946, 834, 1049),
    "centre_pill": (831, 947, 1089, 987),
    "clock_strip": (839, 992, 1083, 1045),
    "right_panel": (1088, 946, 1484, 1049),
}


def hud_box(box):
    a, b, c, d = box
    return (a / 3, 16 + b * 448 / 1080, c / 3, 16 + d * 448 / 1080)


def scene_box(box):
    a, b, c, d = hud_box(box)
    return (a - 320, 424 - d, c - 320, 424 - b)


RAILS = hud_box(SOURCE_RAILS)
FRAME = scene_box(SOURCE_RAILS)
PANELS = {"away": scene_box(SOURCE_REGIONS["left_panel"]),
          "home": scene_box(SOURCE_REGIONS["right_panel"])}
PILL = scene_box(SOURCE_REGIONS["centre_pill"])
STRIP = scene_box(SOURCE_REGIONS["clock_strip"])
FRAME_COLOR = (37, 38, 37, 255)
REGIONS = {"frame": (0, 0, 24, 24), "down": (0, 24, 64, 40),
           "strip": (0, 40, 64, 60), "solid": (1, 62, 2, 63)}
# Native ordinary text draws use FONT metrics directly. Their +30/+34 fields
# are shadow offsets. Scores use native rotating parent/leaf matrices.
ANCHORS = {
    "away_city": (-164, -4, -64), "home_city": (120, -4, -64),
    "away_score": (-68, -26.733, -59), "home_score": (66.5, -26.733, -59),
    "quarter": (-31.333, -21.355, -4), "clock_a": (19.833, -19.904, -4),
    "clock_b": (19.833, -19.904, -4), "drop_clock": (28.333, -19.989, -4),
    "drop_down": (-.5, 2.289, -4), "drop_yellow": (0, -1, -4),
    "drop_red": (0, -1, -4), "drop_hangtime": (0, -1, -4),
    "drop_ball_on": (0, 3, -4),
}


def atlas(*, revision=3, red_bias=None):
    from PIL import Image, ImageDraw
    if red_bias is None:
        red_bias = RED_BIAS
    im = Image.new("RGBA", (64, 64), FRAME_COLOR)
    d = ImageDraw.Draw(im)
    # A nine-slice tile gives the 351-pixel frame one-pixel rails and small
    # corners instead of stretching a 64-pixel border over the entire bar.
    d.rectangle((0, 0, 23, 23), fill=(0, 0, 0, 0))
    rim = (171, 172, 170, 255) if revision > 0 else (122, 124, 132, 255)
    d.rounded_rectangle((0, 0, 23, 23), 3, fill=FRAME_COLOR, outline=rim)
    d.line((3, 1, 20, 1), fill=(70, 71, 69, 255))
    d.line((3, 22, 20, 22), fill=(18, 19, 18, 255))
    d.rectangle((0, 24, 63, 39), fill=FRAME_COLOR)
    red = (165, 13, 37, 255) if revision > 0 else (208, 2, 27, 255)
    d.rounded_rectangle((0, 24, 63, 39), 4, fill=(69, 38, 44, 255))
    d.rounded_rectangle((1, 25, 62, 38), 3, fill=red, outline=(194, 32, 57, 255))
    d.line((5, 25, 58, 25), fill=(214, 57, 77, 255))
    if revision >= 3:
        for y in range(26, 38):
            for x in range(2, 62):
                if im.getpixel((x, y)) == red:
                    t = abs(x - 31.5) / 31.5
                    im.putpixel((x, y), (round(148 + 52 * t), round(22 - 4 * t), round(43 + 3 * t), 255))
    if red_bias:
        for y in range(24, 40):
            for x in range(64):
                rr, gg, bb, aa = im.getpixel((x, y))
                if rr > gg * 2:
                    im.putpixel((x, y), (min(255, max(0, rr + red_bias)), gg, bb, aa))
    d.rectangle((0, 40, 63, 59), fill=FRAME_COLOR)
    d.rounded_rectangle((0, 40, 63, 59), 8, fill=(11, 13, 12, 255))
    d.rounded_rectangle((1, 41, 62, 58), 7, fill=(148, 143, 141, 255))
    d.rounded_rectangle((2, 42, 61, 57), 6, fill=(239, 239, 232, 255))
    # The photograph's play-clock field is light, with a dark separator and
    # dark digits. Preserve that measured fact, despite the brief's prose.
    d.line((46, 44, 46, 56), fill=(168, 167, 161, 255))
    d.rectangle((0, 61, 3, 63), fill=(248, 250, 243, 255))
    return im


def mesh(retail, *, runtime=False, revision=2):
    from . import nfl2k5_scorebug_ingame as r
    m = r.layout.Mesh(retail)
    # Every obsolete tab/mark starts degenerate, inside the actual frame.
    for v in range(r.layout.VCOUNT):
        m.pos[v] = [0, 0, -3]
        m.uv_edit[v] = (-1 + 1.5 / 32, -1 + 62.5 / 32)
        struct.pack_into("<I", m.buf, r.layout.S1 + v * 10, 0xffffffff)
        struct.pack_into("<h", m.buf, r.layout.S1 + v * 10 + 8, 0)

    strips = [indices for _, indices in r.layout.strips(retail)]

    def quad(vertices, box, tile, *, z=0):
        vertices = list(vertices)
        indices = next(indices for indices in strips if vertices[0] in indices)
        first = next(i for i in range(len(indices) - 2)
                     if indices[i:i+3] == vertices[:3])
        reverse = bool(first % 2)
        a, b, c, d = box
        s, t, u, w = tile
        corners = ((0, 1), (1, 1), (0, 0), (1, 0))
        if reverse:
            corners = ((0, 0), (1, 0), (0, 1), (1, 1))
        for i, v in enumerate(vertices):
            x, y = corners[min(i, 3)]
            m.pos[v] = [a + (c - a) * x, d - (d - b) * y, z]
            m.uv_edit[v] = ((s + (u - s) * x) / 32 - 1,
                            (t + (w - t) * y) / 32 - 1)

    groups = [list(range(96, 104)), list(range(104, 112)), list(range(112, 118))]
    groups += [list(range(n, n + 4)) for n in range(118, 166, 4)]
    groups2 = [list(range(166, 174))] + [list(range(n, n + 4)) for n in range(174, 230, 4)]
    a, b, c, d = FRAME
    xs, ys = (a, a + 3, c - 3, c), (b, b + 3, d - 3, d)
    for material_groups in (groups, groups2):
        for iy in range(3):
            for ix in range(3):
                uvx, uvy = (0, 3, 21, 24), (24, 21, 3, 0)
                quad(material_groups[iy * 3 + ix], (xs[ix], ys[iy], xs[ix + 1], ys[iy + 1]),
                     (uvx[ix], uvy[iy + 1], uvx[ix + 1], uvy[iy]))
        if not runtime:
            for i, source in enumerate(((716, 1032, 735, 1039), (747, 1032, 766, 1039),
                                        (777, 1032, 796, 1039), (1120, 1032, 1139, 1039),
                                        (1150, 1032, 1169, 1039), (1180, 1032, 1199, 1039))):
                quad(material_groups[9 + i], scene_box(source), (1.5, 62.5, 1.5, 62.5), z=-2)
    # cscore's first live triangle starts at index 48 after a duplicate. Its
    # strip parity is opposite the down strip's first triangle.
    quad(range(48, 64), STRIP, REGIONS["strip"], z=-3)
    # The clock stream revisits 48 and 49 in a second fan. Collapse that fan
    # to the 48-49 edge, otherwise it paints a third overlapping triangle.
    for v in range(52, 60):
        m.pos[v] = m.pos[49][:]
        m.uv_edit[v] = m.uv_edit[49]
    quad(range(64, 80), PILL, REGIONS["down"], z=-3)
    if runtime:
        # UV helper units are 1/64; these are the texel centres of 128x32.
        quad(range(230, 246), PANELS["away"], (.25, 1, 63.75, 63), z=-2)
        # Independent hscore material, exactly the owner's existing lookup.
        quad(range(80, 96), PANELS["home"], (.25, 1, 63.75, 63), z=-2)
    for side, parent in (("away", 23), ("home", 26)):
        box = PANELS[side]
        m.world[parent][:2] = [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2]
    for name, xyz in ANCHORS.items():
        i, leaf = r.layout.T[name], r.layout.T[name + "_l"]
        delta = [bb - aa for aa, bb in zip(m.world[i], m.world[leaf])]
        m.world[i] = list(xyz)
        m.world[leaf] = [aa + bb for aa, bb in zip(xyz, delta)]
    return m


def xbe_specs(specs):
    """Extend the existing static owner with font selectors and colour fields."""
    dark = 0xff242622
    colors = {0xa95894: 0, 0xa958bc: 0, 0xa958e4: dark, 0xa958e8: dark,
              0xa9590c: dark, 0xa95910: dark, 0xa95934: dark, 0xa95938: dark,
              0xa95a48: dark}
    result = [(va, old, struct.pack("<I", colors[va]) if va in colors else new, label)
              for va, old, new, label in specs]
    # Suppress only the native abbreviations. Runtime panels carry wordmarks;
    # the static panels are the requested anonymous neutral subset.
    result += [(va, struct.pack("<I", 0xffc0c000), bytes(4), "neutral team label")
               for va in (0xa95898, 0xa958c0)]
    slots = {0xa958d8: 3, 0xa95900: 3, 0xa95928: 3,
             0xa95950: 7, 0xa95988: 7, 0xa959d0: 3,
             0xa95a40: 3, 0xa95ab0: 3, 0xa95b20: 3, 0xa95b90: 3, 0xa95c00: 3}
    result += [(va, bytes(4), struct.pack("<I", slot), "scorebug FONT slot")
               for va, slot in slots.items()]
    # FBE30 is the scorebug-only play-clock formatter. Reuse the existing
    # UTF-16 format suffix "%02d" by skipping its leading colon, no new string
    # allocation and no change to rounding, urgency or the callback's ABI.
    result.append((0xfbe43, struct.pack("<I", 0xe6c438), struct.pack("<I", 0xe6c43a),
                   "play clock without leading colon"))
    return result


# Original five-column capitals. These are authored, portable pixel wordmarks,
# not a dependency on installed fonts or a claim to official team typography.
CAPS = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ49", (
    "01110/11011/11011/11111/11011/11011/11011",
    "11110/11011/11011/11110/11011/11011/11110",
    "01111/11000/11000/11000/11000/11000/01111",
    "11110/11011/11011/11011/11011/11011/11110",
    "11111/11000/11000/11110/11000/11000/11111",
    "11111/11000/11000/11110/11000/11000/11000",
    "01111/11000/11000/11011/11011/11011/01111",
    "11011/11011/11011/11111/11011/11011/11011",
    "11111/01110/01110/01110/01110/01110/11111",
    "00111/00011/00011/00011/11011/11011/01110",
    "11011/11011/11110/11100/11110/11011/11011",
    "11000/11000/11000/11000/11000/11000/11111",
    "11011/11111/11111/11011/11011/11011/11011",
    "11011/11111/11111/11111/11011/11011/11011",
    "01110/11011/11011/11011/11011/11011/01110",
    "11110/11011/11011/11110/11000/11000/11000",
    "01110/11011/11011/11011/11111/01110/00011",
    "11110/11011/11011/11110/11100/11011/11011",
    "01111/11000/11000/01110/00011/00011/11110",
    "11111/01110/01110/01110/01110/01110/01110",
    "11011/11011/11011/11011/11011/11011/01110",
    "11011/11011/11011/11011/11011/01110/00100",
    "11011/11011/11011/11011/11111/11111/11011",
    "11011/11011/01110/00100/01110/11011/11011",
    "11011/11011/11011/01110/01110/01110/01110",
    "11111/00011/00110/01100/11000/11000/11111",
    "00110/01110/11010/11010/11111/00010/00010",
    "01110/11011/11011/01111/00011/00011/01110",
)))
NICKNAMES = dict(zip(
    "ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LAC LAR LV MIA MIN NE NO NYG NYJ PHI PIT SEA SF TB TEN WAS".split(),
    "CARDINALS FALCONS RAVENS BILLS PANTHERS BEARS BENGALS BROWNS COWBOYS BRONCOS LIONS PACKERS TEXANS COLTS JAGUARS CHIEFS CHARGERS RAMS RAIDERS DOLPHINS VIKINGS PATRIOTS SAINTS GIANTS JETS EAGLES STEELERS SEAHAWKS 49ERS BUCCANEERS TITANS COMMANDERS".split()))


def wordmark(text):
    from PIL import Image
    im = Image.new("RGBA", (6 * len(text) - 1, 7))
    for n, letter in enumerate(text):
        for y, row in enumerate(CAPS[letter].split("/")):
            for x, bit in enumerate(row):
                if bit == "1":
                    im.putpixel((n * 6 + x, y), (248, 250, 243, 255))
    return im


def panel(span, team, side, *, timeouts=3):
    from PIL import Image, ImageDraw
    from . import nfl2k5_scorebug_ingame as r
    if side not in ("home", "away") or type(timeouts) is not int or not 0 <= timeouts <= 3:
        raise ValueError("invalid scorebug side/timeouts")
    record = None if team is None else r.TEAM_LOGOS[team]
    # Validate provenance even when a source logo would be hidden by its alpha.
    logo = None if record is None else r.texture_image(span, record)
    primary = FRAME_COLOR[:3] if record is None else tuple(bytes.fromhex(record["primary"][1:]))
    # Literal broadcast colour roles: Raiders silver and Texans red are the
    # secondary colours in teams.json. Do not mistake its primary for the photo.
    if team in ("LV", "HOU"):
        primary = (224, 227, 224) if team == "LV" else (215, 18, 51)
    im = Image.new("RGBA", (128, 32))
    d = ImageDraw.Draw(im)
    for x in range(128):
        distance = x if side == "away" else 127 - x
        t = min(1, distance / (57 if team == "LV" else 66))
        for y in range(32):
            shade = 1 - .35 * y / 31 if team == "LV" else 1
            rgb = tuple(round(c * (1 - t) * shade + b * t)
                        for c, b in zip(primary, FRAME_COLOR[:3]))
            im.putpixel((x, y), rgb + (255,))
    if logo is not None:
        bounds = logo.getchannel("A").getbbox()
        if bounds is None:
            raise ValueError("retail team logo is empty")
        width = 48 if team == "HOU" else 43
        logo = logo.crop(bounds).resize((width, 31), Image.Resampling.LANCZOS)
        x = 14 if side == "away" else 68 if team == "HOU" else 71
        im.alpha_composite(logo, (x, 0))
        # RAIDERS already exists in the actual shield. Every other team gets
        # authored small caps in its outer panel, above the logo body.
        if team != "LV":
            mark = wordmark(NICKNAMES[team])
            mark = mark.resize((min(43, mark.width), 4), Image.Resampling.LANCZOS)
            im.alpha_composite(mark, (x + (43 - mark.width) // 2, 0))
    for n, x in enumerate((91, 101, 111)):
        dx = x if side == "away" else 127 - x - 6
        d.polygon(((dx + 1, 27), (dx + 6, 27), (dx + 5, 29), (dx, 29)),
                  fill=(248, 250, 243, 255) if n < timeouts else (66, 66, 65, 255))
    return im
