"""Broadcast kick views (v7): which camera states, constants, native setup callback and final eye box.

Noah 10/29: "broadcasts don't normally show [field goals and punts] sideways." Only field goal / extra point and punt
states leave the sideline mount; kickoffs, returns and every scrimmage state keep it. The states were proved on the
released v0.7 disc in a headless xemu Quick Game (camera state B616C0 polled through a field goal and a punt) and
against the native play-type decode (0x894A0) and release dispatch (0x9FFB6); these tests pin the result and execute
the owned setup callback and final-eye clamp natively. EXPERIMENTAL: the framing is not a gameplay witness.
"""
from pathlib import Path
import hashlib
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_camera as c, nfl2k5_xbe_space as space
from tools.nfl2k5_presentation_proof import FinalProjection
from tests.mod_editor.test_nfl2k5_camera_far import XBE, u
from tools.nfl2k5_camera_far_proof import RETAIL_SHA256

KICK_STATES = (9, 10, 13, 14)
CAMERA = 0xA82940                  # camera 0 object; the copied descriptor is at +0x3F0, target/lens/offset at +0x400
BOX = (0x3C0, 0x3C4, 0x3C8, 0x3D0, 0x3D4, 0x3D8)


class KickStaticTests(unittest.TestCase):
    def test_states_and_constants_are_pinned(self):
        self.assertEqual(c.VERSION, 7)
        self.assertEqual(c.KICK_SET_STATE, {9: c.KICK_FG_GROUND, 10: c.KICK_PUNT_GROUND,
                                            13: c.KICK_FG_AIR, 14: c.KICK_PUNT_AIR})
        self.assertEqual(c.KICK_GATED_STATE, 11)
        self.assertEqual((c.PLAY_KIND_VA, c.CAMERA_STATE_VA), (0xE602BC, 0xB616C0))
        # kickoffs (8), the PAT-to-kickoff setup (7), timeout (12), scrimmage live and pass states are never kick sets
        self.assertTrue(set(c.KICK_SET_STATE).isdisjoint({7, 8, 11, 12, 15, 16, 17, 18, 19}))

    def test_the_four_sets_are_pinned_byte_for_byte(self):
        sets = c.kick_sets()
        self.assertEqual(len(sets), 4 * c.KICK_SET_SIZE)
        expected = {
            c.KICK_FG_GROUND: ((0.0, 100.0, 1365.0), 42.0, (0.0, 450.0, -3665.0)),
            c.KICK_PUNT_GROUND: ((0.0, 100.0, 387.0), 40.0, (0.0, 550.0, -3287.0)),
            c.KICK_FG_AIR: ((0.0, 100.0, 2200.0), 40.0, (0.0, 350.0, -4100.0)),
            c.KICK_PUNT_AIR: ((0.0, 100.0, 2000.0), 37.0, (0.0, 450.0, -4600.0)),
        }
        self.assertEqual(c.KICK_VALUES, expected)
        for index, (target, lens, offset) in expected.items():
            raw = sets[c.KICK_SET_SIZE * index:c.KICK_SET_SIZE * (index + 1)]
            words = struct.unpack('<12f', raw)
            # the record's words +0x10 .. +0x40: look-at xyz and its pad, lens, offset xyz and the native 1.0 word
            self.assertEqual(words[0:3], target)
            self.assertEqual(words[3], 0.0)
            self.assertEqual(words[4], lens)
            self.assertEqual(words[5:8], (0.0, 0.0, 0.0))
            self.assertEqual(words[8:11], offset)
            self.assertEqual(words[11], 1.0)
            # behind the kicker and above the grass, nowhere near the sideline mount (x 4900, y 1400)
            eye = tuple(t + o for t, o in zip(target, offset))
            self.assertEqual(eye[0], 0.0)
            self.assertTrue(c.KICK_EYE_MIN_Y < eye[1] < c.KICK_EYE_MAX_Y, eye)
            self.assertTrue(-c.EYE_MAX_Z < eye[2] < 0, eye)

    def test_owner_budget_and_layout(self):
        self.assertEqual((c.CODE_SIZE, c.READ_ONLY_SIZE), (864, 320))
        self.assertEqual(c.REQUESTS, ((c.OWNER, 'code', 864, 16), (c.OWNER, 'read_only', 320, 16)))
        self.assertEqual((c.SETUP_OFFSET, c.CLAMP_OFFSET, c.CLAMP_CONSTANTS_OFFSET, c.KICK_SETS_OFFSET),
                         (160, 368, 576, 672))
        code = c.code_for(0x14D0000)
        self.assertEqual(len(code), c.CODE_SIZE)
        self.assertEqual(code[c.KICK_SETS_OFFSET:], c.kick_sets())
        # the legacy v5.4 layout is untouched
        self.assertEqual(len(c.code_for(0x14D0000, 54)), 208)


