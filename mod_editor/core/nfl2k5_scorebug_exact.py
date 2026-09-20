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
    # Static rim mask is independent of the photographed silver/red tile.
    # It is generated here, not read from the explicit-folder v10 PNG layers.
    d.rectangle((24, 0, 47, 23), fill=(0, 0, 0, 0))
    d.rounded_rectangle((24, 0, 47, 23), 3, outline=(255, 255, 255, 255))
    d.line((27, 1, 44, 1), fill=(166, 166, 166, 255))
    d.line((27, 22, 44, 22), fill=(166, 166, 166, 255))
    d.line((27, 23, 44, 23), fill=(23, 23, 23, 255))
    # Neutral backing and decorative timeout marks never inherit team tint.
    d.rectangle((48, 0, 63, 23), fill=FRAME_COLOR)
    d.line((48, 0, 63, 0), fill=(74, 75, 73, 255))
    d.line((48, 23, 63, 23), fill=(74, 75, 73, 255))
    d.rectangle((12, 61, 37, 63), fill=(0, 0, 0, 0))
    for x in (12, 22, 32):
        d.rectangle((x, 61, x+5, 63), fill=(248, 250, 243, 255))
    return im


def mesh(retail, *, runtime=False, revision=2):
    from . import nfl2k5_scorebug_ingame as r
    if runtime:
        return mesh_mnf(retail)
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
        if not runtime:
            # Existing alternate frames become the two independent rims.
            # Material 9/groups is home; material 7/groups2 is away.
            left, right = ((PANELS["home"][0], c) if material_groups is groups
                           else (a, PANELS["away"][2]))
            xs = (left, left + 3, right - 3, right)
        for iy in range(3):
            for ix in range(3):
                uvx, uvy = ((0, 3, 21, 24) if runtime else (24, 27, 45, 48)), (24, 21, 3, 0)
                quad(material_groups[iy * 3 + ix], (xs[ix], ys[iy], xs[ix + 1], ys[iy + 1]),
                     (uvx[ix], uvy[iy + 1], uvx[ix + 1], uvy[iy]))
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
    if not runtime:
        # The unused second corner mark has four disjoint triangles. Two
        # make each side's neutral decorative marks. The clock's unused final
        # quad holds the neutral backing. No material,
        # vertex, command, string, or decoded-size allocation is added.
        def mark_quad(vertices, box, tile, z):
            x0, y0, x1, y1 = box
            u0, v0, u1, v1 = tile
            for vertex, (x, y) in zip(vertices, ((0, 0), (1, 0), (0, 1),
                                                (0, 1), (1, 0), (1, 1))):
                m.pos[vertex] = [x0 + (x1-x0)*x, y0 + (y1-y0)*y, z]
                m.uv_edit[vertex] = ((u0 + (u1-u0)*x)/32-1,
                                     (v1 + (v0-v1)*y)/32-1)
        quad(range(60, 64), FRAME, (48.5, 0, 63.5, 24), z=1)
        for vertices, source, shift in ((range(274, 280), (716,1032,796,1039), -24),
                                         (range(280, 286), (1120,1032,1199,1039), 25.5)):
            box = list(scene_box(source))
            box[0] += shift; box[2] += shift
            mark_quad(vertices, box, (12,61,38,64), -2)
        for material in (0x540, 0x640):
            struct.pack_into("<I", m.buf, material+0x18, 0xffd1d2d3)
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
    from PIL import Image
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
    return _panel_timeouts(im, side, timeouts)


def _panel_timeouts(im, side, timeouts):
    """Paint only the three opaque timeout dashes on a validated panel."""
    from PIL import ImageDraw
    d = ImageDraw.Draw(im)
    for n, x in enumerate((91, 101, 111)):
        dx = x if side == "away" else 127 - x - 6
        d.polygon(((dx + 1, 27), (dx + 6, 27), (dx + 5, 29), (dx, 29)),
                  fill=(248, 250, 243, 255) if n < timeouts else (66, 66, 65, 255))
    return im


