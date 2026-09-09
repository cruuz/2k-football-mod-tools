"""Standalone v5 integrity, native menu/control and projection proofs.

EXPERIMENTAL / UNWITNESSED. Bounded instruction fixtures are not gameplay.
"""
import math
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_camera as c, nfl2k5_xbe_space as space
from tests.mod_editor import test_nfl2k5_camera_far as old
from tests.mod_editor import test_nfl2k5_widescreen_polish as native
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe


class IntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The public v4 suite supplies the bounded allocator header fixture and
        # its synthetic header pins; these checks require no private executable.
        old.CameraPatchTests.setUpClass.__func__(cls)

    def test_only_broadcast_gameplay_pointers_change_and_native_record_is_preserved(self):
        before, after = c.read_preset_table(self.retail), c.read_preset_table(self.patched)
        ro = c.allocation(self.patched, 'read_only')
        for row in range(8):
            for state in range(29):
                if row == c.BROADCAST_ROW and state in c.BROADCAST_STATES:
                    self.assertEqual(after[row][state], (before[row][state][0], ro['va']))
                else:
                    self.assertEqual(before[row][state], after[row][state])
        self.assertEqual(c._read(self.patched, c.BROADCAST_TEMPLATE_VA, 80), c.BROADCAST_RETAIL_DESCRIPTOR)
        descriptor = c.broadcast_descriptor()
        # v5.3: type (+0), the look-at's near-side shift (+16) and 2.5 m lead (+24), the lens (+32) and the mount's
        # x and y (+48, +52: the loge front, 45 m out and 14 m up, instead of the template's press box) differ from
        # the retail template; the mount's z (+56), flag, lag pointer, callbacks and padding stay exact.
        self.assertEqual([i for i in range(0, 80, 4)
                          if descriptor[i:i+4] != c.BROADCAST_RETAIL_DESCRIPTOR[i:i+4]], [0, 16, 24, 32, 48, 52])
        self.assertEqual(c.decode_descriptor(descriptor)['type'], 2)
        self.assertEqual(c.decode_descriptor(descriptor)['flag'], 0)
        self.assertEqual(self.receipt['version'], 5)
        self.assertFalse(self.receipt['coach_mode_changed'])
        self.assertFalse(self.receipt['exact_coach_director_proved'])

    def test_forged_descriptor_seal_label_bounds_and_old_allocation_refuse_before_writers(self):
        ro = c.allocation(self.patched, 'read_only')
        requests = space._validate(self.patched)[2]
        # Even a correctly sealed allocator install cannot substitute a different
        # descriptor, lens, eye, callback, flag or padding for this owner.
        for offset in range(0, 80, 4):
            forged = bytearray(self.patched)
            forged[ro['raw'] + offset] ^= 1
            space._seal_scaleout(forged, requests)
            forged = bytes(forged)
            self.assertEqual(space.status(forged), 'applied')
            with patch.object(space, 'install_code', side_effect=AssertionError('writer reached')), \
                 patch.object(space, 'install_read_only', side_effect=AssertionError('writer reached')):
                with self.assertRaises(c.CameraPatchError):
                    c.apply(forged)
        for va in (0x2C6B76, 0x2C6965, 0x2C66C8, 0x52B718, 0xE69970, 0xA40C2, 0x5036C8):
            buf = bytearray(self.patched); buf[c._offset(buf, va)] ^= 1
            with self.assertRaises(c.CameraPatchError):
                c.apply(old.repin(buf))
        # A genuine v4-sized owner is foreign, never silently upgraded in place.
        allocated = space.apply(self.retail, ((c.OWNER, 'code', 64, 16),), scaleout=True)[0]
        with self.assertRaises(c.CameraPatchError):
            c.apply(allocated)
        self.assertEqual((ro['size'], c.CODE_SIZE), (80, 160))


