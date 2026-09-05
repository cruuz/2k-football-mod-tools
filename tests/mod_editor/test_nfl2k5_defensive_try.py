"""Standalone writer and bounded instruction proofs; no console/game witness."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import sys
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from mod_editor.core import nfl2k5_defensive_try as patch
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core import nfl2k5_dynamic_kickoff_relocated as relocated
from mod_editor.core import nfl2k5_kick_rules as kicks
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)" / "default.xbe"
try:
    import unicorn as uc
    from unicorn.x86_const import *  # noqa: F403
except ImportError:
    uc = None
try:
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
except ImportError:
    Cs = None


def reseal(payload):
    buf = bytearray(payload)
    for s in _sections(buf):
        buf[s.header_offset + 36:s.header_offset + 56] = section_digest(buf, s)
    return bytes(buf)


@unittest.skipUnless(XBE.is_file(), "private USA retail default.xbe is absent")
class WriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        cls.patched, cls.receipt = patch.apply(cls.retail)

    def test_retail_pin_and_exact_idempotent_receipt(self):
        self.assertEqual(hashlib.sha256(self.retail).hexdigest(), "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9")
        self.assertEqual(patch.status(self.retail), "retail")
        self.assertEqual(patch.status(self.patched), "applied")
        again, receipt = patch.apply(self.patched)
        self.assertEqual(again, self.patched)
        self.assertEqual(receipt["changed_bytes"], 0)
        self.assertFalse(receipt["runtime_witnessed"])
        self.assertEqual(self.receipt["changed_bytes"], sum(a != b for a, b in zip(self.retail, self.patched)) + len(self.patched) - len(self.retail))
        self.assertEqual(len(self.patched), space.FILE_SIZE)

    def test_each_hook_refuses_mixed_or_foreign_before_mutation(self):
        for name, (va, before, _) in {**patch.BRANCHES, **patch.HOOKS}.items():
            with self.subTest(name=name):
                damaged = bytearray(self.patched)
                damaged[va - 0x10000:va - 0x10000 + len(bytes.fromhex(before))] = bytes.fromhex(before)
                damaged = reseal(damaged)
                self.assertEqual(patch.status(damaged), "foreign")
                with self.assertRaises(ValueError):
                    patch.apply(damaged)
                foreign = bytearray(self.retail)
                foreign[va - 0x10000] ^= 0x40
                self.assertEqual(patch.status(reseal(foreign)), "foreign")
                with self.assertRaises(ValueError):
                    patch.apply(reseal(foreign))

    def test_code_seal_data_and_missing_owner_refusal(self):
        code, data = patch._sites(self.patched)
        self.assertFalse(any(self.patched[data["raw"]:data["raw"] + data["size"]]))
        for offset in (code["raw"], data["raw"], space.DIRECTORY + 20):
            broken = bytearray(self.patched)
            broken[offset] ^= 1
            with self.assertRaises(ValueError):
                patch.apply(bytes(broken))
        grown, _ = relocated.apply(self.retail)
        with self.assertRaisesRegex(ValueError, "allocation missing"):
            patch.apply(grown)

    def test_context_pins_refuse_resealed_nearby_foreign_instructions(self):
        broken=bytearray(self.retail)
        broken[0xB9B9A-0x10000] ^= 1
        self.assertEqual(patch.status(reseal(broken)),"foreign")
        with self.assertRaisesRegex(ValueError,"instruction context"):
            patch.apply(reseal(broken))

    def test_manifest_recorder_observes_hooks_and_zero_initialized_owner_data(self):
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest
        recorder=Recorder(self.retail)
        base,receipt=space.apply(self.retail,patch.REQUESTS+relocated.REQUESTS)
        recorder.observe(space,"apply",self.retail,base,receipt)
        result,receipt=patch.apply(base)
        recorder.observe(patch,"apply",base,result,receipt)
        final,receipt=relocated.apply(result)
        recorder.observe(relocated,"apply",result,final,receipt)
        spans=recorder.finish(final)
        code,data=patch._sites(final)
        for allocation in (code,data):
            self.assertTrue(any(row["owner"]==patch.OWNER and int(row["start"],0)==allocation["va"]
                                and row["size"]==allocation["size"] for row in spans))
        # The checked-in historical manifest remains protected. Check its
        # other retail hook owners; regeneration records the new owner union.
        historical=ReservationManifest.load(DEFAULT_MANIFEST,XbeImage(self.retail))
        for va,before,_ in {**patch.HOOKS,**patch.BRANCHES}.values():
            self.assertEqual(historical.overlaps(va,va+len(bytes.fromhex(before)),exclude_owner=patch.OWNER),[])
        self.assertTrue(any(row["owner"]==patch.OWNER and row["basis"]=="declared edit: cpu_return" for row in spans))

    def test_kicks_and_relocated_kickoff_compose_in_both_orders(self):
        for modern in (False, True):
            base = kicks.apply(self.retail)[0] if modern else self.retail
            union, _ = space.apply(base, patch.REQUESTS + relocated.REQUESTS)
            first = relocated.apply(patch.apply(union)[0])[0]
            second = patch.apply(relocated.apply(union)[0])[0]
            self.assertEqual(first, second)
            self.assertEqual(patch.status(first), "applied")
            self.assertEqual(relocated.status(first), "applied")
            if modern:
                self.assertEqual(kicks.status(first), "applied")
        # Kicks can also follow our own standalone growth.
        self.assertEqual(patch.status(kicks.apply(self.patched)[0]), "applied")

    @unittest.skipUnless(Cs is not None, "Capstone is absent")
    def test_hooks_cover_complete_instructions(self):
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        for name, (va, before, _) in {**patch.BRANCHES, **patch.HOOKS}.items():
            raw = bytes.fromhex(before)
            instructions = list(md.disasm(raw, va))
            self.assertEqual(sum(i.size for i in instructions), len(raw), name)


class Machine:
    """Synthetic objects; callbacks explicitly stubbed, all runs bounded."""
    STOP = 0x3000000
    STACK = 0x301F000
    CTX, RECORD, SPOT = 0x3020000, 0x3021000, 0x3022000
    TEAM = (0xE5FC20, 0xE5FC60)
    PLAYER = (0x3023000, 0x3024000)
    BALL, TRANSFORM, SNAPSHOT, DRIVE = 0x3025000, 0x3026000, 0x3027000, 0x3028000

    def __init__(self, payload):
        self.u = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        self.u.mem_map(0x10000, 0x14AC000)
        self.u.mem_map(self.STOP, 0x40000)
        self.image = XbeImage(payload)
        for s in self.image.sections:
            self.u.mem_write(s.start, payload[s.raw:s.raw + s.raw_size])
        protected = sorted({page for s in self.image.sections if s.executable and not s.writable
                            for page in range(s.start & ~4095, (s.end + 4095) & ~4095, 4096)
                            if not any(t.writable and t.start < page + 4096 and t.end > page for t in self.image.sections)})
        runs = []
        for page in protected:
            if runs and runs[-1][1] == page:
                runs[-1][1] += 4096
            else:
                runs.append([page, page+4096])
        for lo, hi in runs:
            self.u.mem_protect(lo, hi-lo, uc.UC_PROT_READ | uc.UC_PROT_EXEC)
        self.stubs = {}
        self.redirects = {}
        self.calls = []
        self.writes = []
        self.u.hook_add(uc.UC_HOOK_CODE, self._step)
        self.u.hook_add(uc.UC_HOOK_MEM_WRITE, lambda u, access, addr, size, value, _: self.writes.append((addr, size)))
        self.set(0xE602EC, self.CTX)
        self.set(patch.PHASE, 3)
        self.set(0xE602B8, 14)
        self.set(0xE602C0, 2)
        self.set(0xE60280, self.TEAM[0])
        self.set(0xE60284, self.TEAM[1])
        self.set(patch.ORIGINAL_TEAM, self.TEAM[0])
        self.set(0xE5FC00, self.BALL)
        self.set(self.BALL, self.PLAYER[1])
        self.set(self.BALL + 20, self.TRANSFORM)
        for team, player, i in zip(self.TEAM, self.PLAYER, range(2)):
            score = 0x3029000 + i * 0x1000
            self.set(team, self.TEAM[1-i])
            self.set(team + 8, score)
            self.set(score + 12, score + 0x100)
            self.float(score + 0x104, 1 if i == 0 else -1)
            self.set(player + 0x38, team)
            self.set(player + 0x1C, 1)
            self.set(player + 0x10, player + 0x100)
            self.set(player + 0x104, player + 0x200)
            self.set(player + 0x18, player + 0x300)
        self.set(self.CTX + 0x1A0, self.PLAYER[0])
        self.set(self.CTX + 0x1A8, self.PLAYER[1])
        self.set(self.CTX + 0x1AC, self.PLAYER[1])
        self.set(0xE57674, self.DRIVE)
        self.stub(0xA19E0)
        self.stub(0xA09B0)
        self.stub(0xA05F0, pop=4)
        self.stub(0xE9500)
        self.stub(0xAF4F0)
        self.stub(0xE9380)
        self.stub(0xA1BD0)

    def get(self, address):
        return struct.unpack("<I", self.u.mem_read(address, 4))[0]

    def set(self, address, value):
        self.u.mem_write(address, struct.pack("<I", value & 0xFFFFFFFF))

    def float(self, address, value):
        self.u.mem_write(address, struct.pack("<f", value))

    def reg(self, reg, value=None):
        if value is not None:
            self.u.reg_write(reg, value)
        return self.u.reg_read(reg)

    def stub(self, address, value=None, pop=0, action=None):
        self.stubs[address] = (value, pop, action)

    def _step(self, u, address, size, _):
        if address in self.redirects:
            self.calls.append(address)
            self.reg(UC_X86_REG_EIP,self.redirects[address])
            return
        if address in self.stubs:
            self.calls.append(address)
            value, pop, action = self.stubs[address]
            if action:
                action(self)
            if value is not None:
                self.reg(UC_X86_REG_EAX, value)
            sp = self.reg(UC_X86_REG_ESP)
            self.reg(UC_X86_REG_EIP, self.get(sp))
            self.reg(UC_X86_REG_ESP, sp + 4 + pop)

    def run(self, start, args=(), registers=None, stop=None):
        self.reg(UC_X86_REG_ESP, self.STACK)
        self.set(self.STACK, self.STOP)
        for i, v in enumerate(args):
            self.set(self.STACK + 4 + 4*i, v)
        for reg, val in (registers or {}).items():
            self.reg(reg, val)
        end = stop or self.STOP
        self.u.emu_start(start, end, count=20000)
        if self.reg(UC_X86_REG_EIP) != end:
            raise AssertionError(f"instruction budget exhausted at {self.reg(UC_X86_REG_EIP):#x}")
        return self.reg(UC_X86_REG_EAX)

    def descriptor(self, result, scorer=1):
        self.set(self.CTX + 0x178, result)
        self.set(self.CTX + 0x188, self.TEAM[scorer])
        self.set(self.CTX + 0x19C, self.PLAYER[scorer])
        self.run(0x22EB70, (self.TEAM[scorer], 0), {UC_X86_REG_ECX:self.RECORD, UC_X86_REG_EDX:self.SPOT})

    def dead_ball_fixture(self):
        self.set(0xE6028C, self.SPOT)
        self.set(0xB71D10, 17)
        for va in (0x874E0, 0xFEF50, 0x9FC30, 0x189080, 0x1CEEE0, 0x1E8480,
                   0xFEA90, 0xB7330, 0xFC6E0, 0x119760, 0x1195F0, 0x14F9E0,
                   0xAF260, 0xB6340, 0xB6180):
            self.stub(va, 0)
        self.stub(0x12D610, pop=4)


@unittest.skipUnless(XBE.is_file() and uc is not None, "private USA retail XBE or Unicorn is absent")
class InstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        cls.patched = patch.apply(cls.retail)[0]
        cls.modern = patch.apply(kicks.apply(cls.retail)[0])[0]

    def test_full_acquisition_handlers_then_score_or_tackle_both_teams(self):
        for kind in ("interception", "fumble", "blocked_pat"):
            for scorer in (0, 1):
                for score in (False, True):
                    with self.subTest(kind=kind, scorer=scorer, score=score):
                        m = Machine(self.modern)
                        original = 1 - scorer
                        runner, starter = m.PLAYER[scorer], m.PLAYER[original]
                        m.set(0xE5FF80, 1)
                        m.set(0xE602D4, m.SNAPSHOT)
                        m.set(patch.ORIGINAL_TEAM, m.TEAM[original])
                        m.set(0xE60280, m.TEAM[original])
                        m.set(0xE60284, m.TEAM[scorer])
                        m.set(m.CTX + 0x1A0, starter)
                        m.set(m.CTX + 0x1AC, runner)
                        m.set(m.BALL, runner)
                        m.set(0xE602C0, 4 if kind == "interception" else 3)
                        m.set(m.CTX + 0x1B0, starter)
                        m.set(m.CTX + 0x198, starter if kind == "fumble" else 0)
                        m.set(m.CTX + 0x134, int(kind == "blocked_pat"))
                        m.set(m.CTX + 0x1D0, starter if kind == "blocked_pat" else 0)
                        m.set(0xA8A1F0, 0)  # disable optional animation collision cue
                        m.stub(0xA0A00)    # catch notification
                        m.stub(0xA0B60)    # fumble notification
                        m.stub(0xA1BA0)    # blocked-kick presentation
                        m.stub(0x236210, 0, pop=4)  # field-body classifier: in bounds
                        if kind == "blocked_pat":
                            m.set(m.BALL, 0)
                            m.run(0xB78C0, registers={UC_X86_REG_ECX:runner})
                            self.assertEqual(m.get(m.CTX + 0x194), runner)
                            self.assertEqual(m.get(0xE602B8), 14)
                            m.set(m.BALL, runner)  # attachment engine is the fixture boundary
                        m.run(0xB9B50, registers={UC_X86_REG_ECX:runner})
                        self.assertEqual(m.get(0xE60280), m.TEAM[scorer])
                        self.assertEqual(m.get(0xE602B8), 14)
                        self.assertEqual(m.get(0xE602C0), 2)
                        self.assertEqual(m.reg(UC_X86_REG_ESP), m.STACK + 4)
                        if kind == "interception":
                            self.assertEqual(m.get(m.CTX + 0x1B8), runner)
                            self.assertEqual(m.get(m.SNAPSHOT + 0x70), 0)  # no normal INT event
                        if kind == "blocked_pat":
                            self.assertEqual(m.get(m.CTX + 0x134), 0)
                            self.assertEqual(m.get(m.CTX + 0x1CC), runner)
                        if score:
                            # Cross the real goal-plane classifier and its try
                            # score dispatch, including the ball-shape helper.
                            del m.stubs[0x236210]
                            m.float(m.SPOT + 8, 5000 if scorer == 0 else -5000)
                            m.float(m.TRANSFORM + 0x2C, 1)
                            m.stub(0x13A350)
                            m.stub(0x1D0140)
                            self.assertEqual(m.run(0xB7610, (m.SPOT, 0),
                                                   {UC_X86_REG_ECX:runner,
                                                    UC_X86_REG_EDX:runner}), 1)
                            self.assertEqual(m.get(m.CTX + 0x178), 1)
                        else:
                            m.stub(0xB6760, 0)  # tackle is in field, not a touchback
                            m.dead_ball_fixture()
                            m.run(0xB96B0, registers={UC_X86_REG_ECX:runner,
                                                     UC_X86_REG_EDX:starter})
                            self.assertEqual(m.get(0xE602B8), 18)
                            self.assertEqual(m.get(0xE602C0), 1)
                        m.descriptor(1 if score else 0, scorer)
                        m.run(0x22E4D0, registers={UC_X86_REG_ECX:m.RECORD,
                                                  UC_X86_REG_EDX:int(score)})
                        self.assertEqual(m.get(m.get(m.TEAM[scorer] + 8)), 2 if score else 0)
                        self.assertEqual(m.get(m.get(m.TEAM[original] + 8)), 0)
                        self.assertEqual(m.get(0xE60280), m.TEAM[original])
                        self.assertEqual(m.get(patch.PHASE), 2)

    def test_possession_then_return_score_and_original_team_kicks(self):
        for modern in (False, True):
            for scorer in (0, 1):
                m = Machine(self.modern if modern else self.patched)
                original = 1 - scorer
                m.set(patch.ORIGINAL_TEAM, m.TEAM[original])
                m.set(0xE60280, m.TEAM[original])
                m.set(0xE60284, m.TEAM[scorer])
                m.run(0xB91A0, registers={UC_X86_REG_ESI:m.PLAYER[scorer]})
                self.assertEqual(m.get(0xE60280), m.TEAM[scorer])
                self.assertEqual(m.get(patch.ORIGINAL_TEAM), m.TEAM[original])
                self.assertIn(0xA09B0, m.calls)
                m.run(0xB9E30, registers={UC_X86_REG_ESI:m.PLAYER[scorer]}, stop=0xB9E61)
                self.assertEqual(m.get(0xE602B8), 14)
                m.run(0xB8330, registers={UC_X86_REG_ECX:m.PLAYER[scorer]})
                m.descriptor(1, scorer)
                self.assertEqual(m.get(m.RECORD+0x74), 5)
                self.assertEqual(m.get(m.RECORD+0x7C), m.TEAM[scorer])
                self.assertEqual(m.get(m.RECORD+0x14), m.TEAM[original])
                z = struct.unpack("<f", m.u.mem_read(m.RECORD+0x48,4))[0]
                self.assertAlmostEqual(abs(z), 1371.6 if modern else 1828.8, places=2)
                # Full record applier, including the real two-point routine and
                # possession/direction updates; presentation callbacks are stubbed.
                m.run(0x22E4D0, registers={UC_X86_REG_ECX:m.RECORD, UC_X86_REG_EDX:1})
                self.assertEqual(m.get(m.get(m.TEAM[scorer]+8)), 2)
                self.assertEqual(m.get(m.get(m.TEAM[original]+8)), 0)
                self.assertEqual(m.get(0xE60280), m.TEAM[original])
                self.assertEqual(m.get(patch.PHASE), 2)

    def test_interception_and_block_touch_continue_without_holder(self):
        for payload, dies in ((self.retail, True), (self.patched, False)):
            m=Machine(payload)
            m.stub(0xA0390, action=lambda m: m.set(0xE602B8,18))
            m.run(0xB9B93, registers={UC_X86_REG_ESI:m.PLAYER[1]}, stop=0xB9E30 if dies else 0xB9BCD)
            self.assertEqual(m.get(0xE602B8),18 if dies else 14)
            m.set(0xE602B8,14)
            m.set(m.BALL,0)
            # At the first-touch branch, flags come from CMP phase,3.
            m.run(0xB7B51, registers={UC_X86_REG_EFLAGS:0x246}, stop=0xB7B5D)
            self.assertEqual(m.get(0xE602B8),18 if dies else 14)

    def test_recovery_then_tackled_short_ends_try_without_points(self):
        m=Machine(self.patched)
        m.run(0xB91A0, registers={UC_X86_REG_ESI:m.PLAYER[1]})
        m.run(0xB9E30, registers={UC_X86_REG_ESI:m.PLAYER[1]}, stop=0xB9E61)
        # Terminal geometry says no score; failed-try builder and applier real.
        m.descriptor(0)
        self.assertEqual(m.get(m.RECORD),2)
        self.assertEqual(m.get(m.RECORD+0x74),0)
        self.assertEqual(m.get(m.RECORD+0x14),m.TEAM[0])
        m.run(0x22E4D0,registers={UC_X86_REG_ECX:m.RECORD,UC_X86_REG_EDX:0})
        self.assertEqual(m.get(patch.PHASE),2)
        self.assertEqual([m.get(m.get(t+8)) for t in m.TEAM],[0,0])

    def test_try_safety_descriptor_and_one_point_dispatch_both_teams(self):
        for scorer in (0,1):
            m=Machine(self.modern)
            m.descriptor(2,scorer)
            self.assertEqual(m.get(m.RECORD+0x74),2)
            self.assertEqual(m.get(m.RECORD),2)
            self.assertEqual(m.get(m.RECORD+0x14),m.TEAM[0])
            m.run(0x22E4D0,registers={UC_X86_REG_ECX:m.RECORD,UC_X86_REG_EDX:1})
            self.assertEqual(m.get(m.get(m.TEAM[scorer]+8)),1)
            self.assertEqual(m.get(patch.PHASE),2)
            self.assertNotIn(0xA05F0,m.calls) # no ordinary safety event

    def test_history_matrix_expanded_packed_reader_summary_and_wrap(self):
        for outcome in (1,6):
            for drive_team in (0,1):
                td_team = drive_team ^ (outcome == 6)
                for event, scorer, subtype in ((5,1-td_team,5),(2,td_team,6),(2,1-td_team,7)):
                    m=Machine(self.patched)
                    index=127
                    m.set(0xE53800,index)
                    ring=patch.DRIVE_RING+index*4
                    word=(outcome<<26)|(drive_team<<21)|0x123456
                    m.set(ring,word)
                    m.set(m.SNAPSHOT,3)
                    m.set(m.SNAPSHOT+0x354,event)
                    m.set(m.SNAPSHOT+0x358,m.TEAM[scorer])
                    m.set(m.SNAPSHOT+0x35C,m.PLAYER[scorer])
                    for _ in range(2):
                        m.run(0xCD88A,registers={UC_X86_REG_EAX:ring,UC_X86_REG_ESI:m.SNAPSHOT},stop=0xCD909)
                        self.assertEqual(m.get(ring),word|(subtype<<29), (outcome,drive_team,event,scorer,subtype))
                        self.assertEqual(m.get(m.DRIVE+0x1C),subtype)
                    expected=[0,0];expected[td_team]=6;expected[scorer]+=2 if event==5 else 1
                    points=[m.run(0x250360,registers={UC_X86_REG_ECX:t,UC_X86_REG_EDX:255}) for t in (0,1)]
                    self.assertEqual(points,expected)
                    # Full independent scoring-summary loop, one ring entry.
                    m.set(m.SPOT,0);m.set(m.SPOT+4,0)
                    m.run(0xD62E0,(0,128,m.SPOT,m.SPOT+4),{UC_X86_REG_EAX:127})
                    self.assertEqual([m.get(m.SPOT),m.get(m.SPOT+4)],expected)

    def test_all_retail_history_outcomes_and_subtypes_unchanged(self):
        for outcome in range(8):
            for subtype in range(5):
                old,new=Machine(self.retail),Machine(self.patched)
                for m in (old,new):m.set(patch.DRIVE_RING,(outcome<<26)|(subtype<<29))
                for team in (0,1):
                    regs={UC_X86_REG_ECX:team,UC_X86_REG_EDX:0}
                    self.assertEqual(new.run(0x250360,registers=regs),old.run(0x250360,registers=regs))

    def test_safety_classifiers_keep_impetus_and_touchback_distinctions(self):
        for payload, enabled in ((self.retail,False),(self.patched,True)):
            for same_team in (False,True):
                for qualifies in (False,True):
                    m=Machine(payload)
                    runner=m.PLAYER[1]
                    m.set(0xE60280,m.TEAM[1])
                    m.float(m.SPOT+8,5000)
                    m.set(m.CTX+0x1A0,runner if same_team else m.PLAYER[0])
                    m.set(m.CTX+0x150,int(qualifies))
                    # The same-team branch uses the body/end-zone rectangle
                    # classifier. Its call is the explicit geometry boundary.
                    m.stub(0x158010,int(qualifies))
                    m.stub(0x13A350)
                    m.stub(0x1D0140)
                    result=m.run(0xB7610,(m.SPOT,1),{UC_X86_REG_ECX:runner,UC_X86_REG_EDX:runner})
                    self.assertEqual(bool(result),enabled and qualifies)
                    self.assertEqual(m.get(m.CTX+0x178),2 if enabled and qualifies else 0)
                    self.assertEqual(m.reg(UC_X86_REG_ESP),m.STACK+12)

    def test_loose_and_possessed_out_safety_then_kickoff(self):
        for possessed in (False,True):
            for touchback in (False,True):
                m=Machine(self.modern)
                m.set(0xE5FF80,1)
                m.set(0xE60280,m.TEAM[1])
                m.set(0xE60284,m.TEAM[0])
                m.set(0xE602C0,2 if possessed else 3)
                m.float(m.TRANSFORM+8,6000 if not touchback else -6000)
                m.float(m.PLAYER[1]+0x338,5000)
                m.stub(0x20D2C0)
                m.stub(0x13A350)
                m.stub(0x1D0140)
                m.stub(0xB7110,0)
                m.stub(0xB6760,int(touchback))
                m.stub(0xA1A20,pop=4)
                m.stub(0xA0390,action=lambda m:m.set(0xE602B8,18))
                m.run(0xB7BB0,registers={UC_X86_REG_ECX:m.BALL})
                self.assertEqual(m.get(m.CTX+0x178),0 if touchback else 2,(possessed,touchback))
                self.assertEqual(m.get(0xE602B8),18)
                if not touchback:
                    m.descriptor(2,0)
                    m.run(0x22E4D0,registers={UC_X86_REG_ECX:m.RECORD,UC_X86_REG_EDX:1})
                    self.assertEqual(m.get(m.get(m.TEAM[0]+8)),1)
                    self.assertEqual(m.get(0xE60280),m.TEAM[0])
                    self.assertEqual(m.get(patch.PHASE),2)

    def test_real_dead_ball_coordinator_is_once_per_frame(self):
        m=Machine(self.patched)
        m.set(0xE6028C,m.SPOT)
        m.set(0xB71D10,17)
        for va in (0x874E0,0xFEF50,0x9FC30,0x189080,0x1CEEE0,0x1E8480,
                   0xFEA90,0xB7330,0xFC6E0,0x119760,0x1195F0,0x14F9E0,
                   0xAF260,0xB6340,0xB6180):
            m.stub(va,0)
        m.stub(0x12D610,pop=4)
        m.run(0xA0390,registers={UC_X86_REG_ECX:1})
        self.assertEqual(m.get(0xE602B8),18)
        self.assertEqual(m.get(0xE602C0),1)
        calls=list(m.calls)
        m.run(0xA0390,registers={UC_X86_REG_ECX:1})
        self.assertEqual(m.calls,calls)

    def test_blocked_pat_loose_out_uses_safety_before_recovery(self):
        for original in (0, 1):
            for blocked in (False, True):
                for own_end in (False, True):
                    m = Machine(self.patched)
                    defender = 1 - original
                    m.set(0xE5FF80, 1)
                    m.set(0xE60280, m.TEAM[original])
                    m.set(0xE60284, m.TEAM[defender])
                    m.set(patch.ORIGINAL_TEAM, m.TEAM[original])
                    m.set(0xE602C0, 3)
                    m.set(m.BALL, 0)
                    m.set(m.CTX + 0x134, 1)
                    m.set(m.CTX + 0x1D0, m.PLAYER[original])
                    m.set(m.CTX + 0x1A8, m.PLAYER[original])  # kick supplied the impetus
                    m.set(m.CTX + 0x194, m.PLAYER[defender] if blocked else 0)
                    # Team zero advances toward positive z; an own-end exit
                    # is negative for it and positive for team one.
                    m.float(m.TRANSFORM + 8, 6000 * (-1 if original == 0 else 1)
                            * (1 if own_end else -1))
                    for va in (0x20D2C0, 0x13A350, 0x1D0140, 0xA1BA0):
                        m.stub(va)
                    m.stub(0xA1A20, pop=4)
                    m.stub(0xA0390, action=lambda m:m.set(0xE602B8, 18))
                    m.run(0xB7BB0, registers={UC_X86_REG_ECX:m.BALL})
                    safety = blocked and own_end
                    self.assertEqual(m.get(m.CTX + 0x178), 2 if safety else 0,
                                     (original, blocked, own_end))
                    self.assertEqual(m.get(0xE602B8), 18)
                    if safety:
                        self.assertEqual(m.get(m.CTX + 0x188), m.TEAM[defender])
                        m.descriptor(2, defender)
                        m.run(0x22E4D0, registers={UC_X86_REG_ECX:m.RECORD,
                                                  UC_X86_REG_EDX:1})
                        self.assertEqual(m.get(m.get(m.TEAM[defender] + 8)), 1)
                        self.assertEqual(m.get(0xE60280), m.TEAM[original])

    def test_play_by_play_uses_distinct_utf16_suffixes(self):
        for subtype, text in ((2,". 2 PTS!"),(5,". Defensive two-point return"),
                              (6,". Safety on try (+1)"),(7,". Safety on try (+1)")):
            m=Machine(self.patched)
            m.run(0xBD5BE,registers={UC_X86_REG_EAX:subtype},stop=0xBD606)
            pointer=m.reg(UC_X86_REG_EDX)
            raw=bytes(m.u.mem_read(pointer,2*(len(text)+1)))
            self.assertEqual(raw.decode("utf-16-le"),text+"\0")
            # Execute the retail wide-character append routine too.
            m.run(0x30DB0,registers={UC_X86_REG_ECX:m.SPOT,UC_X86_REG_EDX:pointer})
            self.assertEqual(bytes(m.u.mem_read(m.SPOT,len(raw))),raw)

    def test_cpu_try_acquisition_chooses_return_not_kick_touchback_wait(self):
        # The existing return-vs-wait selector restricts its wait branch to
        # phase 1/2. Phase 3 goes to the ordinary possession/return transition.
        # This is a selector proof, not a complete CPU pursuit/animation test.
        for team in (0,1):
            for z in (-5500,-4800,0,4800,5500):
                m=Machine(self.patched)
                m.float(m.PLAYER[team]+0x338,z)
                m.set(m.CTX+0x150,0)
                m.set(m.CTX+0x18C,m.TEAM[1-team])
                self.assertEqual(m.run(0x2EE110,registers={UC_X86_REG_ECX:m.PLAYER[team]}),1)

    def test_added_builder_preserves_x87_sse_stack_and_retained_outputs(self):
        # Compare the added descriptor wrapper with the displaced builder on
        # both the try and ordinary paths. x87 status as well as TOP/registers
        # and XMM are checked; the next-play record is the intentional delta.
        for phase in (3,4):
            old,new=Machine(self.patched),Machine(self.patched)
            code,data=patch._sites(self.patched)
            _,labels=patch.code_for(code["va"],data["va"])
            results=[]
            for m,start in ((old,0x22E050),(new,labels["descriptor"])):
                m.set(patch.PHASE,phase)
                m.set(m.CTX+0x178,1)
                m.set(m.CTX+0x19C,m.PLAYER[1])
                m.set(m.CTX+0x188,m.TEAM[1])
                m.reg(UC_X86_REG_FPCW,0x37f)
                # Nonempty x87 stack, including live values below TOP. An
                # empty-stack control-word check would miss clobbered data.
                m.u.mem_write(m.STOP + 0x200, bytes.fromhex("d9e8 d9eb d9ea c3"))
                m.run(m.STOP + 0x200)
                for i in range(8):
                    m.reg(UC_X86_REG_XMM0 + i, 0x123456789abcdef + i)
                m.run(start,registers={UC_X86_REG_ESI:m.RECORD,UC_X86_REG_EBX:0x1234,UC_X86_REG_EDI:0x5678})
                registers = (UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX,
                             UC_X86_REG_EBX, UC_X86_REG_ESI, UC_X86_REG_EDI,
                             UC_X86_REG_EFLAGS, UC_X86_REG_FPSW, UC_X86_REG_FPCW,
                             UC_X86_REG_FPTAG, UC_X86_REG_ESP)
                registers += tuple(UC_X86_REG_FP0 + i for i in range(8))
                registers += tuple(UC_X86_REG_XMM0 + i for i in range(8))
                results.append(tuple(m.reg(r) for r in registers))
            self.assertEqual(*results)

    def test_cpu_carrier_transition_selects_return_callback_and_direction(self):
        for team in (0,1):
            for cpu in (False,True):
                for payload,installed in ((self.retail,False),(self.patched,True)):
                    m=Machine(payload)
                    player=m.PLAYER[team]
                    plan=0x3030000
                    m.set(patch.ORIGINAL_TEAM,m.TEAM[1-team])
                    m.set(m.BALL,player)
                    m.set(player,1)
                    m.set(player+0xC,player+0x400)
                    m.set(player+0x400,-1 if cpu else 0)
                    m.set(player+0x20,player+0x500)
                    m.set(player+0x810,plan)
                    m.float(player+0x338,-5500 if team==0 else 5500)
                    m.stub(0x2C9AF0,plan)
                    m.stub(0x2C9AB0)
                    m.stub(0xAF510)
                    m.stub(0x1AE370,pop=4)
                    # Proximity helper returns 0.0 in ST0, making the retail
                    # end-zone wait condition true. All decision code is real.
                    m.u.mem_write(m.STOP+0x100,bytes.fromhex("d9ee c3"))
                    m.redirects[0x2E1E30]=m.STOP+0x100
                    m.run(0x2E36F0,registers={UC_X86_REG_ECX:player})
                    advancing=installed and cpu
                    self.assertEqual(m.get(plan),0x2E2DA0 if advancing else 0x2EE090)
                    if advancing:
                        self.assertEqual(m.get(plan+0x30),0 if team==0 else 0x8000)
                    self.assertEqual(m.reg(UC_X86_REG_ESP),m.STACK+4)

    def test_stat_commit_rebuilds_separate_conversion_line_without_double_count(self):
        m=Machine(self.patched)
        code,data=patch._sites(self.patched)
        m.set(0xE53800,130)
        # Return on an offensive TD, return on a defensive TD, ordinary 2PT,
        # and safety: only the first two enter the independent new category.
        m.set(patch.DRIVE_RING,(1<<26)|(5<<29))
        m.set(patch.DRIVE_RING+4,(6<<26)|(5<<29))
        m.set(patch.DRIVE_RING+8,(1<<26)|(2<<29))
        m.set(patch.DRIVE_RING+12,(1<<26)|(7<<29))
        for _ in range(2):
            m.set(m.STACK+52,m.STOP)
            m.run(0x1EEA96)
            stats=patch.read_runtime_stats(self.patched,m.u.mem_read)
            self.assertEqual(stats["label"],"Defensive two-point conversions")
            self.assertEqual(stats["teams"],[1,1])
            self.assertEqual(stats["points"],[2,2])
            self.assertTrue(stats["committed"])
            self.assertFalse(stats["persistent"])
        # A reset/rebuild with no drives clears the prior game's tally.
        m.set(0xE53800,-1)
        m.set(m.STACK+52,m.STOP)
        m.run(0x1EEA96)
        self.assertEqual(patch.read_runtime_stats(self.patched,m.u.mem_read)["teams"],[0,0])
        for addr,size in m.writes:
            self.assertTrue(m.STOP<=addr< m.STOP+0x40000 or data["va"]<=addr< data["va"]+data["size"],hex(addr))


if __name__ == "__main__":
    unittest.main()
