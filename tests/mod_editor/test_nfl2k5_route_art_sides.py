"""Route Segment (0x12) art: inside / outside comes from the receiver's side of the ball.

Beta 73 report (Discord, 2026-09-19): in Create a Play, Gun Trips Right, the TE left of the
ball ran "Post (5 yd)" but the editor drew it breaking toward the left sideline, and WR3 on
the right ran "Corner (4 yd)" but was drawn breaking toward the middle.  The encoded play was
right; the preview drew the side-relative kinds for the wrong side.

The retail draw handler 0x182110 (draw slot of opcode 0x12 in the table at 0x521078) asks
0x17FF40 which side of the ball the receiver lined up on and breaks every kind except 0 and 9
inside or outside of it; the runtime route executor 0x225730 turns the same ways.  The offline
tests run everywhere; the retail tests read the private XBE and playbooks when present.
"""
from __future__ import annotations

import hashlib
import math
import os
import pathlib
import struct
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mod_editor.core import nfl2k5_play_codec as codec
from mod_editor.core import nfl2k5_play_library as lib

YD = codec.YD_CM
EXTRACT = pathlib.Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)")
RETAIL_XBE = EXTRACT / "default.xbe"

INSIDE, OUTSIDE, STRAIGHT = "inside", "outside", "straight"
# What the retail art does with each kind for a receiver lined up off the ball.
EXPECTED = {0: STRAIGHT, 1: INSIDE, 2: INSIDE, 3: INSIDE, 4: INSIDE, 5: OUTSIDE, 6: OUTSIDE,
            7: OUTSIDE, 8: INSIDE, 10: INSIDE, 11: INSIDE}


def nodes(*segments) -> list[codec.Node]:
    return [codec.Node(op, 0, list(vals)) for op, vals in [lib.start(3), *segments]]


def lateral(art: list[codec.ArtSegment]) -> float:
    """Sideways travel of the last drawn piece (cm, + = offense's right)."""
    (x0, _y0), (x1, _y1) = art[-1].points[0], art[-1].points[-1]
    return x1 - x0


def direction(dx: float, x_cm: float) -> str:
    if abs(dx) < 1e-6:
        return STRAIGHT
    return INSIDE if (dx < 0) == (x_cm > 0) else OUTSIDE


