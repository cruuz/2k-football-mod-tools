"""MyCareer defensive camera (b780 n1): a defensive MyPlayer sees the play from behind his own defense.

SWeaR, 2026-11-02: "The camera in MyCareer needs to be flipped when playing as a defensive player so you're facing
the offense." The game's camera faces one way, the float B61760 (+1 or -1), which the retail code sets only from the
offense's field direction (0x880A0 at every camera state change, refreshed by 0x88410 and 0x88490). Every camera
consumer reads it through the getter 0x883F0 (camera states 5..27; 1.0 otherwise) and the solver 0x5F760 multiplies
the descriptor's target and offset z by it, so the retail game always films from behind the offense, whoever the
user controls. MyCareer replaces only the getter's read (0x883FF): while its bound MyPlayer body is on the defensive
side (body +0x38 == [0xE60284]) the getter returns -B61760. B61760 itself keeps the offense's direction.

Proof level: native code under Unicorn on the pinned USA retail XBE with MyCareer applied (the real getter, the
real binder through a native career load, the real retail camera solver for the settled eye). The look in the
game and the stick mapping are emulator evidence, recorded in the b780 n1 report.
"""
from pathlib import Path
import hashlib
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC

GETTER, READ, DIRECTION, CAMERA_STATE = 0x883F0, 0x883FF, 0xB61760, 0xB616C0
OFFENSE, DEFENSE = 0xE60280, 0xE60284
HOME, AWAY = 0xE5FC20, 0xE5FC60
DEFENSIVE_POSITIONS = (4, 5, 6, 10, 11, 15, 16)      # CB FS SS OLB ILB DT DE (native position codes)
OFFENSIVE_POSITIONS = (0, 3, 7, 8, 9, 12, 13, 14)    # QB WR HB FB TE C G T


def f32(word):
    return struct.unpack('<f', struct.pack('<I', word))[0]


