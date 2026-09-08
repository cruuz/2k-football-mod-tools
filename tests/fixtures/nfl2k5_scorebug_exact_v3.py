"""Broadcast-derived scorebug scene v3. EXPERIMENTAL / UNWITNESSED.

The frame comes from the LV/HOU JPEG; static text fit uses Noah's r64 captures.
This module authors native scene inputs, not a renderer or a gameplay claim.
Frame coordinates map the broadcast to the game's active 640x448 viewport.
The existing fixed-span writer and its retail wrapper/scratch budget own IO.
"""
from __future__ import annotations

import struct

VERSION = "espn-broadcast-exact-v3"
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
# Retail FONT4 needs 31/40/18 advance units for 4TH/15:00/40. The
# static fallback cannot use the smaller diagnostic FONTs. Keep the frame,
# expand its lower row, and reserve real padding on both sides of each word.
STATIC_STRIP = (-56., STRIP[1], 56., STRIP[3])
STATIC_PILL = (-52., PILL[1], 52., PILL[3])
STATIC_CELLS = {"quarter": (264., 301.), "game_clock": (301., 347.),
                "play_clock": (347., 376.)}
EVENT_ROW = STATIC_PILL
FRAME_COLOR = (37, 38, 37, 255)
REGIONS = {"frame": (0, 0, 24, 24), "down": (0, 24, 64, 40),
           "strip": (0, 40, 64, 60), "solid": (1, 62, 2, 63)}
# Authored broadcast details. The evidence tool retains both neighbours of
# each selected value; the reference is used only for measurement/comparison.
STYLE = {'clock_fill': 247, 'clock_radius': 9, 'hou_dx': 0, 'hou_dy': -3, 'hou_height': 39, 'hou_width': 49, 'lv_dx': 0, 'lv_dy': -4, 'lv_height': 41, 'lv_width': 42, 'pill_radius': 0, 'red': 224, 'red_reflection': 1.9, 'rim': 1, 'rim_gain': 7, 'rim_red': -9, 'separator': 200, 'separator_left': 1, 'silver': 222, 'silver_falloff': 0.35, 'silver_reflection': 0.4, 'wordmark_hou': 0, 'wordmark_weight': 0, 'separator_profile': 1, 'separator_right_x': 46.5, 'separator_left_x': 16.0}

# Native ordinary text draws use FONT metrics directly. Their +30/+34 fields
# are shadow offsets. Scores use native rotating parent/leaf matrices.
ANCHORS = {
    "away_city": (-168, -10, -64), "home_city": (132, -10, -64),
    "away_score": (-92, -26.733, -59), "home_score": (92, -26.733, -59),
    "quarter": (-37, -19, -4), "clock_a": (24, -19, -4),
    "clock_b": (24, -19, -4), "drop_clock": (41.5, -19, -4),
    "drop_down": (-.5, 2.289, -4), "drop_yellow": (0, -24, -8),
    "drop_red": (0, -24, -8), "drop_hangtime": (0, -24, -8),
    "drop_ball_on": (0, -24, -8),
}
# Private FONTs are available only in the diagnostic runtime collection.
# Keep the fixed-span static scene on its retail FONT anchors.
RUNTIME_ANCHORS = {'away_city': (-75, 0, -64), 'away_score': [-67.75, -27.651, -59], 'clock_a': [16.833, -20.904, -4], 'clock_b': [16.833, -20.904, -4], 'drop_ball_on': [0, 3, -4], 'drop_clock': [28.833, -18.989, -4], 'drop_down': [-0.5, 2.289, -4], 'drop_hangtime': [0, -1, -4], 'drop_red': [0, -1, -4], 'drop_yellow': [0, -1, -4], 'home_city': (59.5, 0, -64), 'home_score': [66.75, -27.651, -59], 'quarter': [-28.333, -18.855, -4]}
RUNTIME_ANCHORS["drop_ball_on"] = (0, -26, -8)
for _event in ("drop_yellow", "drop_red", "drop_hangtime"):
    RUNTIME_ANCHORS[_event] = (0, -26, -8)