class RouteKindSideTests(unittest.TestCase):
    """Every kind, drawn for a receiver left and right of the ball."""

    def test_every_route_kind_breaks_to_the_correct_side_for_left_and_right_receivers(self):
        for kind, want in EXPECTED.items():
            for x in (10 * YD, -10 * YD, 3 * YD, -3 * YD):
                with self.subTest(kind=kind, x_yd=x / YD):
                    art = codec.play_art(nodes(lib.seg(kind, 10)), (x, 0.0))
                    self.assertTrue(art, "every route kind draws something")
                    self.assertEqual(direction(lateral(art), x), want,
                                     f"kind {kind} ({codec.ROUTE_SEGMENT_TYPES[kind]}) at x={x / YD:+.0f} yd")

    def test_left_receiver_art_is_the_mirror_of_the_right_receiver_art(self):
        for kind in EXPECTED:
            right = codec.play_art(nodes(lib.seg(0, 4), lib.seg(kind, 10)), (12 * YD, 0.0))
            left = codec.play_art(nodes(lib.seg(0, 4), lib.seg(kind, 10)), (-12 * YD, 0.0))
            with self.subTest(kind=kind):
                self.assertEqual(len(right), len(left))
                for a, b in zip(right, left):
                    for (xa, ya), (xb, yb) in zip(a.points, b.points):
                        self.assertAlmostEqual(xa, -xb, places=3)
                        self.assertAlmostEqual(ya, yb, places=3)

    def test_the_side_argument_does_not_override_the_alignment(self):
        # The wizard's rules and option previews call play_art without a side; the game
        # still resolves routes from where the receiver lined up.
        for side in (1, -1):
            art = codec.play_art(nodes(lib.seg(0, 5), lib.seg(2, 10)), (-5 * YD, 0.0), side=side)
            self.assertGreater(lateral(art), 0, "a left-side post breaks toward the middle")

    def test_pass_block_side_follows_the_distance_sign_not_the_alignment(self):
        for x in (8 * YD, -8 * YD, 0.0):
            self.assertGreater(lateral(codec.play_art(nodes(lib.seg(9, 21)), (x, 0.0))), 0)
            self.assertLess(lateral(codec.play_art(nodes(lib.seg(9, -21)), (x, 0.0))), 0)

    def test_breaks_are_one_leg_of_the_encoded_distance(self):
        # 0x181A80 rotates (0, distance) by the break angle: no hidden stem.
        for kind, degrees in ((1, 30), (2, 45), (3, 60), (6, 45)):
            dx, dy = codec.route_segment_offset(kind, 10 * YD, 1)
            self.assertAlmostEqual(math.hypot(dx, dy), 10 * YD, places=3)
            self.assertAlmostEqual(math.degrees(math.atan2(abs(dx), dy)), degrees, places=3)
        art = codec.play_art(nodes(lib.seg(0, 5), lib.seg(2, 10)), (-5 * YD, 0.0))
        self.assertEqual(len(art), 2)
        self.assertEqual(art[0].points, [(-5 * YD, 0.0), (-5 * YD, 5 * YD)], "the stem is the seg-0 distance")
        self.assertAlmostEqual(art[1].points[1][1] - art[1].points[0][1], 10 * YD * math.cos(math.radians(45)), places=3)

    def test_comebacks_and_block_marks_use_the_retail_offsets(self):
        self.assertEqual(codec.route_segment_offset(7, 2 * YD, 1), (60.96, -121.92))
        self.assertEqual(codec.route_segment_offset(11, 2 * YD, 1), (-60.96, -121.92))
        self.assertEqual(codec.route_segment_offset(8, 4 * YD, -1), (121.92, 0.0))
        self.assertEqual(codec.route_segment_offset(10, 1 * YD, 1), (-121.92, 1 * YD))

    def test_side_deadband_is_half_a_foot(self):
        self.assertEqual(codec.route_side(16.0), 1)
        self.assertEqual(codec.route_side(0.0), 1)
        self.assertEqual(codec.route_side(-15.24), 1, "within half a foot: the call-screen flag, drawn right")
        self.assertEqual(codec.route_side(-15.3), -1)
        self.assertEqual(codec.ROUTE_INSIDE_KINDS | codec.ROUTE_OUTSIDE_KINDS, frozenset(EXPECTED) - {0})

    def test_library_routes_break_the_way_their_names_say(self):
        want = {"Post": INSIDE, "Corner": OUTSIDE, "Out": OUTSIDE, "In / Dig": INSIDE, "Slant": INSIDE,
                "Curl": INSIDE, "Comeback": OUTSIDE, "Flat": OUTSIDE, "Drag": INSIDE}
        for name, side_word in want.items():
            for x in (9 * YD, -9 * YD):
                with self.subTest(route=name, x_yd=x / YD):
                    chain = lib.route_chain(name, None, 1 if x >= 0 else -1)
                    art = codec.play_art([codec.Node(op, 0, list(v)) for op, v in chain], (x, 0.0))
                    self.assertEqual(direction(lateral(art), x), side_word)

    def test_drawn_routes_keep_the_stem_and_pick_the_retail_comeback_kinds(self):
        def line(*pts):
            return [(x * YD, z * YD) for x, z in pts]
        chain, words = lib.quantize_drawn_route(line((12, 0), (12, 10), (6, 16)), 1)
        self.assertEqual([vals[0] for _op, vals in chain[1:]], [0, 2])
        self.assertAlmostEqual(chain[1][1][2], 10 * YD)
        self.assertIn("post", words)
        chain, _ = lib.quantize_drawn_route(line((-12, 0), (-12, 8), (-18, 14)), -1)
        self.assertEqual([vals[0] for _op, vals in chain[1:]], [0, 6], "a left receiver breaking left is a corner")
        chain, words = lib.quantize_drawn_route(line((12, 0), (12, 12), (10, 10)), 1)
        self.assertEqual(chain[-1][1][0], 11, "back toward the middle is kind 11")
        chain, words = lib.quantize_drawn_route(line((12, 0), (12, 12), (14, 10)), 1)
        self.assertEqual(chain[-1][1][0], 7, "back toward the sideline is kind 7")
        self.assertIn("sideline", words)


def reporter_play() -> tuple[list[tuple[int, int]], list[str], list[lib.Chain]]:
    """Gun Trips Right: TE Post 5, WR2 Go, WR3 Corner 4, WR In / Dig (the Discord screenshot)."""
    _blurb, players = lib.FORMATION_TEMPLATES["Gun Trips Right"]
    positions = [(int(round(p.x * YD)), int(round(p.z * YD))) for p in players]
    kinds = [p.kind for p in players]
    labels = [codec.position_label(c) for c in lib.ranked_codes(kinds, [p.x for p in players])]
    slot = {label: s for s, label in enumerate(labels)}
    spec = lib.PlaySpec("test play1", "pass", positions, kinds, {
        slot["TE"]: lib.PlayerAssignment("route", "Post", 5),
        slot["WR2"]: lib.PlayerAssignment("route", "Go"),
        slot["WR3"]: lib.PlayerAssignment("route", "Corner", 4),
        slot["WR"]: lib.PlayerAssignment("route", "In / Dig"),
    })
    return positions, labels, lib.build_chains(spec)