# ---------------------------------------------------------------------------
# 2026 Monday Night Football layout for the runtime owner (beta 70).
# Measured from the ESPN Chiefs at Broncos Week 1 broadcast capture (1920x1080)
# and mapped to the 640x448 HUD exactly like the static v3 bar above.
# ---------------------------------------------------------------------------
MNF_VERSION = "espn-mnf-2026-v4"
# Broadcast pixel rectangles (x0, y0, x1, y1) on the 1920x1080 frame.
MNF_SOURCE = {
    "bar": (437, 942, 1478, 1052),
    "away_wing": (437, 942, 650, 1052), "home_wing": (1265, 942, 1478, 1052),
    "plate": (837, 947, 1083, 983), "strip": (839, 999, 1082, 1040),
    # Team marks fill the measured wing height at their original source aspect.
    "away_logo": (453, 943, 653, 1050), "home_logo": (1268, 943, 1468, 1050),
}
MNF_BAR = scene_box(MNF_SOURCE["bar"])
MNF_PANELS = {"away": scene_box(MNF_SOURCE["away_wing"]), "home": scene_box(MNF_SOURCE["home_wing"])}
MNF_PLATE = scene_box(MNF_SOURCE["plate"])
MNF_LOGOS = {"away": scene_box(MNF_SOURCE["away_logo"]), "home": scene_box(MNF_SOURCE["home_logo"])}
# One orientation-independent 64x64 logo per team, fitted to a 200x107 source box.
MNF_WING_LOGO_ROWS, MNF_WING_RAMP_ROWS = (0, 64), (0, 0)
MNF_WING_LAYOUT = {"away": {"logo": (242,243,244,245)}, "home": {"logo": (85,87,90,91)}}
MNF_STRIP = scene_box(MNF_SOURCE["strip"])
# The 2026 layout's regions in the retail comparison's vocabulary (frame, wings, plate, strip).
MNF_COMPARE_REGIONS = {"frame_rim": MNF_SOURCE["bar"], "left_panel": MNF_SOURCE["away_wing"],
                       "centre_pill": MNF_SOURCE["plate"], "clock_strip": MNF_SOURCE["strip"],
                       "right_panel": MNF_SOURCE["home_wing"]}
MNF_V4_COMPARE_REGIONS = {**MNF_COMPARE_REGIONS,
    "housing": (837,983,1083,1045), "white_capsule": (839,999,1019,1039),
    "play_clock_cell": (1019,999,1082,1040), "pointer": (951,942,965,947)}
# Text anchors: x is the alignment point (scores/quarter/play clock centred,
# the game clock right-aligned like retail), y the text bottom in scene units.
_SX = lambda px: px / 3 - 320
_SY = lambda py: 424 - (16 + py * 448 / 1080)
# Text origins measured with the native draw projection (tools/nfl2k5_scorebug_projection):
# a record's screen origin is 424 - anchor_y - K, with K = 0 for the rotating score
# records, 15 for the element and clock records and 27 for the two team-name records
# (their transforms carry a retail offset), and the glyph top sits glyph_y0 rows below
# the origin (FONT4 4, FONT8 7). Targets are the broadcast text tops on the 640x448 HUD.
def _ORIGIN(px_top, glyph_y0, k):
    return 424 - (16 + px_top * 448 / 1080 - glyph_y0) - k
MNF_ANCHORS = {
    "away_city": (_SX(756), _ORIGIN(1032, 13, 27), -64), "home_city": (_SX(1160), _ORIGIN(1032, 13, 27), -64),   # private light-grey tick glyphs
    "away_score": (_SX(756), _ORIGIN(965, 0, 0), -59), "home_score": (_SX(1160), _ORIGIN(965, 0, 0), -59),
    "quarter": (_SX(871), _ORIGIN(1001, 0, 15), -4), "clock_a": (_SX(960), _ORIGIN(1006, 0, 15), -4), "clock_b": (_SX(960), _ORIGIN(1006, 0, 15), -4),
    "drop_clock": (_SX(1050.5), _ORIGIN(1007, 0, 15), -4), "drop_down": (_SX(960), _ORIGIN(955, 0, 15), -4),
    "drop_yellow": (0, _ORIGIN(955, 4, 15), -8), "drop_red": (0, _ORIGIN(955, 4, 15), -8),
    "drop_hangtime": (0, _ORIGIN(955, 4, 15), -8), "drop_ball_on": (0, _ORIGIN(955, 4, 15), -8),
}
MNF_REGIONS = {"frame": (0, 0, 256, 110), "ramp": (0, 112, 213, 222),
               "plate": (0, 224, 246, 260), "housing": (0, 262, 246, 324),
               "strip": (0, 326, 243, 367), "cell": (0, 370, 63, 411),
               "solid": (2, 414, 3, 415), "body": (6, 414, 7, 415)}