@unittest.skipUnless(XBE.is_file() and u, 'pinned USA XBE and Unicorn required')
class KickNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest('retail hash differs')
        cls.patched, cls.receipt = c.apply(cls.retail)
        cls.table = c.read_preset_table(cls.patched)[c.BROADCAST_ROW]
        cls.ro = c.allocation(cls.patched, 'read_only')['va']

    def put(self, p, address, value):
        p.uc.mem_write(address, struct.pack('<I', value))

    def words(self, p, offset, count):
        return struct.unpack('<%df' % count, bytes(p.uc.mem_read(CAMERA + offset, 4 * count)))

    def setup(self, state, kind, direction=1):
        p = FinalProjection(self.patched)
        self.put(p, c.CAMERA_STATE_VA, state)
        self.put(p, c.PLAY_KIND_VA, kind)
        p.setup(self.table[state][1], direction=direction)
        return p

    def test_receipt_and_allocation(self):
        self.assertEqual(self.receipt['version'], 7)
        self.assertEqual(self.receipt['owned_code_bytes'], 864)
        self.assertEqual(c.allocation(self.patched)['size'], 864)
        self.assertEqual(c.status(self.patched), 'applied')
        self.assertEqual(c.apply(self.patched)[0], self.patched)

    def test_setup_callback_swaps_only_the_kick_states(self):
        normal = {}
        for state in c.BROADCAST_STATES:
            if state == 1:
                continue
            p = self.setup(state, 0)
            normal[state] = (self.words(p, 0x400, 12), self.words(p, 0x388, 1), self.words(p, 0x3C0, 8))
        for state in c.BROADCAST_STATES:
            if state == 1:
                continue
            for kind in range(0, 7):
                p = self.setup(state, kind)
                got = (self.words(p, 0x400, 12), self.words(p, 0x388, 1), self.words(p, 0x3C0, 8))
                kick_index = c.KICK_SET_STATE.get(state)
                if state == c.KICK_GATED_STATE and kind in (3, 6):
                    kick_index = c.KICK_FG_GROUND if kind == 3 else c.KICK_PUNT_GROUND
                if kick_index is None:
                    self.assertEqual(got, normal[state], (state, kind))
                    # the sideline mount: x minimum positive, y box 1400..1500
                    self.assertEqual((got[2][0], got[2][1], got[2][5]), (2500.0, 1400.0, 1500.0))
                    continue
                target, lens, offset = c.KICK_VALUES[kick_index]
                raw = struct.unpack('<12f', c.kick_sets()[48 * kick_index:48 * kick_index + 48])
                self.assertEqual(got[0], raw, (state, kind))
                self.assertEqual(got[1], (lens,), (state, kind))
                # eye box: behind-the-kicker view may sit anywhere over the field, 2..14 m up, inside the end zones
                box = got[2]
                self.assertEqual((box[0], box[1], box[2]), (-c.EYE_MAX_X, c.KICK_EYE_MIN_Y, -c.EYE_MAX_Z))
                self.assertEqual((box[4], box[5], box[6]), (c.EYE_MAX_X, c.KICK_EYE_MAX_Y, c.EYE_MAX_Z))

    def test_other_rows_and_kick_states_without_a_kick_keep_native_records(self):
        # kickoff (8), setup (7), timeout (12), pass in the air (15) and the live states keep the sideline mount for
        # every play kind, including kickoff kinds 1 and 2 and the kinds that stay set through a return
        for state in (7, 8, 12, 15, 16, 17, 18, 19):
            for kind in range(0, 7):
                p = self.setup(state, kind)
                self.assertEqual(self.words(p, 0x3C0, 1), (2500.0,), (state, kind))
                self.assertEqual(self.words(p, 0x410, 1), (c._f32(c.BROADCAST_LENSES[c.broadcast_slot(state)]),), (state, kind))
        # state 11 with a pass or run kind (4, 5) or a kickoff kind (1, 2) is the sideline pre-snap
        for kind in (0, 1, 2, 4, 5):
            p = self.setup(11, kind)
            self.assertEqual(self.words(p, 0x3C0, 1), (2500.0,))
        # Standard and Far rows are untouched by this owner
        retail = c.read_preset_table(self.retail)
        after = c.read_preset_table(self.patched)
        for row in range(7):
            self.assertEqual(after[row], retail[row], row)

    def test_kick_eye_stays_inside_the_field_for_every_ball_and_inherited_eye(self):
        # Ball positions over the whole field and both end zones, an elevated ball in the air, both directions, and a
        # deliberately bad inherited eye and velocity (the sideline mount or the corner). Every native output, after
        # smoothing, sits inside the kick box: |x| within the field, 2..14 m up, |z| <= EYE_MAX_Z.
        for state in KICK_STATES:
            for direction in (1, -1):
                p = self.setup(state, 3 if state in (9, 13) else 6, direction)
                for va in (0xA82BF0, 0xA82C70):
                    p.uc.mem_write(va, struct.pack('<4f', 7300., 3650., 5936. * direction, 1.))
                p.uc.mem_write(0xA82C80, struct.pack('<4f', 4000., -2000., 5000. * direction, 0.))
                for n in range(0, 24):
                    ball = (min(2400, -2400 + n * 200), 2000. if state in (13, 14) else 0., (5486 - n * 457) * direction)
                    row = p.frame(ball, direction=direction, snap=(n % 5 == 0))
                    x, y, z = row['eye']
                    self.assertLessEqual(x, c.EYE_MAX_X - max(0, abs(z) - c.CORNER_START_Z) + 1e-3, (state, direction, row))
                    self.assertGreaterEqual(x, -c.EYE_MAX_X - 1e-3, (state, direction, row))
                    self.assertTrue(c.KICK_EYE_MIN_Y - 1e-3 <= y <= c.KICK_EYE_MAX_Y + 1e-3, (state, direction, row))
                    self.assertLessEqual(abs(z), c.EYE_MAX_Z + 1e-3, (state, direction, row))
                    self.assertEqual(row['eye'], row['filter_eye'])

    def test_kick_eye_sits_behind_the_ball_and_looks_downfield(self):
        # settled native projection of each set at the ball: the eye is behind the ball (relative to the play
        # direction) and the look-at is ahead of it, in both directions
        for state in KICK_STATES:
            for direction in (1, -1):
                p = self.setup(state, 3 if state in (9, 13) else 6, direction)
                eye, target = p.eye, p.target
                self.assertLess(eye[2] * direction, 0, (state, direction, eye))
                self.assertGreater((target[2] - eye[2]) * direction, 1500, (state, direction, eye, target))
                self.assertAlmostEqual(eye[0], 0.0, places=3)

    def test_uprights_and_the_kicker_read_on_the_ground_view(self):
        # Native play-state evidence (xemu, released v0.7 disc): in the field goal and extra point snap view (state 9)
        # the camera focus is the kicker, about 7 yards (640 cm) behind the line of scrimmage, so the uprights are
        # 1800 cm (an extra point from the 2) to 7700 cm (a 70-yard try) ahead of the focus. Projected through the
        # native solver (4:3 and 16:9): the whole upright (top, crossbar, foot) is on screen and above the scorebar
        # (y < 381 of 480) at every distance, the kicker sits in the middle of the frame and the line of scrimmage
        # (700 cm ahead of him) is in view.
        from mod_editor.core import nfl2k5_widescreen as wide
        for aspect in ('4:3', '16:9'):
            payload = self.patched if aspect == '4:3' else wide.apply(self.patched, aspect)[0]
            p = FinalProjection(payload)
            self.put(p, c.CAMERA_STATE_VA, 9)
            self.put(p, c.PLAY_KIND_VA, 3)
            p.setup(self.table[9][1])
            for distance in (1800, 3200, 5200, 7700):
                top_l, top_r = p.point(-282, 1372, distance), p.point(282, 1372, distance)
                bar, foot = p.point(0, 305, distance), p.point(0, 0, distance)
                self.assertTrue(0 < top_l[1] < bar[1] < foot[1] < 300, (aspect, distance, top_l, bar, foot))
                self.assertTrue(250 < top_r[0] < top_l[0] < 390, (aspect, distance, top_l, top_r))
            head, foot = p.point(0, 190, 0), p.point(0, 0, 0)
            self.assertTrue(150 < head[1] < foot[1] < 381 and abs(head[0] - 320) < 5, (aspect, head, foot))
            line = p.point(0, 175, 700)
            self.assertTrue(100 < line[1] < head[1], (aspect, line))
            self.assertTrue(0 < p.point(-600, 175, 700)[0] < 640 and 0 < p.point(600, 175, 700)[0] < 640)
            # Punt snap view (state 10): the focus is the punter, 15 yards behind the line of scrimmage.
            q = FinalProjection(payload)
            self.put(q, c.CAMERA_STATE_VA, 10)
            self.put(q, c.PLAY_KIND_VA, 6)
            q.setup(self.table[10][1])
            head, foot = q.point(0, 190, 0), q.point(0, 0, 0)
            self.assertTrue(150 < head[1] < foot[1] < 381 and abs(head[0] - 320) < 5, (aspect, head, foot))
            for x in (-600, 0, 600):
                px = q.point(x, 175, 1371)
                self.assertTrue(80 < px[1] < head[1] and 0 < px[0] < 640, (aspect, x, px))


if __name__ == '__main__':
    unittest.main()