def wizard_art(positions, chains, slot) -> list[codec.ArtSegment]:
    # The call AssignPage._refresh makes for every player.
    x0, z0 = positions[slot]
    return codec.play_art([codec.Node(op, 0, list(v)) for op, v in chains[slot]], (float(x0), float(z0)),
                          side=1 if x0 >= 0 else -1)


class ReporterPlayTests(unittest.TestCase):
    def setUp(self):
        self.positions, self.labels, self.chains = reporter_play()
        self.slot = {label: s for s, label in enumerate(self.labels)}

    def test_alignment_matches_the_screenshot(self):
        x = {label: self.positions[s][0] / YD for label, s in self.slot.items()}
        self.assertLess(x["TE"], 0)
        self.assertLess(0, x["WR"])
        self.assertLess(x["WR"], x["WR2"])
        self.assertLess(x["WR2"], x["WR3"])

    def test_post_breaks_inside_and_corner_breaks_outside(self):
        te = wizard_art(self.positions, self.chains, self.slot["TE"])
        te_x = self.positions[self.slot["TE"]][0]
        self.assertEqual([p[0] for p in te[0].points], [te_x, te_x], "5-yard stem straight up")
        self.assertAlmostEqual(te[0].points[1][1] - te[0].points[0][1], 5 * YD)
        dx, dy = (te[-1].points[1][0] - te[-1].points[0][0], te[-1].points[1][1] - te[-1].points[0][1])
        self.assertGreater(dx, 0, "TE post breaks toward the middle (up and to the right)")
        self.assertAlmostEqual(dx, dy, places=3)
        wr3 = wizard_art(self.positions, self.chains, self.slot["WR3"])
        self.assertAlmostEqual(wr3[0].points[1][1] - wr3[0].points[0][1], 4 * YD)
        dx, dy = (wr3[-1].points[1][0] - wr3[-1].points[0][0], wr3[-1].points[1][1] - wr3[-1].points[0][1])
        self.assertGreater(dx, 0, "WR3 corner breaks toward the right sideline (up and to the right)")
        self.assertAlmostEqual(dx, dy, places=3)

    def test_go_stays_straight_and_the_dig_crosses_inside(self):
        go = wizard_art(self.positions, self.chains, self.slot["WR2"])
        self.assertEqual(len(go), 1)
        self.assertEqual(lateral(go), 0)
        dig = wizard_art(self.positions, self.chains, self.slot["WR"])
        self.assertLess(lateral(dig), 0, "WR (right of the ball) digs toward the middle")

    def test_editor_scene_draws_the_same_directions(self):
        try:
            from PyQt5.QtWidgets import QApplication, QGraphicsLineItem
        except ImportError:
            self.skipTest("PyQt5 missing; offscreen Qt required")
        app = QApplication.instance() or QApplication([])
        from PyQt5.QtGui import QColor
        from mod_editor.gui.play_designer_qt import FieldScene
        for label, rightward in (("TE", True), ("WR3", True), ("WR", False)):
            scene = FieldScene()
            scene.draw_art(wizard_art(self.positions, self.chains, self.slot[label]), QColor("#ffffff"))
            lines = [item.line() for item in scene.art_items if isinstance(item, QGraphicsLineItem)]
            last = lines[-1]
            with self.subTest(player=label):
                self.assertEqual(last.x2() > last.x1(), rightward, "screen right is the offense's right")
                if label != "WR":
                    self.assertLess(last.y2(), last.y1(), "the break goes upfield (screen up)")
        del app


def _retail_xbe():
    if not RETAIL_XBE.is_file():
        return None
    raw = RETAIL_XBE.read_bytes()
    from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage
    if hashlib.sha256(raw).hexdigest() != RETAIL_SHA256:
        return None
    return XbeImage(raw)


