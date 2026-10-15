"""Execute the automatic-profile adapters and native CPU publication tails.

Private disc/executable inputs are opt-in. No selector, RNG, publication tail,
controller-ownership writer or playback accessor is mocked.
"""
from pathlib import Path
import json
import os
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_coach_ai as ai, nfl2k5_coach_ai_code as code


class Capacity(unittest.TestCase):
    def test_adapter_fits_existing_allocation(self):
        self.assertLessEqual(len(code.CODE), ai.CODE_SIZE)
        self.assertEqual((ai.CODE_SIZE, ai.DATA_SIZE), (5120, 128))


class NativePresentation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = os.environ.get("NFL2K5_COACH_AI_XBE")
        image = os.environ.get("NFL2K5_COACH_AI_IMAGE")
        if not source or not image:
            raise unittest.SkipTest("Set NFL2K5_COACH_AI_XBE and NFL2K5_COACH_AI_IMAGE for native execution")
        from mod_editor.core import nfl2k5_roster_records as rr
        from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
        cls.xbe = ai.apply(Path(source).read_bytes())[0]
        with OuterImage(image) as archive:
            raw = archive.read_entry(BOOK_ENTRIES["SEA"])
            roster = rr.RosterDocument(archive.read_entry(5)[32:])
        cls.book, cls.receipt = ai.build_profile(raw, json.loads(
            (ROOT / "data/vip/coaches/SEA.json").read_text()))
        at = roster.teams[cls.receipt["book_index"]].coach_offset
        cls.coach = roster.body[at:at + 0xA8]

    def world(self, mode=4, payload=None):
        from tools.b77.vp2_native import bind_automatic
        w, context = bind_automatic(payload or self.xbe, self.book, self.receipt, self.coach, mode)
        # Use the real two runtime objects, rather than World's selector alias.
        w.put(0xE60280, 0xE5FC60)
        w.put(0xE60284, 0xE5FC20)
        w.configure()
        return w, context

    def test_paired_book_native_accessor_suppresses_profile_draw(self):
        from mod_editor.core import nfl2k5_playbook_pair as pair, nfl2k5_xbe_space as space
        from mod_editor.core import nfl2k5_cpu_money_downs as money
        from mod_editor.core import nfl2k5_play_scoring as s
        source = os.environ.get("NFL2K5_COACH_AI_RETAIL_XBE")
        if not source:
            self.skipTest("Set NFL2K5_COACH_AI_RETAIL_XBE for paired-book execution")
        requests = money.REQUESTS + ai.REQUESTS + pair.REQUESTS
        payload = space.apply(Path(source).read_bytes(), requests, scaleout=True)[0]
        payload = money.apply(payload, level="modern2")[0]
        payload = pair.apply(ai.apply(payload)[0])[0]
        w, context = self.world(payload=payload)
        # The real paired-book accessor suppresses VIP access for a side whose
        # runtime book pair is active, even while the automatic binding exists.
        w.put(pair.allocations(payload)["data"]["va"] + 92, 1)
        self.assertEqual(w.call(0xF71E0, ecx=0xE5FC60), 0)
        out = s.SOURCE + 0x19100
        w.m.mem_write(out, b"\xa5" * 16)
        pc = ai.allocations(payload)["code"]["va"] + code.LABELS["coach_choose"]
        before = w.visits["0x17f1d0"]
        self.assertEqual(w.call(pc, ecx=0xE5FC60, edx=out), 0)
        self.assertEqual(w.visits["0x17f1d0"], before)
        self.assertEqual(bytes(w.m.mem_read(out, 16)), b"\xa5" * 16)
        self.assertEqual(w.get(0xBA04B4), context)
        self.assertEqual(w.get(0xE5FC98), 0)

    def test_native_offense_publication_uses_profile_without_virtual_controller(self):
        from mod_editor.core import nfl2k5_play_scoring as s, nfl2k5_playbook_inspector as ip
        from tools.b77.vp1_verify import settings
        for mode in (4, 5, 6, 7):
            w, context = self.world(mode)
            out = s.SOURCE + 0x19100
            for index in (0, 3, 6, 12, 18, 19):
                w.configure(**settings(index))
                w.call(0x1B2D40, ecx=0xE5FC60)
                for _ in range(4):
                    w.call(0x20B670, ecx=0xE5FC60, edx=out)
                    category, formation, play, coverage = struct.unpack("<4I", w.m.mem_read(out, 16))
                    fi = (formation - s.BOOK - ip.FORMATION_BASE) // ip.FORMATION_SIZE
                    pi = (play - s.BOOK - ip.PLAY_BASE) // ip.PLAY_SIZE
                    flags = w.get(w.get(0xE5FC60 + 12) + 0x24)
                    self.assertIn((fi, pi, bool(flags & 0x1004)), {
                        (c["formation"], c["play"], bool(c["flipped"]))
                        for c in self.receipt["pools"][index]["choices"]})
                    self.assertEqual(play, coverage)
                    self.assertNotEqual(category, 0)
                    self.assertNotEqual(w.get(context + 0xDE8), 0)
                    self.assertEqual(w.get(0xE5FC98), 0)
                    self.assertEqual(w.get(w.state_va + 60), 0)
                    self.assertEqual(w.get(0xE5FF80), mode)

    def test_native_defense_publication_and_controller_reassignment(self):
        from mod_editor.core import nfl2k5_play_scoring as s, nfl2k5_playbook_inspector as ip
        w, _ = self.world()
        w.change_controllers((False, False))
        context = w.get(0xBA04B0)
        w.call(0x1B2D40, ecx=0xE5FC20)
        out = s.SOURCE + 0x19100
        for _ in range(12):
            w.call(0x20B820, ecx=0xE5FC20, edx=out, args=(0,))
            _, formation, front, coverage = struct.unpack("<4I", w.m.mem_read(out, 16))
            record = w.get(context + 0xDEC)
            self.assertNotEqual(record, 0)
            expected = tuple(w.m.mem_read(record + 3, 3))
            actual = ((formation - s.BOOK - ip.FORMATION_BASE) // ip.FORMATION_SIZE,
                      (front - s.BOOK - ip.PLAY_BASE) // ip.PLAY_SIZE,
                      (coverage - s.BOOK - ip.PLAY_BASE) // ip.PLAY_SIZE)
            self.assertEqual(actual, expected)
            self.assertEqual([w.get(a + 0x38) for a in (0xE5FC20, 0xE5FC60)], [0, 0])
        w.change_controllers((True, False))
        self.assertEqual(w.get(0xBA04B0), 0)
        self.assertEqual(w.get(0xE5FC98), 0)

    def test_native_menu_branch_stays_inactive(self):
        from mod_editor.core import nfl2k5_play_scoring as s
        w, context = self.world()
        w.put(0xB70CA0, 0)
        def boundary(m, _a, _n, _d):
            # Stop this bounded branch before UI construction, with a synthetic
            # caller return. The native branch itself is unmodified.
            m.reg_write(w.r.UC_X86_REG_EIP, s.STOP)
            m.reg_write(w.r.UC_X86_REG_ESP, s.STACK + 4)
            m.emu_stop()
        hook = w.m.hook_add(w.ucmod.UC_HOOK_CODE, boundary, begin=0xAC5AD, end=0xAC5AD)
        before = w.visits["0x17f1d0"]
        w.call(0xAC507, ebx=0, edi=1)
        w.m.hook_del(hook)
        self.assertEqual(w.get(0xB70CA0), 0)
        self.assertEqual(w.visits["0x17f1d0"], before)
        self.assertEqual(w.get(0xBA04B4), context)

    def test_human_explicit_vip_special_phases_and_reentry_bypass(self):
        from mod_editor.core import nfl2k5_play_scoring as s
        from tools.b77.vp2_native import user_choice
        for case in ("human", "explicit", "special_1", "special_2", "special_3", "reentry", "wrong_book",
                     "scenario", "challenge"):
            with self.subTest(case=case):
                w, _ = self.world()
                if case == "human":
                    w.change_controllers((False, True))
                elif case == "explicit":
                    chosen = user_choice(w, self.receipt["book_index"])
                    w.put(0xBA04B4, chosen)
                    w.setup(team=0xE5FC60)
                    self.assertEqual(w.get(0xBA04B4), chosen)
                    self.assertEqual(w.get(0xE5FC98), 1)
                elif case == "reentry":
                    w.put(w.state_va + 60, 1)
                elif case == "wrong_book":
                    w.put(0xE5FC60 + 0x20, 0)
                elif case == "scenario":
                    w.put(0xE5FF80, 8)
                elif case == "challenge":
                    w.put(0xE601FC, 1)
                else:
                    w.put(0xE602B4, int(case[-1]))
                out = s.SOURCE + 0x19100
                w.m.mem_write(out, b"\xa5" * 16)
                before = w.visits["0x17f1d0"]
                pc = ai.allocations(self.xbe)["code"]["va"] + code.LABELS["coach_choose"]
                self.assertEqual(w.call(pc, ecx=0xE5FC60, edx=out), 0)
                self.assertEqual(bytes(w.m.mem_read(out, 16)), b"\xa5" * 16)
                self.assertEqual(w.visits["0x17f1d0"], before)


if __name__ == "__main__":
    unittest.main()