MNF_COLORS = {"body": (37,37,37), "body_hi": (37,37,37), "lip": (60,64,70),
              "plate": (255,255,255), "capsule": (248,248,250), "capsule_ink": (30,30,30),
              "separator": (196,200,208)}
# Possession plate colours per team (ESPN's team colour, lifted so it reads on
# the charcoal bar). Indexed by the retail two-digit asset code at runtime.
ESPN_PLATE = {
    "ARI": "#97233F", "ATL": "#A71930", "BAL": "#241773", "BUF": "#00338D", "CAR": "#0085CA", "CHI": "#0B162A",
    "CIN": "#FB4F14", "CLE": "#FF3C00", "DAL": "#003594", "DEN": "#0C2340", "DET": "#0076B6", "GB": "#203731",
    "HOU": "#03202F", "IND": "#002C5F", "JAX": "#006778", "KC": "#E31837", "LAC": "#0080C6", "LAR": "#003594",
    "LV": "#000000", "MIA": "#008E97", "MIN": "#4F2683", "NE": "#002244", "NO": "#101820", "NYG": "#0B2265",
    "NYJ": "#125740", "PHI": "#004C54", "PIT": "#101820", "SEA": "#002244", "SF": "#AA0000", "TB": "#D50A0A",
    "TEN": "#0C2340", "WAS": "#5A1414",
}


# Explicit secondary choices for near-black primaries. Others retain full primary.
ESPN_PLATE_SECONDARY = {"CHI": "#C83803", "DEN": "#FB4F14", "HOU": "#C8102E",
                        "LV": "#A5ACAF", "NE": "#C60C30", "NO": "#D3BC8D",
                        "PIT": "#FFB612", "SEA": "#69BE28", "TEN": "#4B92DB"}
ESPN_WING_LIT = {"DEN": (55,93,163), "KC": (208,10,67)}
# The bar shows team colours "as lit": on air a dark primary such as the Cowboys'
# #003594 is lifted, not drawn raw (raw under the plate mask it read as black in
# game). The floors are the measured lit values: the KC plate top (178,12,60)
# under the 0.83 mask top is a tint of HSL lightness 0.37; the DEN and KC lit
# wings (55,93,163) and (208,10,67) are lightness 0.43. Hue and saturation are
# kept. The plate cell's mean luminance under the label rows is 0.788, and the
# white label must keep 4.5:1 contrast on the lit plate, so bright secondaries
# (gold, silver, action green) are lowered until they do.
PLATE_LIGHTNESS_FLOOR = 0.36
WING_LIGHTNESS_FLOOR = 0.43
PLATE_MASK_LABEL = 0.788
PLATE_LABEL_CONTRAST = 4.5
PLATE_LABEL_MARGIN = 0.3  # palette quantisation and the raster cost up to about 0.15 on the rendered plate
PLATE_LABEL_RGB = (255, 255, 255)


def hex_rgb(colour):
    return tuple(int(colour[i:i + 2], 16) for i in (1, 3, 5))


def relative_luminance(rgb):
    """WCAG relative luminance of an sRGB colour (0..255 channels)."""
    def channel(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a, b):
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def with_lightness(rgb, lightness):
    import colorsys
    h, _, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    return tuple(min(255, max(0, round(c * 255))) for c in colorsys.hls_to_rgb(h, lightness, s))


NEUTRAL_BELOW = 40  # black primaries (LV, NO, PIT) light to grey, not to their faint blue cast