@unittest.skipUnless(RETAIL_XBE.is_file(), "private retail XBE missing")
class RetailDrawHandlerTests(unittest.TestCase):
    """The preview's inside / outside table read back from the retail executable."""

    DRAW = 0x182110
    CASES = (0x182168, 0x1821A2, 0x1821EF, 0x18223C, 0x182289, 0x1822BF, 0x1822F5, 0x1823DB,
             0x182403, 0x182384, 0x182342, 0x18217A)
    SIDE_TEST = 0x17FF40
    # kind -> (call to the side test, right-of-ball branch, left-of-ball branch, operand form)
    BRANCHES = {
        1: (0x1821B6, (0x1821C7, "6ae2"), (0x1821DB, "6a1e"), "angle"),
        2: (0x182203, (0x182214, "6ad3"), (0x182228, "6a2d"), "angle"),
        3: (0x182250, (0x182261, "6ac4"), (0x182275, "6a3c"), "angle"),
        6: (0x182309, (0x18231A, "6a2d"), (0x18232E, "6ad3"), "angle"),
        4: (0x18228A, (0x182298, "f7db"), (0x1822AE, "db45f8"), "negate"),
        5: (0x1822C0, (0x1822CE, "db45f8"), (0x1822DF, "f7db"), "negate"),
        7: (0x1823DC, (0x1823F0, "680ad77342"), (0x18218F, "680ad773c2"), "float"),
        11: (0x18217B, (0x18218F, "680ad773c2"), (0x1823F0, "680ad77342"), "float"),
        8: (0x182404, (0x18240D, "680ad7f3c2"), (0x182414, "680ad7f342"), "float"),
        10: (0x182359, (0x182362, "680ad773c2"), (0x182373, "680ad77342"), "float"),
    }

    @classmethod
    def setUpClass(cls):
        cls.xbe = _retail_xbe()
        if cls.xbe is None:
            raise unittest.SkipTest("default.xbe is not the pinned retail executable")

    def _sine(self, degrees: int) -> float:
        # 0x17FD40: piecewise-linear sine table at 0x4E53E8, 0x10000 units per turn.
        units = int(degrees * struct.unpack("<f", self.xbe.read(0x4E6C40, 4))[0]) & 0xFFFF
        base, slope = struct.unpack("<ff", self.xbe.read(0x4E53E8 + (units >> 8) * 8, 8))
        return slope * units + base

    def _lateral_sign(self, form: str, code: str) -> int:
        raw = bytes.fromhex(code)
        if form == "angle":            # push imm8 angle -> 0x181A80 turns (0, d) to x = sin(angle) * d
            return 1 if self._sine(struct.unpack("<b", raw[1:2])[0]) > 0 else -1
        if form == "negate":           # neg ebx = x = -distance, fild [ebp-8] = x = +distance
            return -1 if raw == bytes.fromhex("f7db") else 1
        return 1 if struct.unpack("<f", raw[1:5])[0] > 0 else -1

    def test_opcode_table_routes_0x12_to_the_draw_handler(self):
        self.assertEqual(struct.unpack("<I", self.xbe.read(0x521078 + 0x12 * 0x14 + 0x0C, 4))[0], self.DRAW)
        self.assertEqual(struct.unpack("<12I", self.xbe.read(0x182448, 48)), self.CASES)

    def test_side_test_reads_the_alignment_with_a_half_foot_deadband(self):
        self.assertEqual(hashlib.sha256(self.xbe.read(self.SIDE_TEST, 0x94)).hexdigest(),
                         "27100dac6f274bc0331305bfb176c06f683254c1f2d3e3481361920459f8cee4")
        self.assertAlmostEqual(struct.unpack("<f", self.xbe.read(0x50A050, 4))[0], codec.ROUTE_SIDE_DEADBAND_CM, places=4)
        self.assertEqual(self.xbe.read(0x182587, 7).hex(), "0f290500fcbd00", "alignment stored once per chain")

    def test_every_side_relative_kind_matches_the_retail_branches(self):
        for kind, (call, right, left, form) in self.BRANCHES.items():
            with self.subTest(kind=kind):
                raw = self.xbe.read(call, 5)
                self.assertEqual(raw[0], 0xE8)
                self.assertEqual(call + 5 + struct.unpack("<i", raw[1:])[0], self.SIDE_TEST)
                for address, code in (right, left):
                    self.assertEqual(self.xbe.read(address, len(code) // 2).hex(), code)
                for side, (_address, code) in ((1, right), (-1, left)):
                    dx, _dy = codec.route_segment_offset(kind, 10 * YD, side)
                    self.assertEqual(1 if dx > 0 else -1, self._lateral_sign(form, code),
                                     f"kind {kind}, receiver {'right' if side > 0 else 'left'} of the ball")

    def test_pass_block_branches_on_the_distance_sign(self):
        self.assertEqual(self.xbe.read(0x182384, 4).hex(), "85db7e1a", "test ebx, ebx; jle: the sign of the distance")

    def test_runtime_route_executor_turns_the_same_ways(self):
        table = struct.unpack("<12I", self.xbe.read(0x225DA4, 48))
        self.assertEqual(table[10], table[1], "kind 10 turns like kind 1")

        def turn(kind: int) -> int:
            raw = self.xbe.read(table[kind], 16)
            self.assertEqual(raw[:6].hex() + raw[10:12].hex(), "f7de1bf681e681c6")
            mask, add = struct.unpack("<II", raw[6:10] + raw[12:16])
            return ((mask + add) & 0xFFFF) - (0x10000 if (mask + add) & 0x8000 else 0)

        inside = turn(4)
        self.assertEqual(abs(inside), 0x4000, "lateral in is a quarter turn")
        for kind in (1, 2, 3, 5, 6, 7, 8, 11):
            with self.subTest(kind=kind):
                self.assertEqual(turn(kind) * inside > 0, kind in codec.ROUTE_INSIDE_KINDS)
        self.assertEqual({k: abs(turn(k)) for k in (1, 2, 3, 6, 7, 8, 11)},
                         {1: 0x1555, 2: 0x2000, 3: 0x2AAA, 6: 0x2000, 7: 0x6000, 8: 0x5555, 11: 0x6000})


@unittest.skipUnless((EXTRACT / "vc_53450030" / "0").is_file(), "retail extracted vc_53450030/0 missing")
class RetailPlaybookTests(unittest.TestCase):
    """Stock plays use the same kind on both sides of the ball for the same route."""

    # (book, play, formation, {slot: (x yards, route kinds after the opener)}, what the last kind does)
    CASES = (
        ("PHI", "90 Quick Slants", "Quads", {6: (-9, [0, 1]), 7: (-15, [0, 1]), 8: (15, [0, 1]), 9: (9, [0, 1])}, INSIDE),
        ("ARZ", "50 X/Z Posts", "Triple", {7: (-15, [0, 2]), 8: (15, [0, 2])}, INSIDE),
        ("CAR", "50 Y/TE Corners", "I Jokers", {6: (-5, [0, 6]), 8: (5, [0, 6])}, OUTSIDE),
        ("BUF", "50 Y/TE Comebacks", "I Jokers", {6: (-5, [0, 7]), 8: (5, [0, 7])}, OUTSIDE),
        ("BAL", "90 All Stops", "Empty Open", {6: (-9, [0, 11]), 7: (-15, [0, 11]), 8: (15, [0, 11]),
                                               9: (12, [0, 11]), 10: (9, [0, 11])}, INSIDE),
        ("ARZ", "50 TE/Z Curls", "I Twins", {6: (-5, [0, 8]), 7: (9, [0, 8])}, INSIDE),
    )

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_playbook_inspector as insp
        from nfl2k5_playbook_position_recode import BOOK_ENTRIES, OuterImage
        cls.books = {}
        with OuterImage(EXTRACT) as archive:
            for name in sorted({case[0] for case in cls.CASES}):
                raw = archive.read_entry(BOOK_ENTRIES[name])
                cls.books[name] = (insp.parse_playbook_resource(raw, asset_id=name), raw[0x20:])

    def test_same_route_same_kind_on_both_sides_and_the_art_agrees(self):
        for book_name, play_name, formation_name, slots, word in self.CASES:
            book, body = self.books[book_name]
            formation = next(f for f in book.formations if f.name == formation_name)
            play = next(book.plays[link.play_index] for link in formation.play_links
                        if book.plays[link.play_index].name == play_name)
            record = lib.formation_record(body, formation.index)
            _flags, chains = lib.play_chains(body, play.index)
            for slot, (x_yd, kinds) in slots.items():
                with self.subTest(book=book_name, play=play_name, slot=slot):
                    x = record.slots[slot].x[0]
                    self.assertAlmostEqual(x / YD, x_yd, delta=0.1)
                    decoded = [codec.Node.from_bytes(raw) for raw in chains[slot][1]]
                    self.assertEqual([int(n.operands[0]) for n in decoded if n.op == 0x12], kinds)
                    art = codec.play_art(decoded, (float(x), float(record.slots[slot].z[0])))
                    self.assertEqual(direction(lateral(art), x), word)


if __name__ == "__main__":
    unittest.main()