# Events replace the down text in its existing pill; the three clock cells
# keep their geometry and depth. The diagnostic runtime keeps its v2 scene.
for _event in ("drop_ball_on", "drop_yellow", "drop_red", "drop_hangtime"):
    ANCHORS[_event] = (0, 2.289, -8)


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
    if STYLE['rim']:
        # Horizontal knots describe silver, neutral and red reflection roles.
        knots = ((0., (239,242,235)), (.24, (86,89,83)), (.40, (48,43,41)),
                 (.51, (57,51,46)), (.64, (151,72,78)), (1., (226,49,68)))
        for x in range(24):
            t = min(1., max(0., (x-3)/17))
            lo, hi = next((lo, hi) for lo, hi in zip(knots, knots[1:]) if lo[0] <= t <= hi[0])
            alpha = (t-lo[0])/(hi[0]-lo[0])
            rgb = [round(a*(1-alpha)+b*alpha) + STYLE['rim_gain'] for a,b in zip(lo[1],hi[1])]
            rgb[0] += round(STYLE['rim_red'] * max(0., (t-.5)*2))
            rgb = tuple(min(255,max(0,c)) for c in rgb)
            for y, gain in ((0,1.), (1,.65), (22,.65), (23,.09)):
                if im.getpixel((x,y))[3]:
                    im.putpixel((x,y), tuple(round(c*gain) for c in rgb)+(255,))
        for y in range(2,22):
            im.putpixel((0,y),(210,213,207,255))
            im.putpixel((23,y),(211,34,52,255))
    d.rectangle((0, 24, 63, 39), fill=FRAME_COLOR)
    red = (165, 13, 37, 255) if revision > 0 else (208, 2, 27, 255)
    d.rounded_rectangle((0, 24, 63, 39), STYLE["pill_radius"], fill=(69, 38, 44, 255))
    d.rounded_rectangle((1, 25, 62, 38), max(0, STYLE["pill_radius"]-1), fill=red, outline=(194, 32, 57, 255))
    if STYLE.get("pill_profile", 0):
        # The upper shoulders meet the frame; only the lower corners turn in.
        d.rectangle((0,24,63,31), fill=(69,38,44,255))
        d.rectangle((1,25,62,31), fill=red)
        d.line((1,25,62,25), fill=(194,32,57,255))
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
    d.rectangle((0, 40, 63, 59), fill=(55, 56, 54, 255))
    d.rectangle((1, 41, 62, 58), fill=(247, 247, 240, 255))
    # Separate, squared cells, with the requested dark play-clock field.
    d.rectangle((47, 41, 62, 58), fill=(35, 38, 34, 255))
    d.line((21, 41, 21, 58), fill=(91, 92, 87, 255))
    d.line((47, 41, 47, 58), fill=(65, 66, 61, 255))
    d.rectangle((0, 61, 3, 63), fill=(248, 250, 243, 255))
    d.rectangle((4, 61, 7, 63), fill=FRAME_COLOR)
    d.rectangle((8, 61, 11, 63), fill=(255, 255, 255, 255))
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
                box = list(scene_box(source))
                shift = -24 if i < 3 else 25.5
                box[0] += shift; box[2] += shift
                quad(material_groups[9 + i], box, (1.5, 62.5, 1.5, 62.5), z=-2)
    # cscore's first live triangle starts at index 48 after a duplicate. Its
    # strip parity is opposite the down strip's first triangle.
    quad(range(48, 64), STRIP if runtime else STATIC_STRIP, REGIONS["strip"], z=-3)
    # The clock stream revisits 48 and 49 in a second fan. Collapse that fan
    # to the 48-49 edge, otherwise it paints a third overlapping triangle.
    for v in range(52, 60):
        m.pos[v] = m.pos[49][:]
        m.uv_edit[v] = m.uv_edit[49]
    quad(range(64, 80), PILL if runtime else STATIC_PILL, REGIONS["down"], z=-3)
    # Retail can request events and down together. Static events cover the
    # down text at the same pill geometry, with clocks clear beneath them.
    event_row = (-64., -28., 64., -3.) if runtime else EVENT_ROW
    event_tile = (5.5, 62.5, 5.5, 62.5) if runtime else REGIONS["down"]
    quad(range(16, 32), event_row, event_tile, z=-7)
    for vertices in (range(0, 16), range(32, 48)):
        quad(vertices, event_row, event_tile, z=-7)
    # Both scene variants share the pinned XBE material-name descriptor.
    # The diagnostic runtime keeps this former mark geometrically collapsed.
    name = "score_buga\0".encode("utf-16le")
    m.buf[0x3f8c:0x3f8c+len(name)] = name
    if not runtime:
        quad(range(80, 96), EVENT_ROW, event_tile, z=-7)
        # Zscore is the away panel; the old corner mark becomes the home
        # panel. Both have their own existing native material record. Their
        # vertices stay on the root palette, independent of score rotation.
        quad(range(230, 246), PANELS["away"], (9.5, 62.5, 9.5, 62.5), z=-1)
        quad(range(262, 274), PANELS["home"], (9.5, 62.5, 9.5, 62.5), z=-1)
        # This old mark is a list of disjoint triangles separated by doubled
        # indices, not a continuous quad strip. Supply the other half through
        # its second triangle (265,266,267); all later triangles stay collapsed.
        bottom_right = m.pos[265][:]
        m.pos[265] = m.pos[264][:]
        m.pos[266] = m.pos[263][:]
        m.pos[267] = bottom_right
        # Neutral until the first live abbreviation draw, then native tint.
        for material in (0x4c0, 0x6c0):
            struct.pack_into("<I", m.buf, material+0x14, 0xffffffff)
            struct.pack_into("<I", m.buf, material+0x18, 0xff252625)
    if runtime:
        # UV helper units are 1/64; these are the texel centres of 128x32.
        quad(range(230, 246), PANELS["away"], (.25, 1, 63.75, 63), z=-2)
        # Independent hscore material, exactly the owner's existing lookup.
        quad(range(80, 96), PANELS["home"], (.25, 1, 63.75, 63), z=-2)
    for side, parent in (("away", 23), ("home", 26)):
        box = PANELS[side]
        m.world[parent][:2] = [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2]
    for name, xyz in (RUNTIME_ANCHORS if runtime else ANCHORS).items():
        i, leaf = r.layout.T[name], r.layout.T[name + "_l"]
        delta = [bb - aa for aa, bb in zip(m.world[i], m.world[leaf])]
        m.world[i] = list(xyz)
        m.world[leaf] = [aa + bb for aa, bb in zip(xyz, delta)]
    return m