def lit_rgb(rgb, floor):
    """Raise HSL lightness to ``floor`` keeping hue and saturation; brighter colours are unchanged."""
    import colorsys
    _, lightness, _ = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    if lightness >= floor:
        return tuple(rgb)
    if max(rgb) < NEUTRAL_BELOW:
        grey = round(floor * 255)
        return (grey, grey, grey)
    return with_lightness(rgb, floor)


def lit_plate_rgb(rgb):
    """The plate colour drawn under the label: the tint through the cell mask."""
    return tuple(min(255, round(c * PLATE_MASK_LABEL)) for c in rgb)


def plate_rgb(team):
    """Lit team colour for the possession plate: the explicit secondary for near-black
    teams, otherwise the primary lifted to the plate floor; then lowered in lightness
    until the white label keeps PLATE_LABEL_CONTRAST on the masked plate."""
    import colorsys
    colour = lit_rgb(hex_rgb(ESPN_PLATE_SECONDARY.get(team, ESPN_PLATE[team])), PLATE_LIGHTNESS_FLOOR)
    _, lightness, _ = colorsys.rgb_to_hls(*(c / 255 for c in colour))
    while contrast_ratio(PLATE_LABEL_RGB, lit_plate_rgb(colour)) < PLATE_LABEL_CONTRAST + PLATE_LABEL_MARGIN and lightness > 0.05:
        lightness = round(lightness - 0.01, 4)
        colour = with_lightness(colour, lightness)
    return colour


def plate_argb(team):
    r, g, b = plate_rgb(team)
    return 0xFF000000 | (r << 16) | (g << 8) | b


def wing_rgb(team):
    """Lit team primary for the wing ramp (the measured DEN and KC values stay explicit)."""
    return tuple(ESPN_WING_LIT[team]) if team in ESPN_WING_LIT else lit_rgb(hex_rgb(ESPN_PLATE[team]), WING_LIGHTNESS_FLOOR)


def plate_table():
    """40 ARGB words indexed by asset code (two digits, 00..39); unknown codes stay neutral."""
    from . import nfl2k5_scorebug_ingame as r
    table = [0xFF3A3F48] * 40
    for team, record in r.TEAM_LOGOS.items():
        table[int(record["asset_code"])] = plate_argb(team)
    return table


def wing_table():
    from . import nfl2k5_scorebug_ingame as r
    table = [0xff4a4e58] * 40
    for team, record in r.TEAM_LOGOS.items():
        rgb = wing_rgb(team)
        table[int(record["asset_code"])] = 0xff000000 | rgb[0]<<16 | rgb[1]<<8 | rgb[2]
    return table


def atlas_mnf():
    """Paint at twice source resolution; downsample into the appended 256x512 P8 atlas.

    A single frame quad has no internal band. A white alpha ramp overlays its
    charcoal with the owner tint. All rounded silhouettes are painted masks.
    """
    from PIL import Image, ImageDraw
    from .runtime_dependencies import require_numpy
    np = require_numpy("Scorebug texture conversion")
    im = Image.new("RGBA", (256,512))
    def tile(name, size, radius, color, *, end=None):
        w,h=size; out=Image.new("RGBA",(w*2,h*2)); d=ImageDraw.Draw(out)
        d.rounded_rectangle((0,0,w*2-1,h*2-1),radius*2,fill=color)
        if end=="left": d.rectangle((w,h*0,w*2-1,h*2-1),fill=color)
        if end=="right": d.rectangle((0,0,w-1,h*2-1),fill=color)
        return out
    def put(name,out):
        a,b,c,d=MNF_REGIONS[name]
        im.paste(out.resize((c-a,d-b),Image.Resampling.LANCZOS),(a,b))
    body=tile("frame",(1041,110),8,(37,37,37,255))
    d=ImageDraw.Draw(body)
    d.line((16,1,2065,1),fill=(60,64,70,255),width=4)
    d.line((16,217,2065,217),fill=(13,20,28,255),width=4)
    put("frame",body)
    # Alpha, rather than black luminance, mixes the team tint into the flat body.
    ramp=tile("ramp",(213,110),8,(255,255,255,255),end="left")
    pix=np.asarray(ramp).copy();x=np.arange(426)/425;fade=1-x*x*(3-2*x)
    pix[:,:,3]=(pix[:,:,3]*fade[None,:]).round().astype('uint8')
    put("ramp",Image.fromarray(pix))
    put("plate",tile("plate",(246,36),6,(255,255,255,255)))
    put("housing",tile("housing",(246,62),20,(24,24,26,255)))
    pill=tile("strip",(243,41),20,(248,248,250,255))
    d=ImageDraw.Draw(pill);mask=tile("cell",(63,41),20,(215,0,51,255),end="right")
    pill.paste(mask,(360,0),mask);put("strip",pill)
    put("cell",tile("cell",(63,41),20,(255,255,255,255),end="right"))
    d=ImageDraw.Draw(im);d.rectangle((0,413,4,417),fill=(255,255,255,255));d.rectangle((5,413,9,417),fill=(37,37,37,255))
    return im


