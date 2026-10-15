"""Execute production human bursts, including native input, caps and sp1 guards."""
from pathlib import Path
import hashlib
import itertools
import os
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_abilities_runtime as abilities
from mod_editor.core import nfl2k5_human_tap_burst as human
from mod_editor.core import nfl2k5_tap_burst as sp1
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
try:
    from tests.nfl2k5_sprint_machine import SprintMachine
    from unicorn import x86_const as x86
except ImportError:
    SprintMachine = None

BASE = Path(os.environ.get("B773_SP2_BASE_XBE", "/nonexistent/base.xbe"))
RETAIL = Path(os.environ.get("NFL2K5_RETAIL_XBE", "/nonexistent/retail.xbe"))
BASE_HASH = "1b41ec19aac6377484b9b30ee7a5c5ab220fb93d61aa3c14bafdb70092a9504f"


@unittest.skipUnless(SprintMachine and BASE.is_file() and RETAIL.is_file(),
                     "Unicorn and pinned base/retail fixtures required")
class HumanBurstTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base, cls.retail = BASE.read_bytes(), RETAIL.read_bytes()
        assert hashlib.sha256(cls.base).hexdigest() == BASE_HASH
        assert hashlib.sha256(cls.retail).hexdigest() == RETAIL_SHA256
        cls.fixed, cls.receipt = abilities.apply(cls.base)
        settings = abilities.read_settings(cls.base)
        keys = ("lock_speedster", "lock_right_stick", "lock_special_moves", "right_stick_stars_only",
                "charge_stars_only", "button_moves_stars_only", "star_access")
        cls.fresh = abilities.apply(cls.retail, **{k: settings[k] for k in keys})[0]

    def test_install_replay_full_union_and_old_allocations(self):
        from tests.nfl2k5_allocator_stack import REQUESTS
        space.plan(REQUESTS)
        self.assertEqual(human.status(self.base), "retail")
        self.assertEqual(human.status(self.fixed), "applied")
        self.assertEqual(sp1.status(self.fixed), "applied")
        self.assertEqual(abilities.apply(self.fixed)[1]["changed_bytes"], 0)
        self.assertEqual(human.apply(self.fixed)[0], self.fixed)
        self.assertTrue(all(a in space.layout(self.fixed)["allocations"]
                            for a in space.layout(self.base)["allocations"]
                            if a['owner'] != space.DIRECTORY_OWNER))
        old = next(a for a in space.layout(self.base)['allocations'] if a['owner'] == space.DIRECTORY_OWNER)
        new = next(a for a in space.layout(self.fixed)['allocations'] if a['owner'] == space.DIRECTORY_OWNER)
        self.assertEqual(new, dict(old, size=space.PAGE-human.CODE_SIZE))
        self.assertEqual(abilities.read_settings(self.base), abilities.read_settings(self.fixed))
        self.assertEqual(len(self.base), len(self.fixed))

    def test_legacy_gap_install_keeps_the_authors_exact_hash_and_replays(self):
        with patch.object(human, 'REQUESTS', ((human.LEGACY_OWNER, 'code', 512, 16),)):
            legacy = abilities.apply(self.base)[0]
        self.assertEqual(hashlib.sha256(legacy).hexdigest(),
                         'a1304b2c59290d019a1edbcfb128985f191595141c631a15f230081396b40959')
        self.assertEqual(human.status(legacy), 'applied')
        self.assertEqual(abilities.apply(legacy)[0], legacy)

    def test_dike_speed70_and_curve_through_real_pad_layouts(self):
        for raw in (self.fixed, self.fresh):
            m = SprintMachine(raw)
            for speed, bonus, duration in ((64,.04,.25),(65,.04,.25),(70,.05,.30),
                                           (75,.06,.35),(90,.10,.5),(93,.10,.5),(127,.10,.5)):
                for layout, role, condition in itertools.product(range(3), (0,.17,1), (.8,1)):
                    m.setup(speed=speed, abilities=0x14, layout=layout)
                    m.f32(m.S+0x190,role);m.f32(m.COND+4,condition)
                    m.frame(True);m.frame(False)
                    self.assertEqual(m.frame(True), (22,22,0))
                    multiplier, expiry = m.enter_burst()
                    self.assertAlmostEqual(multiplier,1+bonus*condition,places=6)
                    self.assertAlmostEqual(expiry,duration,places=6)

    def test_cpu_charge_phase_and_non_tap_gates_preserve_state_and_abi(self):
        machines = [SprintMachine(p) for p in (self.base,self.fixed)]
        regs = ("EAX","EBX","ECX","EDX","ESI","EDI","EBP","ESP","EFLAGS")
        for phase,controller,command,star,charge,condition in itertools.product(
                (0,14),(-2,-1,0,3,4),(0,22),(False,True),(False,True),(0,.1,.5,1)):
            states=[];registers=[]
            for m in machines:
                m.setup(speed=93,controller=controller,abilities=0x100 if star else 0)
                m.u32(0xE602B8,phase);m.u32(m.T+0x1c,command)
                m.f32(m.S+0x44,1 if charge else 0);m.u32(m.S+0x90,3 if charge else 0)
                m.f32(m.COND+4,condition);m.run(0x30ED50,count=20000)
                states.append(bytes(m.uc.mem_read(m.P,0xE000)))
                registers.append([m.uc.reg_read(getattr(x86,'UC_X86_REG_'+r)) for r in regs])
            self.assertEqual(*registers)
            differences=[i for i,(a,b) in enumerate(zip(*states)) if a!=b]
            self.assertTrue(all(0x10d8<=i<0x10dc or 0x10e0<=i<0x10e4 for i in differences))
            eligible=phase==14 and 0<=controller<=3 and command==22 and machines[0].number(machines[0].S+0xd8)==.25
            self.assertEqual(bool(differences),eligible)

    def test_repeat_refresh_and_native_extra_preserve_stronger_stars(self):
        m = SprintMachine(self.fixed)
        for speed,duration in ((70,.3),(93,.5)):
            m.setup(speed=speed,abilities=0x100)
            m.frame(True);m.frame(False);m.frame(True);m.enter_burst()
            m.f32(m.S+0xe0,1.2)
            m.f32(m.S+0xe4,.01)
            m.sprint_rate()  # real update atelapsed0.1 withdecodedtap22
            self.assertAlmostEqual(m.number(m.S+0xe0),1.2,places=6)
            self.assertAlmostEqual(m.number(m.S+0xd8),.1+duration,places=6)
            self.assertGreaterEqual(m.number(m.S+0xe4),.01-1e-7)
            expiry=m.number(m.S+0xd8)
            m.u32(m.T+0x1c,0);m.sprint_rate()
            self.assertEqual(m.number(m.S+0xd8),expiry)

    def test_update_preserves_cpu_non_tap_charge_and_deeper_x87_values(self):
        pair = [SprintMachine(p) for p in (self.base, self.fixed)]
        for controller, command, charged in itertools.product((-1, 0, 3, 4), (0, 22), (False, True)):
            outcomes = []
            for m in pair:
                m.setup(speed=93, controller=controller, abilities=0x100)
                m.u32(m.T+0x1c, command)
                m.u32(m.S+0x90, 1 if charged else 0)
                m.f32(m.S+0xe0, 1.075 if charged else 1.04)
                m.f32(m.S+0xd8, 1.5 if charged else .25)
                m.f32(m.SCRATCH+16, 3.5)
                m.uc.mem_write(m.STOP+0x300, b'\xd9\x05'+struct.pack('<I', m.SCRATCH+16))
                m.uc.emu_start(m.STOP+0x300, m.STOP+0x306, count=1)
                rate = m.sprint_rate()
                self.assertEqual(m.pop_float(), 3.5)
                outcomes.append((rate, bytes(m.uc.mem_read(m.P, 0xE000))))
            if controller not in range(4) or command != 22 or charged:
                self.assertEqual(*outcomes)

    def test_caps_lock_and_hold_charge_unchanged(self):
        for locked in (False,True):
            raw=abilities.apply(self.retail,lock_speedster=locked,charge_stars_only=True)[0]
            old=abilities.apply_rating_rules(self.retail,lock_speedster=locked,charge_stars_only=True)[0]
            pair=[SprintMachine(p) for p in (old,raw)]
            for speed,flags in itertools.product((70,93,100,127),(0,0x20,0x100,0x120)):
                outcomes=[]
                for m in pair:
                    m.setup(speed=speed,abilities=flags)
                    rating=m.rating;pace=m.normal_speed()
                    commands=[m.frame(True)[0] for _ in range(90)]
                    outcomes.append((rating,pace,commands,m.number(m.S+0x44)))
                    m.u32(m.T+0x1c,22);m.enter_burst()
                    self.assertEqual(m.number(m.S+0x1b4),rating)
                self.assertEqual(*outcomes)
                self.assertEqual(outcomes[1][2],[22]+[0]*89)
                self.assertEqual(outcomes[1][3],1 if flags&0x100 else 0)

    def test_repair_write_replay_scope_studio_and_unknown_refusal(self):
        from tools.b77 import sp2_repair as repair
        with tempfile.TemporaryDirectory() as directory:
            before, after = (Path(directory) / name for name in ("before.xbe", "after.xbe"))
            before.write_bytes(self.base)
            after.write_bytes(self.base)
            written = repair.repair_executable(after)
            self.assertEqual(written["changed_bytes"], 1291)
            self.assertEqual(written["written_bytes"], 4182)
            self.assertEqual(after.read_bytes(), self.fixed)
            replay = repair.repair_executable(after)
            self.assertEqual((replay["changed_bytes"], replay["written_bytes"]), (0, 0))
            scope = repair.compare_executable(before, after, studio=True)
            self.assertEqual(scope["outside_scope_changed_bytes"], 0)
            self.assertTrue(scope["studio_equal"])
            corrupt = bytearray(self.fixed)
            corrupt[0] ^= 1
            after.write_bytes(corrupt)
            with self.assertRaisesRegex(ValueError, "unknown complete executable hash"):
                repair.repair_executable(after)
            self.assertEqual(after.read_bytes(), corrupt)
            with self.assertRaisesRegex(ValueError, "unknown comparison hashes"):
                repair.compare_executable(before, after)

    def test_foreign_hook_code_and_dependencies_refuse_even_resealed(self):
        a=next(r for r in space.layout(self.fixed)["allocations"] if r['owner']==human.OWNER)
        image=XbeImage(self.fixed)
        offsets=[image.offset(va,1) for va in (0x30EF48,0x30EFBB,0x30EDF1,0x50CB58)]
        offsets += [a['raw'],a['raw']+511]
        requests=space._read_scale_directory(self.fixed)
        for off in offsets:
            buf=bytearray(self.fixed);buf[off]^=1
            space._seal_scaleout(buf,requests)
            for section in _sections(buf):
                buf[section.header_offset+36:section.header_offset+56]=section_digest(buf,section)
            broken=bytes(buf)
            self.assertEqual(human.status(broken),'foreign')
            with self.assertRaises(ValueError):abilities.apply(broken)
            self.assertEqual(broken,bytes(buf))


if __name__ == "__main__":
    unittest.main()