@unittest.skipUnless(old.XBE.is_file() and old.u is not None,
                     'pinned USA default.xbe, Capstone and Unicorn required')
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.patched, cls.receipt = c.apply(cls.retail)

    put = staticmethod(old.SelectionProofTests.put)
    get = staticmethod(old.SelectionProofTests.get)
    stub = old.SelectionProofTests.stub

    def machine(self, payload=None):
        from tools.nfl2k5_camera_broadcast_proof import map_owned
        payload = self.patched if payload is None else payload
        h = native.RetailExecutionTests()
        uc = h.load(payload)
        if space.status(payload) == 'applied':
            map_owned(uc, payload)
        return h, uc

    def menu_machine(self):
        h, uc = self.machine()
        # The native enum, session setter and active-row setter execute. Only
        # scene-dependent frame/preview calls are substituted in the menu census.
        self.stub(uc, {0xA5620: (0, 4), 0x2C6800: (0, 0)})
        self.put(uc, 0xB616C0, 0)
        return h, uc

    def test_native_menu_callbacks_cycle_all_choices_and_never_enter_first_person(self):
        h, uc = self.menu_machine()
        row = struct.unpack('<13I', c._read(self.patched, 0x52B700, 52))
        self.assertEqual((row[6], row[7]), (0x2C6B00, 0x2C6B40))
        h.execute(uc, row[3]); self.assertEqual(uc.reg_read(old.r.UC_X86_REG_EAX), 7)
        h.execute(uc, row[4]); self.assertEqual(uc.reg_read(old.r.UC_X86_REG_EAX), 0)
        for callback, step in ((row[6], 1), (row[7], -1)):
            for i, choice in enumerate(c.MENU_ROWS):
                expected = c.MENU_ROWS[(i + step) % len(c.MENU_ROWS)]
                for coach in (0, 1):
                    self.put(uc, c.OPTION_GLOBAL_VA, choice)
                    self.put(uc, 0xB665F0, choice)
                    self.put(uc, 0xE6002C, coach)
                    slots = bytes((j * 13 + 3) % 256 for j in range(8 * 28))
                    uc.mem_write(0xE5FE88, slots)
                    settings = bytes(uc.mem_read(0xE5FF80, 736))
                    writes = []
                    handle = uc.hook_add(old.u.UC_HOOK_MEM_WRITE,
                        lambda _u, _a, address, size, _v, _d: writes.append((address, size)))
                    try:
                        h.execute(uc, callback)
                    finally:
                        uc.hook_del(handle)
                    self.assertEqual(self.get(uc, c.OPTION_GLOBAL_VA), expected)
                    self.assertEqual(self.get(uc, 0xB665F0), expected)
                    self.assertEqual(self.get(uc, 0xE6002C), coach)
                    self.assertEqual(bytes(uc.mem_read(0xE5FE88, len(slots))), slots)
                    changed = bytearray(settings); struct.pack_into('<I', changed, 0x70, expected)
                    self.assertEqual(bytes(uc.mem_read(0xE5FF80, 736)), changed)
                    self.assertFalse(any(address <= 0xE6002C < address + size for address, size in writes))
                    self.assertEqual(uc.reg_read(old.r.UC_X86_REG_EAX), 1)
                    self.assertEqual(uc.reg_read(old.r.UC_X86_REG_ESP), h.STACK + 4)
                    h.execute(uc, row[8])
                    label = uc.reg_read(old.r.UC_X86_REG_EAX)
                    text = bytes(uc.mem_read(label, 40)).decode('utf-16le').split('\0')[0]
                    self.assertEqual(text, c.PRESET_NAMES[expected])
            for invalid in (6, 8, 0xFFFFFFFF):
                self.put(uc, c.OPTION_GLOBAL_VA, invalid); self.put(uc, 0xB665F0, 0)
                h.execute(uc, callback)
                self.assertIn(self.get(uc, c.OPTION_GLOBAL_VA), c.MENU_ROWS)

    def test_native_label_width_preview_and_cancel_include_broadcast(self):
        h, uc = self.machine()
        labels = []
        def font_width(machine, address, _size, _data):
            if address != 0x49410:
                return
            ptr = machine.reg_read(old.r.UC_X86_REG_EDX)
            value = bytes(machine.mem_read(ptr, 40)).decode('utf-16le').split('\0')[0]
            labels.append(value)
            sp = machine.reg_read(old.r.UC_X86_REG_ESP)
            machine.reg_write(old.r.UC_X86_REG_EAX, len(value) * 10)
            machine.reg_write(old.r.UC_X86_REG_EIP, self.get(machine, sp))
            machine.reg_write(old.r.UC_X86_REG_ESP, sp + 4)
        handle = uc.hook_add(old.u.UC_HOOK_CODE, font_width)
        h.execute(uc, 0x2C66D0, ecx=h.AREA)
        uc.hook_del(handle)
        self.assertEqual(labels[-1], 'Broadcast')
        self.assertGreaterEqual(uc.reg_read(old.r.UC_X86_REG_EAX), 90)
        # The actual preview math accepts our complete type-2 record. Original
        # row 7 has zero offsets in this slot and cannot supply this geometry.
        uc.reg_write(old.r.UC_X86_REG_EBX, 7)
        h.execute(uc, 0x2C6800)
        matrix = native.RetailExecutionTests.f(uc, 0xC8DEF0, 16)
        self.assertTrue(all(math.isfinite(value) for value in matrix))
        self.assertTrue(any(abs(value) > 1 for value in matrix))
        self.put(uc, c.OPTION_GLOBAL_VA, 7, 1, 0, 1)
        h.execute(uc, 0x2C6A35)
        self.stub(uc, {0x709A0: (0, 0), 0xA5620: (0, 4)})
        self.put(uc, c.OPTION_GLOBAL_VA, 1)
        self.put(uc, 0xB665F0, 1)
        self.put(uc, 0xB616C0, 0)
        h.execute(uc, 0x2C6A90)
        self.assertEqual(self.get(uc, c.OPTION_GLOBAL_VA), 7)
        self.assertEqual(self.get(uc, 0xB665F0), 7)

    def test_coach_flag_controls_body_binding_independently_of_broadcast_row(self):
        h, uc = self.menu_machine()
        actor, controls = h.AREA + 0x6000, h.AREA + 0x7000
        self.put(uc, 0xE5FF80, 1)  # ordinary game, not mode 0/3 or First Person
        self.put(uc, 0xE5FFE4, 0)
        uc.mem_write(0xE5FE88, bytes(224)); self.put(uc, 0xE5FE88, 1)
        self.put(uc, 0xE5FC24, actor)
        self.put(uc, actor + 0xC, controls)
        self.stub(uc, {0x1A7840: (0, 0)})  # no replacement actor in the second pass
        for choice in (0, 1, 7):
            h.execute(uc, 0x2C6960, ecx=choice)
            for coach in (0, 1):
                self.put(uc, 0xE6002C, coach)
                uc.mem_write(controls, struct.pack('<9I', 0, 11, 12, 13, 14, 15, 16, 17, 18))
                h.execute(uc, 0x156870, args=(0xE5FC20,))
                self.assertEqual(self.get(uc, controls), 0xFFFFFFFF if coach else 0)
                self.assertEqual(self.get(uc, 0xE5FE88), 1)  # team/play-call ownership remains
                self.assertEqual(self.get(uc, 0xB665F0), choice)
                self.assertEqual(tuple(self.get(uc, controls + off) for off in range(16, 36, 4)),
                                 (0,) * 5 if coach else (14, 15, 16, 17, 18))
            # The untouched Coach Mode menu toggles only the independent flag.
            h.execute(uc, 0x149320)
            self.assertEqual(self.get(uc, 0xE6002C), 0)
            self.assertEqual(self.get(uc, 0xB665F0), choice)

    def test_raw_tv_live_descriptor_inherits_eye_but_adaptation_starts_independently(self):
        h, uc = self.machine()
        retail_table = c.read_preset_table(self.retail)
        output = []
        for eye in ((0., 650., -1600.), (3600., 1250., 200.)):
            uc.mem_write(0xA82D60, struct.pack('<4f', *eye, 1))
            h.execute(uc, 0x60090, ecx=0, edx=retail_table[7][16][1], args=(0x3F800000,))
            output.append(tuple(native.RetailExecutionTests.f(uc, 0xA82D60, 3)))
            h.execute(uc, 0x60090, ecx=0, edx=c.allocation(self.patched, 'read_only')['va'], args=(0x3F800000,))
            self.assertEqual(tuple(native.RetailExecutionTests.f(uc, 0xA82D60, 3)), c.BROADCAST_VALUES[2])
        self.assertNotEqual(*output)

    def test_generic_mycareer_keeps_broadcast_choice_player_binding_and_focus(self):
        from mod_editor.core import nfl2k5_my_career_mode as mode
        from tests.nfl2k5_my_career_mode4_fixture import Machine
        seed = space.apply(self.retail, c.REQUESTS + mode.REQUESTS, scaleout=True)[0]
        forward = c.apply(mode.apply(seed)[0])[0]
        reverse = mode.apply(c.apply(seed)[0])[0]
        self.assertEqual(forward, reverse)
        for away in (False, True):
            with self.subTest(away=away), Machine(forward) as m:
                body, _, _ = m.presentation(away=away)
                m.replace_stub(0xA5620, lambda: m.ret(pop=4))
                m.replace_stub(0x2C6800, lambda: m.ret())
                m.put(0xB665F0, 7)
                m.call(0xA55EB)
                self.assertEqual(m.get(0xB665F0), 0)
                controls = m.get(body + 12)
                control_before = bytes(m.uc.mem_read(controls, 36))
                for choice in c.MENU_ROWS:
                    m.put(0xB616C0, 16)
                    m.call(0x2C6960, ecx=choice)
                    m.call(0xA5490)
                    self.assertEqual(m.get(0xB665F0), choice)
                    self.assertEqual(m.get(0xE6002C), 0)
                    self.assertEqual(bytes(m.uc.mem_read(controls, 36)), control_before)
                    focus = m.BODIES + 0x1D000
                    args = (0x3C888889, focus, focus+16, focus+32, focus+48, 0x3F800000)
                    m.call('mode_camera_focus', args=args, stop=0x5F760)
                    self.assertEqual(m.get(m.reg('ESP') + 8), m.get(body + 0x18) + 0x30)
                    self.assertEqual(m.get(0xB665F0), choice)

    @classmethod
    def evidence(cls):
        # One native projection run (156 cases) shared by the framing and the stands proofs.
        if not hasattr(cls, '_evidence'):
            from tools.nfl2k5_camera_broadcast_proof import prove
            cls._evidence = prove(cls.retail)
        return cls._evidence

    def test_mount_stays_clear_of_the_near_stands_for_every_sampled_ball_position(self):
        # beta 63.1 (maumau78, 2026-09-09: "on right side will clip over crowd and stadium structure"). v5.2 put the
        # eye 5650 cm toward the camera side of the ball and 1650 cm up, the second level's own front-row height, so
        # the native follow carried the mount into the loge/club seats as soon as the ball passed the near hash, and
        # into the loge corner trim in the end zones. The stands model and the sampled ball grid live in the proof
        # tool; the eye here is the settled native one from the solver, per direction, state, zoom and aspect.
        from tools.nfl2k5_camera_broadcast_proof import (BALL_GRID_X, CLEAN_BALL_X, STANDS, V52_EYE_FOCUS_RELATIVE,
                                                         stands_violations)
        evidence = self.evidence()
        self.assertEqual(len(evidence['rows']), 156)
        self.assertEqual(max(BALL_GRID_X), CLEAN_BALL_X)
        self.assertGreaterEqual(CLEAN_BALL_X, 900.0)   # past the near hash (282) and up to the near numbers (1097)
        for row in evidence['rows']:
            self.assertEqual(row['stands']['violations'], [], (row['aspect'], row['direction'], row['state'], row['pass_zoom']))
            eye = row['metrics']['eye_focus_relative_cm']
            # the mount stays in front of the second level for the whole clean band and below its corner trim
            self.assertLess(eye[0] + CLEAN_BALL_X, STANDS['second_level']['front_x'])
            self.assertLess(eye[1], STANDS['corner']['y_from'])
        self.assertEqual(evidence['stands']['rows_with_violations'], 0)
        # The reported failure, reproduced on the same grid with v5.2's settled eye (red before this fix): the second
        # level from the near hash on, the corner trim for balls in the end zone, in both play directions.
        for direction in (1, -1):
            old = stands_violations(V52_EYE_FOCUS_RELATIVE[:2] + (V52_EYE_FOCUS_RELATIVE[2] * direction,), direction)
            kinds = {v['kind'] for v in old}
            self.assertEqual(kinds, {'second level', 'corner trim'})
            self.assertTrue(any(v['kind'] == 'second level' and v['ball'][0] <= 300 for v in old))
            self.assertTrue(any(v['kind'] == 'corner trim' and abs(v['ball'][1]) >= 4572 for v in old))
            self.assertEqual(evidence['stands']['v52_violations'][str(direction)], len(old))

    def test_native_projection_all_gameplay_states_aspects_and_pass_options(self):
        evidence = self.evidence()
        self.assertEqual(len(evidence['rows']), 156)
        references = {}
        for row in evidence['rows']:
            metrics = row['metrics']
            target, lens, eye = c.BROADCAST_VALUES
            self.assertEqual(metrics['lens_word'], int(lens))
            self.assertAlmostEqual(metrics['downward_pitch_degrees'],
                                   math.degrees(math.atan2(eye[1], math.hypot(eye[0], eye[2]))), places=5)
            # the eye follows the shifted, led target: relative to the focus it is the look-at plus the mount's offset
            self.assertEqual(metrics['eye_focus_relative_cm'],
                             (eye[0] + target[0], eye[1] + target[1], (eye[2] + target[2]) * row['direction']))
            key = row['direction'], row['state'], row['pass_zoom']
            y = [point[1] for point in row['points_640x480'].values()]
            if row['aspect'] == '4:3':
                references[key] = y
            else:
                for a, b in zip(y, references[key]):
                    self.assertAlmostEqual(a, b, places=3)
            for name, (x, y) in row['points_640x480'].items():
                # v5.2 is the TV director's wide shot following the ball: the focus, the backfield, both flats and
                # the 15-yard receiver stay inside every aspect and above the scorebug; receivers 25 and 40 yards
                # deep are past the downfield edge until the camera follows the ball, as on television.
                self.assertTrue(0 < y < 381, (row['aspect'], name, x, y))
                if name not in ('left_deep', 'right_deep', 'deep_middle'):
                    self.assertTrue(0 < x < 640, (row['aspect'], name, x, y))
                else:  # past the downfield edge, whichever way the offense is moving
                    self.assertTrue(x < 0 if row['direction'] == 1 else x > 640, (row['aspect'], name, x, y))
            self.assertTrue(abs(row['points_640x480']['focus'][0] - 320) < 64, row['points_640x480']['focus'])


if __name__ == '__main__':
    unittest.main()