def mesh_mnf(retail):
    """Painted masks and plain quads inside the unchanged 4,800-byte scene span."""
    from . import nfl2k5_scorebug_ingame as r
    m = r.layout.Mesh(retail)
    # Retail's UV affine includes a small scale/bias correction for its 64px
    # atlas. The painted atlas and logo cells use exact normalized coordinates.
    struct.pack_into("<4f",m.buf,r.layout.SHAPE+0x30,.5,.5,.5,.5)
    for v in range(r.layout.VCOUNT):
        m.pos[v] = [0, 0, -3]
        m.uv_edit[v] = (-1 + 1.5 / 32, -1 + 62.5 / 32)
        struct.pack_into("<I", m.buf, r.layout.S1 + v * 10, 0xffffffff)
        struct.pack_into("<h", m.buf, r.layout.S1 + v * 10 + 8, 0)
    def draw(k, quads):
        """Replace only inline indices inside the fixed retail push-buffer span."""
        indices=[]
        for ids,source,tile,z,logo in quads:
            a,b,c,d=scene_box(source);ss,t,u,w=tile
            for v,(x,y) in zip(ids,((0,1),(1,1),(0,0),(1,0))):
                m.pos[v]=[a+(c-a)*x,d-(d-b)*y,z]
                tw,th=(64,64) if logo else (256,512)
                m.uv_edit[v]=((ss+(u-ss)*x)*2/tw-1,(t+(w-t)*y)*2/th-1)
            if indices: indices.extend((indices[-1],ids[0]))
            indices.extend(ids)
        if len(indices)%2: indices.append(indices[-1])
        words=[0x417fc,6,0x40001800|((len(indices)//2)<<18)]
        words += [indices[i]|indices[i+1]<<16 for i in range(0,len(indices),2)]
        words += [0x417fc,0]
        off,capacity=r.layout.SUBMESH_COMMANDS[k]
        if len(words)>capacity: raise ValueError("painted quads exceed retail command span")
        words += [0]*(capacity-len(words))
        struct.pack_into("<"+str(capacity)+"I",m.buf,off,*words)
    def q(ids,source,tile,z=0,logo=False):return (tuple(ids),source,tile,z,logo)
    # The static body draws before translucent masks in the retail material order.
    draw(3,[q(range(48,52),MNF_SOURCE["bar"],MNF_REGIONS["frame"]),
            q(range(52,56),(837,983,1083,1045),MNF_REGIONS["housing"],-2.8),
            q(range(56,60),MNF_SOURCE["strip"],MNF_REGIONS["strip"],-3)])
    for k,ids in ((0,range(0,4)),(1,range(16,20)),(2,range(32,36)),(10,range(274,278))):
        draw(k,[q(ids,MNF_SOURCE["plate"],MNF_REGIONS["body"],-7)])
    draw(4,[q(range(64,68),MNF_SOURCE["plate"],MNF_REGIONS["plate"],-3),
            q(range(76,80),(951,942,965,947),MNF_REGIONS["solid"],-3.1)])
    # A triangle pointer shares the plate tint; collapse its upper edge to centre.
    m.pos[78][0]=m.pos[79][0]=_SX(958)
    for k,side,ids in ((8,"away",(242,243,244,245)),(5,"home",(85,87,90,91))):
        draw(k,[q(ids,MNF_SOURCE[side+"_logo"],(0,0,64,64),-2,True)])
    draw(6,[q(range(96,100),MNF_SOURCE["away_wing"],MNF_REGIONS["ramp"],-1)])
    a,b,c,d=MNF_REGIONS["ramp"]
    draw(7,[q(range(166,170),MNF_SOURCE["home_wing"],(c,b,a,d),-1)])
    draw(9,[q(range(262,266),(1019,999,1082,1040),MNF_REGIONS["cell"],-3.25)])
    name="score_buga\0".encode("utf-16le");m.buf[0x3f8c:0x3f8c+len(name)]=name
    struct.pack_into("<I",m.buf,0x4c0+0x18,0xffd70033)

    for side, parent in (("away", 23), ("home", 26)):
        m.world[parent][:2] = list(MNF_ANCHORS[side + "_score"][:2])
    for name, xyz in MNF_ANCHORS.items():
        i, leaf = r.layout.T[name], r.layout.T[name + "_l"]
        delta = [bb - aa for aa, bb in zip(m.world[i], m.world[leaf])]
        m.world[i] = list(xyz)
        m.world[leaf] = [aa + bb for aa, bb in zip(xyz, delta)]
    return m


def mnf_panel(team, side, fit=None):
    """Shared transparent logo cell, fitted at the final quad's source aspect.

    ``fit`` widens the mark horizontally (``fill_x``) and scales its height (``height``,
    a fraction of the wing height) the way the broadcast draws each mark: ESPN stretches
    the Chiefs arrowhead from 1.53 to 1.89 wide-to-tall and draws the Broncos horse at
    79 percent of the wing height, 1.19 wider than the official mark.
    """
    from pathlib import Path
    from PIL import Image
    if side not in ("home", "away"):
        raise ValueError("invalid scorebug side")
    im = Image.new("RGBA", (64, 64) if team else (32,32), (0, 0, 0, 0))
    if team is not None:
        logos = Path(__file__).resolve().parents[2] / "data" / "nfl2k5_scorebug_mnf" / "logos"
        key = {"WAS": "wsh"}.get(team, team.lower())
        path = logos / f"{key}.png"
        if path.exists():
            logo = Image.open(path).convert("RGBA")
            bounds = logo.getchannel("A").getbbox()
            if bounds:
                logo = logo.crop(bounds)
            l0, l1 = MNF_WING_LOGO_ROWS
            a,b,c,d = MNF_SOURCE["home_logo"]
            fill_x = float((fit or {}).get("fill_x", 1.0))
            height = float((fit or {}).get("height", 1.0))
            zoom = float((fit or {}).get("zoom", 1.0))
            shift_x = float((fit or {}).get("shift_x", 0.0))
            shift_y = float((fit or {}).get("shift_y", 0.0))
            if not (0.5 <= fill_x <= 2.0 and 0.25 <= height <= 1.0
                    and 0.5 <= zoom <= 2.0 and -0.5 <= shift_x <= 0.5
                    and -0.5 <= shift_y <= 0.5):
                raise ValueError("invalid logo fit")
            scale = min((c-a)/logo.width,(d-b)*height/logo.height)
            src_w = min(c-a, logo.width*scale*fill_x)
            w = max(1,round(src_w*64/(c-a)*zoom))
            h = max(1,round(logo.height*scale*(l1-l0)/(d-b)*zoom))
            from .nfl2k5_scorebug_assets import resample_logo, alpha_bleed
            logo = resample_logo(logo, (w, h))
            # Clip the enlarged mark at the wing edge, as the live package
            # does for tall shields and the Texans bull. Defaults preserve
            # legacy callers and the 64 by 64 runtime texture contract.
            im.paste(logo, ((64-w)//2+round(shift_x*64),
                           l0+(l1-l0-h)//2+round(shift_y*64)))
            im = alpha_bleed(im)
    return im