def xbe_specs(specs):
    """Extend the existing static owner with font selectors and colour fields."""
    dark = 0xff242622
    colors = {0xa95894: 0xffffffff, 0xa958bc: 0xffffffff, 0xa958e4: dark, 0xa958e8: dark,
              0xa9590c: dark, 0xa95910: dark, 0xa95934: dark, 0xa95938: dark,
              0xa95a48: 0xffffffff}
    result = [(va, old, struct.pack("<I", colors[va]) if va in colors else new, label)
              for va, old, new, label in specs]
    # Preserve the native possession predicate: white off-ball, yellow on-ball.
    result += [(va, struct.pack("<I", 0xffc0c000), struct.pack("<I", 0xffffff40), "live possession highlight")
               for va in (0xa95898, 0xa958c0)]
    slots = {0xa958d8: 3, 0xa95900: 3, 0xa95928: 3,
             0xa95950: 7, 0xa95988: 7, 0xa959d0: 3,
             0xa95a40: 3, 0xa95ab0: 3, 0xa95b20: 3, 0xa95b90: 3, 0xa95c00: 3}
    result += [(va, bytes(4), struct.pack("<I", slot), "scorebug FONT slot")
               for va, slot in slots.items()]
    result += [(va, struct.pack("<I", 4), struct.pack("<I", 3), "live team FONT4")
               for va in (0xa95888, 0xa958b0)]
    from . import nfl2k5_scorebar_v3
    result.extend(nfl2k5_scorebar_v3.xbe_specs())
    result.append((0xa95b94, struct.pack("<I", 1), struct.pack("<I", 3), "center ball label in its own row"))
    # These literals are used only by FBEB0, the native ball/field-goal label.
    # Keep formatting and branches; replace the line break within its own row.
    for va, text in ((0xe6c484, "Ball at\nMidfield"), (0xe6c4a8, "Ball on\n%s %d"),
                     (0xe6c4c4, "%d Yard\nAttempt")):
        old = (text + "\0").encode("utf-16le")
        result.append((va, old, (text.replace("\n", " ") + "\0").encode("utf-16le"), "single-line ball label"))
    # FBE30 is the scorebug-only play-clock formatter. Reuse the existing
    # UTF-16 format suffix "%02d" by skipping its leading colon, no new string
    # allocation and no change to rounding, urgency or the callback's ABI.
    # V3 owns the complete FBE30 formatter span, including this operand.
    # Compact the four existing quarter cases into a common copy/capitalize
    # tail, entirely inside their original instruction span. Only this
    # callback's caller-owned buffer changes; shared 1st/2nd strings and the
    # native overtime branch remain retail. PUSH ECX at FC090 saves the buffer.
    old = bytes.fromhex("bae4c3e600e8004af3ff59c3baecc3e600e8f449f3ff59c3"
                        "baf4c3e600e8e849f3ff59c3bafcc3e600e8dc49f3ff59c3")
    new = bytearray()
    for i, literal in enumerate((0xe6c3e4, 0xe6c3ec, 0xe6c3f4, 0xe6c3fc)):
        new += b"\xba" + struct.pack("<I", literal) + b"\xeb" + bytes((21 - i * 7,))
    new += b"\xe8" + struct.pack("<i", 0x30ab0 - (0xfc0a6 + len(new) + 5))
    new += b"\x59"  # restore the caller's buffer as the uppercase argument
    new += b"\xe9" + struct.pack("<i", 0x30f20 - (0xfc0a6 + len(new) + 5))
    result.append((0xfc0a6, old, bytes(new).ljust(len(old), b"\x90"), "quarter capitals in existing cases"))
    for i in range(1, 4):
        result.append((0xfc0f0 + i * 4, struct.pack("<I", 0xfc0a6 + i * 12),
                       struct.pack("<I", 0xfc0a6 + i * 7), "quarter case table"))
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
    from math import exp
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
        primary = (STYLE["silver"], min(255,STYLE["silver"]+3), STYLE["silver"]) if team == "LV" else (STYLE["red"], 18, 51)
    im = Image.new("RGBA", (128, 32))
    d = ImageDraw.Draw(im)
    for x in range(128):
        distance = x if side == "away" else 127 - x
        t = min(1, distance / (57 if team == "LV" else 66))
        for y in range(32):
            shade = 1 - STYLE["silver_falloff"] * y / 31 if team == "LV" else 1
            rgb = tuple(round(c * (1 - t) * shade + b * t)
                        for c, b in zip(primary, FRAME_COLOR[:3]))
            if team in ('LV', 'HOU'):
                amount = STYLE['silver_reflection' if team == 'LV' else 'red_reflection']
                gloss = min(1., amount * (.42*exp(-y/1.5) + .2*exp(-(31-y))))
                tint = (248,252,247) if team == 'LV' else (254,58,88)
                rgb = tuple(round(a*(1-gloss)+b*gloss) for a,b in zip(rgb,tint))
            im.putpixel((x, y), rgb + (255,))
    if logo is not None:
        bounds = logo.getchannel("A").getbbox()
        if bounds is None:
            raise ValueError("retail team logo is empty")
        width = 48 if team == "HOU" else 43
        height = 31
        prefix = "lv" if team == "LV" else "hou" if team == "HOU" else None
        if prefix:
            width, height = STYLE[prefix+"_width"], STYLE[prefix+"_height"]
        logo = logo.crop(bounds).resize((width, height), Image.Resampling.LANCZOS)
        x = 14 if side == "away" else 68 if team == "HOU" else 71
        dx, dy = (STYLE[prefix+"_dx"], STYLE[prefix+"_dy"]) if prefix else (0,0)
        im.alpha_composite(logo, (x+dx, dy))
        # RAIDERS already exists in the actual shield. Every other team gets
        # authored small caps in its outer panel, above the logo body.
        if team != "LV" and (team != "HOU" or STYLE["wordmark_hou"]):
            mark = wordmark(NICKNAMES[team])
            if STYLE["wordmark_weight"]:
                from PIL import ImageFilter
                mark.putalpha(mark.getchannel("A").filter(ImageFilter.MaxFilter(3) if STYLE["wordmark_weight"] > 0 else ImageFilter.MinFilter(3)))
            mark = mark.resize((min(43, mark.width), 4), Image.Resampling.LANCZOS)
            im.alpha_composite(mark, (x + (43 - mark.width) // 2, 0))
    for n, x in enumerate((91, 101, 111)):
        dx = x if side == "away" else 127 - x - 6
        d.polygon(((dx + 1, 27), (dx + 6, 27), (dx + 5, 29), (dx, 29)),
                  fill=(248, 250, 243, 255) if n < timeouts else (66, 66, 65, 255))
    return im