def word(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


class DefensiveCameraStaticTests(unittest.TestCase):
    def test_hook_and_guard_are_declared(self):
        hooks = {name: (va, pin, op) for name, va, pin, op in mode.MODE_HOOKS}
        self.assertEqual(hooks['mode_camera_dir'], (READ, 'd9056017b600', 0xE9))   # fld dword ptr [0xB61760]
        guards = {va: (size, digest) for va, size, digest in mode.GUARDS}
        self.assertEqual(guards[GETTER][0], 0x1D)

    def test_runtime_source_negates_only_the_read_for_a_defensive_body(self):
        source = (ROOT / 'tools/mycareer_mode/runtime.S').read_text(encoding='utf-8')
        body = source[source.index('mode_camera_dir:'):source.index('mode_art_input:')]
        code = [line.split('/*')[0].strip() for line in body.splitlines()]
        code = [line for line in code if line and not line.startswith('*')]
        self.assertEqual(code, [
            'mode_camera_dir:', 'fld DWORD PTR [0xb61760]', 'call enabled', 'jz 1f',
            'mov eax,DWORD PTR [state+2568]', 'test eax,eax', 'jz 1f', 'mov eax,DWORD PTR [eax+0x38]',
            'cmp eax,DWORD PTR [0xe60284]', 'jne 1f', 'fchs', '1: ret'])


@unittest.skipUnless(HAVE_UC and XBE.is_file(), 'pinned USA XBE and Unicorn required')
class DefensiveCameraNativeTests(unittest.TestCase):
    STUB, OUT = 0x221F000, 0x221F100

    @classmethod
    def setUpClass(cls):
        if XBE.stat().st_size > 16 * 1024**2:
            raise unittest.SkipTest('retail XBE exceeds 16 MiB')
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest('retail XBE pin differs')
        cls.payload = mode.apply(cls.retail)[0]

    def machine(self, position, away):
        from tests.nfl2k5_my_career_mode_fixture import Machine
        from tests.mod_editor.test_nfl2k5_my_career_control import ControlTests
        m = Machine(self.payload)
        body, side = ControlTests().load(m, position, away)
        self.assertEqual(m.call('mode_unit_present'), body)      # the real binder sets S(2568)
        self.assertEqual(m.get(m.state + 2568), body)
        self.assertEqual(m.get(body + 0x38), side)
        # call 0x883F0 ; fstp dword ptr [OUT] ; ret
        stub = b'\xe8' + struct.pack('<i', GETTER - (self.STUB + 5)) + b'\xd9\x1d' + struct.pack('<I', self.OUT) + b'\xc3'
        m.uc.mem_write(self.STUB, stub)
        return m, body, side

    def facing(self, m, state, direction):
        m.put(CAMERA_STATE, state)
        m.put(DIRECTION, word(direction))
        m.put(self.OUT, 0xDEADBEEF)
        regs = (0x1111, 0x2222, 0x3333)
        m.call(self.STUB, ecx=regs[0], edx=regs[1], ebx=regs[2])
        self.assertEqual((m.reg('ECX'), m.reg('EDX'), m.reg('EBX')), regs)   # only EAX may change
        self.assertEqual(m.get(DIRECTION), word(direction))                 # B61760 keeps the offense's direction
        return f32(m.get(self.OUT))

    def test_the_getter_jumps_to_the_owned_read_and_the_rest_stays_retail(self):
        image, retail = XbeImage(self.payload), XbeImage(self.retail)
        labels = mode.code_for(mode.legacy.allocations(self.payload)[0]['va'],
                               mode.legacy.allocations(self.payload)[1]['va'])[1]
        site = image.read(READ, 6)
        self.assertEqual(site[0], 0xE9)
        self.assertEqual(READ + 5 + struct.unpack_from('<i', site, 1)[0], labels['mode_camera_dir'])
        self.assertEqual(site[5], 0x90)
        self.assertEqual(image.read(GETTER, READ - GETTER), retail.read(GETTER, READ - GETTER))
        self.assertEqual(image.read(READ + 6, 7), retail.read(READ + 6, 7))
        self.assertEqual(mode.status(self.payload), 'applied')

    def test_defensive_myplayer_faces_the_offense_in_every_gameplay_state(self):
        for position in DEFENSIVE_POSITIONS:
            for away in (False, True):
                m, body, side = self.machine(position, away)
                with self.subTest(position=position, away=away), m:
                    m.put(OFFENSE, HOME if away else AWAY)       # MyPlayer's club is on defense
                    m.put(DEFENSE, side)
                    for direction in (1.0, -1.0):
                        for state in range(29):
                            expected = (-direction if 5 <= state <= 27 else 1.0)
                            self.assertEqual(self.facing(m, state, direction), expected, (state, direction))

    def test_offensive_myplayer_keeps_the_retail_view(self):
        for position in OFFENSIVE_POSITIONS:
            m, body, side = self.machine(position, False)
            with self.subTest(position=position), m:
                self.assertEqual((m.get(OFFENSE), m.get(DEFENSE)), (HOME, AWAY))
                for direction in (1.0, -1.0):
                    for state in (5, 7, 8, 9, 10, 11, 14, 16, 19, 23, 27):
                        self.assertEqual(self.facing(m, state, direction), direction)

    def test_possession_change_turns_the_view_with_the_side(self):
        m, body, side = self.machine(11, False)          # an ILB of the home club, home on offense in the fixture
        with m:
            self.assertEqual(self.facing(m, 11, 1.0), 1.0)   # his club has the ball: retail
            m.put(OFFENSE, AWAY); m.put(DEFENSE, HOME)       # turnover: his club defends
            self.assertEqual(self.facing(m, 11, 1.0), -1.0)
            self.assertEqual(self.facing(m, 16, -1.0), 1.0)
            m.put(OFFENSE, HOME); m.put(DEFENSE, AWAY)       # and has the ball again
            self.assertEqual(self.facing(m, 16, -1.0), -1.0)

    def test_off_field_absent_or_inactive_myplayer_keeps_the_retail_view(self):
        for case in ('absent', 'unbound', 'disabled', 'quit'):
            m, body, side = self.machine(4, True)
            with self.subTest(case=case), m:
                self.assertEqual(self.facing(m, 11, 1.0), -1.0)      # bound defender: flipped
                if case == 'absent':
                    m.put(body + 0x48, 1)                          # not a field body any more (the binder's test)
                    self.assertEqual(m.call('mode_unit_present'), 0)
                elif case == 'unbound':
                    m.put(m.state + 2568, 0)
                elif case == 'disabled':
                    m.put(0xE576A0, 0)                             # not in the Franchise/MyCareer context
                else:
                    m.put(m.state, 0)                              # MyCareer left (magic cleared)
                for state in (8, 11, 14, 16):
                    self.assertEqual(self.facing(m, state, 1.0), 1.0, (case, state))
                    self.assertEqual(self.facing(m, state, -1.0), -1.0, (case, state))

    def test_retail_refresh_still_sees_the_offense_direction(self):
        """0x88490 resets the camera when B61760 differs from the offense's sign. The owned read must not feed it."""
        m, body, side = self.machine(10, True)
        with m:
            at = m.BODIES + 0x1E000
            for address, value in ((HOME + 8, at), (at + 0xC, at + 0x100), (at + 0x104, word(-1.0))):
                m.put(address, value)
            m.put(DIRECTION, word(-1.0))
            resets = []
            m.stub(0xA5AA0, lambda: (resets.append(1), m.ret()))
            m.put(CAMERA_STATE, 11)
            self.assertEqual(self.facing(m, 11, -1.0), 1.0)          # MyPlayer (away club) defends: flipped read
            m.call(0x88490)
            self.assertEqual(resets, [])                             # same offense sign: no camera reset
            self.assertEqual(m.get(DIRECTION), word(-1.0))

    def test_native_solver_puts_the_eye_behind_the_defense(self):
        """The getter's value through the retail Standard pre-snap and live descriptors (states 11, 16, 17) and the
        retail solver 0x5F760 (settled eye): with the offense attacking toward +d, a defensive MyPlayer's camera sits
        on the defense's side of the focus (z * d > 0) and looks back across it toward the offense."""
        from nfl2k5_camera_far_proof import Projection
        image = XbeImage(self.retail)
        for state in (11, 16, 17):
            descriptor = struct.unpack('<II', image.read(0x4F03F8 + state * 8, 8))[1]     # row 0 (Standard)
            for d in (1.0, -1.0):
                for defense in (False, True):
                    camera = -d if defense else d                  # what the owned getter returns (tests above)
                    with self.subTest(state=state, offense=d, defense=defense):
                        p = Projection(self.retail)
                        p.setup(descriptor, direction=camera)
                        eye_z, target_z = p.eye[2], p.target[2]
                        self.assertGreater(eye_z * d if defense else -eye_z * d, 600.0, (p.eye, p.target))
                        self.assertLess((target_z - eye_z) * eye_z, 0.0, (p.eye, p.target))


if __name__ == '__main__':
    unittest.main()
