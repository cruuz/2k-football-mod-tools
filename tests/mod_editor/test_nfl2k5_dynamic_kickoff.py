"""Bounded execution of the installed hooks, never an emulator/GUI launch.

Public tests use a synthetic XBE. Private tests load the SHA-pinned executable,
execute the actual hook instructions and retail continuations, and protect
.text against runtime writes. Fixtures model engine objects; unrelated scene,
audio, and animation internals are explicit stubs. RNG values are controlled.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mod_editor.core import nfl2k5_dynamic_kickoff as dk
from mod_editor.core import nfl2k5_kick_rules as kr
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest, RETAIL_XBE_SHA256
from tools import nfl2k5_kickoff_alignment as ka

try:
    import unicorn as uni
    from unicorn import x86_const as x86
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
except ImportError:
    uni = None
    Cs = None

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)" / "default.xbe"
PRIVATE_REASON = f"private NFL 2K5 USA default.xbe required at {RETAIL}; no proprietary fixture is distributed"


def synthetic():
    """Only header geometry and hook pins, with a zero-filled stand-in cave."""
    buf = bytearray(0x300000)
    buf[:4] = b"XBEH"
    struct.pack_into("<I", buf, 0x104, 0x10000)
    struct.pack_into("<II", buf, 0x11C, 22, 0x10200)
    # Mirror the shared page around the writable gap, with small synthetic data.
    headers = ((0x16, 0x11000, 0x2FF000, 0x1000, 0x2FF000),
               (7, 0xA69000, 0x969, 0, 0), (7, 0xA69980, 0x100, 0, 0))
    for i, fields in enumerate(headers):
        struct.pack_into("<5I", buf, 0x200 + i * 56, *fields)
    for va, original in dk.HOOKS.values():
        buf[va - 0x10000:va - 0x10000 + len(original)] = original
    return bytes(buf)


class PatchTests(unittest.TestCase):
    def setUp(self):
        self.payload = synthetic()
        self.pin = patch.object(dk, "RETAIL_CAVE_SHA256", hashlib.sha256(bytes(dk.CAVE_SIZE)).hexdigest())
        self.pin.start()
        self.addCleanup(self.pin.stop)

    def test_apply_settings_idempotence_and_exact_write_set(self):
        self.assertEqual(dk.status(self.payload), "retail")
        settings = dict(touchback_yard=30, cpu_landing_probability=72,
                        cpu_target_yards=(2, 18), cpu_touchback_probability=83)
        out, receipt = dk.apply(self.payload, **settings)
        self.assertEqual(dk.read_settings(out), {"status": "applied", **settings})
        again, repeated = dk.apply(out, **settings)
        self.assertEqual(out, again)
        self.assertEqual(repeated["changed_bytes"], 0)
        self.assertEqual(receipt["sections_repinned"], [0])
        allowed = set(range(0x200 + 36, 0x200 + 56))
        for va, size in [(dk.CAVE_VA, dk.CAVE_SIZE)] + [(va, len(b)) for va, b in dk.HOOKS.values()]:
            allowed.update(range(va - 0x10000, va - 0x10000 + size))
        self.assertTrue(all(i in allowed for i, (a, b) in enumerate(zip(self.payload, out)) if a != b))
        self.assertEqual(_sections(out)[0].stored_digest, section_digest(out, _sections(out)[0]))
        with self.assertRaisesRegex(dk.DynamicKickoffError, "different settings"):
            dk.apply(out)

    def test_corruption_partial_application_and_read_only_storage_refused(self):
        out, _ = dk.apply(self.payload)
        for va, original in dk.HOOKS.values():
            for source in (self.payload, out):
                bad = bytearray(source)
                bad[va - 0x10000] ^= 1
                self.assertEqual(dk.status(bytes(bad)), "foreign")
        for va in (dk.CAVE_VA, dk.CAVE_VA + dk.CAVE_SIZE - 1):
            bad = bytearray(out)
            bad[va - 0x10000] ^= 1
            with self.assertRaises(dk.DynamicKickoffError):
                dk.apply(bytes(bad))
        bad = bytearray(self.payload)
        struct.pack_into("<I", bad, 0x200 + 56, 6)
        self.assertEqual(dk.status(bytes(bad)), "foreign")
        for size in (0, 256, 0x300, 0x1000, len(out) // 2):
            self.assertEqual(dk.status(out[:size]), "foreign")

    def test_invalid_parameters(self):
        for settings in (dict(touchback_yard=20), dict(touchback_yard=True),
                         dict(cpu_landing_probability=float("nan")), dict(cpu_landing_probability=101),
                         dict(cpu_touchback_probability=-1), dict(cpu_target_yards=(0, 20)),
                         dict(cpu_target_yards=(15, 10)), dict(cpu_target_yards=(5.0, 15)),
                         dict(cpu_target_yards=None)):
            with self.subTest(settings=settings), self.assertRaises(dk.DynamicKickoffError):
                dk.apply(self.payload, **settings)


class Machine:
    CTX, KICK_TEAM, RECEIVE_TEAM = 0x2000000, 0x2001000, 0x2002000
    KICKER, RETURNER, COVERAGE, BLOCKER = 0x2004000, 0x2005000, 0x2006000, 0x2007000
    BALL, BALL_POS = 0x2010000, 0x2010100
    CONTACT = 0x2010200
    CLOCK, GAME, DESC, NODE, OPS = 0x2011000, 0x2012000, 0x2013000, 0x2014000, 0x2014100
    KICK_BOOK, RECEIVE_BOOK = 0x2015000, 0x2016000
    STACK, STOP, CALLBACK, COUNTER, SCALAR = 0x3028000, 0x3030000, 0x3030010, 0x3030100, 0x3030200

    def __init__(self, payload, direction=1, kick_yard=35, phase=2, onside=False,
                 human_kicker=False, human_returner=False, rolls=(0, 0, 0), state_va=None):
        self.uc = uni.Uc(uni.UC_ARCH_X86, uni.UC_MODE_32)
        self.uc.mem_map(0x10000, 0xFF0000)
        self.uc.mem_map(0x2000000, 0x20000)
        self.uc.mem_map(0x3020000, 0x20000)
        self.state_va = dk.FLAGS if state_va is None else state_va
        for sec in _sections(payload):
            if sec.virtual_address >= 0x1000000:
                self.uc.mem_map(sec.virtual_address & -4096, (sec.raw_size + 4095) & -4096)
            self.uc.mem_write(sec.virtual_address, payload[sec.raw_offset:sec.raw_offset + sec.raw_size])
            if sec.virtual_address >= 0x1000000:
                flags = struct.unpack_from("<I", payload, sec.header_offset)[0]
                perms = uni.UC_PROT_READ | (uni.UC_PROT_WRITE if flags & 1 else 0) | (uni.UC_PROT_EXEC if flags & 4 else 0)
                self.uc.mem_protect(sec.virtual_address & -4096, (sec.raw_size + 4095) & -4096, perms)
        self.uc.mem_protect(0x11000, 0x410000, uni.UC_PROT_READ | uni.UC_PROT_EXEC)
        self.direction = direction
        self.rolls = iter(rolls)
        self.calls = []
        self.fpu_stubs = {}
        self.stub_pops = {va: 0 for va in (
            0x874E0, 0xFEF50, 0x9FC30, 0x189080, 0x1CEEE0, 0x1E8480, 0xFEA90,
            0xB7330, 0xFC6E0, 0x119760, 0x1195F0, 0x14F9E0, 0xAF4F0, 0xAF260, 0xB6180,
            0x217F90)}
        self.stub_pops.update({0x12D610: 4, 0x31BEB0: 12})
        self.uc.hook_add(uni.UC_HOOK_CODE, self._hook)
        for va, value in ((dk.CTX, self.CTX), (dk.BALL, self.BALL), (dk.PHASE, phase),
                          (dk.PLAY_STATE, 14), (dk.POSSESSION, self.KICK_TEAM),
                          (0xE60284, self.RECEIVE_TEAM), (0xE60288, self.KICK_TEAM),
                          (0xE6028C, self.CLOCK), (0xE602D4, self.GAME), (0xE602C0, 3),
                          (0xE5FF80, 4), (0xB71D10, 1), (self.CTX + 0x134, 1),
                          (self.CTX + 0x1C4, self.KICKER), (self.BALL + 0x14, self.BALL_POS)):
            self.put(va, value)
        self.f32(0xB71D0C, 1 / 60)
        self.f32(self.CTX + 0x18, -direction * (50 - kick_yard) * 91.44)
        for team, opponent, sign in ((self.KICK_TEAM, self.RECEIVE_TEAM, direction),
                                     (self.RECEIVE_TEAM, self.KICK_TEAM, -direction)):
            self.put(team, opponent)
            self.put(team + 8, team + 0x100)
            self.put(team + 0x10C, team + 0x200)
            self.f32(team + 0x204, sign)
        for team, book, kind, xz in (
            (self.KICK_TEAM, self.KICK_BOOK, 10 if onside else 8, ka.kickoff_xz_2026()),
            (self.RECEIVE_TEAM, self.RECEIVE_BOOK, 11 if onside else 9, ka.KICK_RETURN_XZ_2026),
        ):
            self.put(team + 0xC, team + 0x300)
            self.put(team + 0x308, book + 0x200)
            self.put(team + 0x20, book)
            self.put(book + 0x34, 1)  # formation count, used by E0670
            self.put(book + 0x44, book + 0x200)
            self.put(book + 0x204, kind << 8)
            slots = bytearray(ka.SLOTS_SIZE)
            for slot in range(11): slots[slot * 14 + 1] = 1  # retail stance
            self.uc.mem_write(book + 0x21A, ka.with_xz(slots, xz))
        for player, team, slot, human in ((self.KICKER, self.KICK_TEAM, 0, human_kicker),
                                          (self.RETURNER, self.RECEIVE_TEAM, 0, human_returner),
                                          (self.COVERAGE, self.KICK_TEAM, 1, False),
                                          (self.BLOCKER, self.RECEIVE_TEAM, 2, False)):
            self.put(player + 0x1C, 1)
            self.f32(player + 8, 1)
            self.put(player + 0x38, team)
            self.put(player + 0x3C, player + 0xF00)
            self.uc.mem_write(player + 0x2C, bytes([2 if player == self.KICKER else 4 if player == self.RETURNER else 15]))
            self.uc.mem_write(player + 0x2E, bytes([slot]))
            self.put(player + 0xC, player + 0x100)
            self.put(player + 0x100, 0 if human else 0xFFFFFFFF)
            self.put(player + 0x20, player + 0x200)
            self.put(player + 0x61C, self.NODE)
            self.put(player + 0x10, player + 0x900)
            self.put(player + 0x18, player + 0xB00)
            self.put(player + 0x14, player + 0xC00)
            self.put(player + 0x24, player + 0xE00)
            self.put(player + 0x904, self.DESC)
        # Execute the actual 1B8CA0 -> 1B8C40 -> 1B81A0 opcode reader.
        state = self.KICKER + 0x200 + 0x41C
        self.put(state, self.NODE)
        self.put(self.NODE + 4, self.OPS)
        self.uc.mem_write(self.OPS, b"\x08")
        self.f32(state + 0x14, 2 if onside else 0)
        self.put(self.DESC + 8, self.CALLBACK)
        self.uc.mem_write(self.CALLBACK, bytes.fromhex("ff05") + struct.pack("<I", self.COUNTER) + b"\xc3")
        self.position(0, self.direction * -1371.6)

    def put(self, va, value): self.uc.mem_write(va, struct.pack("<I", value & 0xFFFFFFFF))
    def get(self, va): return struct.unpack("<I", self.uc.mem_read(va, 4))[0]
    def f32(self, va, value): self.uc.mem_write(va, struct.pack("<f", value))
    def readf(self, va): return struct.unpack("<f", self.uc.mem_read(va, 4))[0]
    def flags(self): return self.uc.mem_read(self.state_va, 1)[0]
    def position(self, x, z, holder=0):
        self.put(self.BALL, holder)
        self.uc.mem_write(self.BALL_POS, struct.pack("<4f", x, 100.0, z, 1.0))
        self.uc.mem_write(self.CONTACT, struct.pack("<4f", x, 8.49, z, 1.0))

    def _ret(self, pops=0):
        sp = self.uc.reg_read(x86.UC_X86_REG_ESP)
        target = self.get(sp)
        self.uc.reg_write(x86.UC_X86_REG_ESP, sp + 4 + pops)
        self.uc.reg_write(x86.UC_X86_REG_EIP, target)

    def _hook(self, _uc, address, _size, _data):
        if address in self.fpu_stubs:
            self.calls.append(address)
            # A bounded attribute fixture: return ST0=1, with the real ABI.
            self.uc.mem_write(self.CALLBACK + 0x20, b"\xd9\xe8\xc2" + struct.pack("<H", self.fpu_stubs[address]))
            self.uc.reg_write(x86.UC_X86_REG_EIP, self.CALLBACK + 0x20)
        elif address == dk.RAND:
            self.calls.append(address)
            self.uc.reg_write(x86.UC_X86_REG_EAX, next(self.rolls, 0))
            self._ret()
        elif address in self.stub_pops:
            self.calls.append(address)
            if address == 0x31BEB0:
                self.put(self.COUNTER, self.get(self.COUNTER) + 1)
            self.uc.reg_write(x86.UC_X86_REG_EAX, 0)
            self._ret(self.stub_pops[address])

    def run(self, address, *, stop=None, ecx=0, edx=0, esi=0, args=()):
        for reg, value in ((x86.UC_X86_REG_ESP, self.STACK), (x86.UC_X86_REG_ECX, ecx),
                           (x86.UC_X86_REG_EDX, edx), (x86.UC_X86_REG_ESI, esi)):
            self.uc.reg_write(reg, value)
        self.put(self.STACK, self.STOP)
        for i, arg in enumerate(args): self.put(self.STACK + 4 + 4 * i, arg)
        target = self.STOP if stop is None else stop
        self.uc.emu_start(address, target, count=30_000)
        if self.uc.reg_read(x86.UC_X86_REG_EIP) != target:
            raise AssertionError(f"instruction budget exhausted at {self.uc.reg_read(x86.UC_X86_REG_EIP):#x}")

    def launch(self):
        va, original = dk.HOOKS["launch"]
        self.run(va, stop=va + len(original), args=(0, self.KICKER))

    def event(self, name):
        va, original = dk.HOOKS[name]
        self.run(va, stop=va + len(original), ecx=self.BALL if name == "ground" else self.RETURNER,
                 edx=self.CONTACT)

    def spot(self, touchback=True):
        self.f32(self.CTX + 0x17C, self.direction if touchback else 0)
        self.run(0xB6340)
        return 50 - abs(self.readf(self.CTX + 0x38)) / 91.44


@unittest.skipUnless(RETAIL.is_file() and uni is not None and Cs is not None,
                     PRIVATE_REASON + "; unicorn and capstone also required")
class RetailExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = RETAIL.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_XBE_SHA256:
            raise unittest.SkipTest("private XBE does not match the NFL 2K5 USA retail SHA-256")
        cls.base, _ = kr.apply(cls.retail)
        cls.payload, _ = dk.apply(cls.base)

    def machine(self, settings=None, **kwargs):
        payload = dk.apply(self.base, **settings)[0] if settings else self.payload
        m = Machine(payload, **kwargs)
        m.launch()
        return m

    def test_composition_both_orders_and_untouched_kick_rules_recognition(self):
        first, _ = dk.apply(self.retail)
        opposite, _ = kr.apply(first)
        self.assertEqual(opposite, self.payload)
        self.assertEqual(kr.status(opposite), "applied")
        self.assertEqual(dk.status(opposite), "applied")
        self.assertEqual(dk.apply(opposite)[0], opposite)

    def test_cave_entry_and_interior_and_writable_storage_have_no_retail_references(self):
        from tools.nfl2k5_dynamic_kickoff_audit import audit
        result = audit(RETAIL)
        self.assertEqual(result["cave"]["external_references"], [])
        self.assertEqual(result["storage"]["address_literals"], [])
        self.assertGreater(result["long_branch_candidates_checked"], 50_000)

    def test_each_hook_decodes_and_cave_control_flow_is_bounded(self):
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        md.detail = True
        code = dk.cave_bytes()
        insns = list(md.disasm(code, dk.CAVE_VA))
        self.assertEqual(sum(i.size for i in insns), len(code))
        starts = {i.address for i in insns}
        for i in insns:
            if i.mnemonic.startswith("j") or i.mnemonic == "call":
                target = i.operands[0].imm
                if dk.CAVE_VA <= target < dk.CAVE_VA + dk.CAVE_SIZE:
                    self.assertIn(target, starts)
        for name, (va, original) in dk.HOOKS.items():
            self.assertEqual(sum(i.size for i in md.disasm(original, va)), len(original), name)

    def test_hold_releases_on_contact_for_both_directions_and_player_roles(self):
        for direction in (-1, 1):
            for event in ("ground", "touch"):
                with self.subTest(direction=direction, event=event):
                    m = self.machine(direction=direction)
                    self.assertEqual(m.flags() & 7, dk.NONE)
                    for who in (m.COVERAGE, m.BLOCKER):
                        before = bytes(m.uc.mem_read(who, 0x1000))
                        m.run(dk.HOOKS["plan"][0], ecx=who)
                        m.run(dk.HOOKS["motion"][0], esi=who)
                        self.assertEqual(m.get(m.COUNTER), 0)
                        # The only mutation is the retail animation-updated flag.
                        expected = bytearray(before)
                        struct.pack_into("<I", expected, 0xC54, 1)
                        self.assertEqual(bytes(m.uc.mem_read(who, 0x1000)), expected)
                    for who in (m.KICKER, m.RETURNER):
                        old = m.get(m.COUNTER)
                        m.run(dk.HOOKS["plan"][0], ecx=who)
                        m.run(dk.HOOKS["motion"][0], esi=who)
                        self.assertEqual(m.get(m.COUNTER), old + 2)
                    # Passing arbitrary time does not release; only the event does.
                    m.f32(0xB71D0C, 20)
                    m.run(dk.HOOKS["plan"][0], ecx=m.COVERAGE)
                    self.assertEqual(m.flags() & 7, 0)
                    m.position(0, direction * 3657.6)
                    m.event(event)
                    self.assertEqual(m.flags() & 7, dk.LANDING)
                    old = m.get(m.COUNTER)
                    m.run(dk.HOOKS["plan"][0], ecx=m.COVERAGE)
                    self.assertEqual(m.get(m.COUNTER), old + 1)

    def test_retail_formation_reader_then_los_clamp_reproduces_and_fixes_coverage(self):
        # Execute retail type lookup, coordinate decoding, direction transform,
        # and target clamp. Only the unrelated heading/scene queries are stubs.
        for direction in (-1, 1):
            for payload, fixed in ((self.base, False), (self.payload, True)):
                m = Machine(payload, direction=direction)
                m.put(dk.PLAY_STATE, 12)
                m.fpu_stubs[0x187780] = 0
                m.stub_pops[0x136D40] = 0
                for slot, (x, z) in enumerate(ka.kickoff_xz_2026()):
                    with self.subTest(direction=direction, fixed=fixed, slot=slot):
                        who = m.KICKER if slot == 0 else m.COVERAGE
                        m.uc.mem_write(who + 0x2E, bytes([slot]))
                        tee = m.readf(m.CTX + 0x18)
                        # 154EC0's initial placement uses this type-8 book lookup.
                        m.run(0x18B210, ecx=who, edx=m.CONTACT, args=(m.SCALAR,))
                        self.assertAlmostEqual(m.readf(m.CONTACT), direction * x, places=3)
                        self.assertAlmostEqual(m.readf(m.CONTACT + 8), tee + direction * z, places=3)
                        # The later selected-play target passes through 183F60.
                        m.run(0x1840B0, ecx=who, edx=m.CONTACT)
                        expected = tee + direction * z if fixed or slot == 0 else tee - direction * 94.5
                        self.assertAlmostEqual(m.readf(m.CONTACT + 8), expected, places=3)
                        if slot:
                            self.assertAlmostEqual(m.readf(m.CONTACT), direction * x, places=3)
                        args = (m.get(m.CONTACT), m.get(m.CONTACT + 8))
                        m.run(dk.HOOKS["position"][0], ecx=who, args=args)
                        self.assertAlmostEqual(m.readf(who + 0xB38), expected, places=3)
                        self.assertEqual(m.flags(), 0, "lineup must work before the launch latch")

    def test_receiving_slots_retain_setup_zone_and_deep_coordinates(self):
        for direction in (-1, 1):
            m = Machine(self.payload, direction=direction)
            m.put(dk.PLAY_STATE, 12)
            m.stub_pops[0x136D40] = 0
            for slot, (x, z) in enumerate(ka.KICK_RETURN_XZ_2026):
                with self.subTest(direction=direction, slot=slot):
                    who = m.RETURNER if slot < 2 else m.BLOCKER
                    m.uc.mem_write(who + 0x2E, bytes([slot]))
                    for reader in (0x18B210, 0x1840B0):
                        m.run(reader, ecx=who, edx=m.CONTACT,
                              args=(m.SCALAR,) if reader == 0x18B210 else ())
                        self.assertAlmostEqual(m.readf(m.CONTACT), direction * x, places=3)
                        self.assertAlmostEqual(m.readf(m.CONTACT + 8),
                                               m.readf(m.CTX + 0x18) + direction * z, places=3)

    def test_all_private_books_feed_the_actual_lineup_and_target_readers(self):
        packs = RETAIL.parent / "vc_53450030"
        if not packs.is_dir():
            self.skipTest(f"private extracted PLAY packs required at {packs}; no books are distributed")
        with ka.recode.OuterImage(packs) as archive:
            books = ka._load(archive)
        names = {book.name for book, _refs in books}
        self.assertEqual(len(names), 36)
        self.assertTrue({"GEN", "reference", "Editor", "WCO"} <= names)
        self.assertNotIn("PRACTICE", names)
        for direction in (-1, 1):
            m = Machine(self.payload, direction=direction)
            m.put(dk.PLAY_STATE, 12)
            m.fpu_stubs[0x187780] = 0
            m.stub_pops[0x136D40] = 0
            forms = 0x2020000
            m.uc.mem_map(forms, 0x10000)
            for book, refs in books:
                # Keep every real formation, in its real index order: E0B40
                # must find types 8/9, including GEN/reference/Editor.
                m.uc.mem_write(forms, book.body[ka.FORMATION_BASE:ka.FORMATION_BASE + 50 * ka.FORMATION_SIZE])
                for team, runtime_book, name, xz in (
                    (m.KICK_TEAM, m.KICK_BOOK, ka.KICKOFF_NAME, ka.kickoff_xz_2026()),
                    (m.RECEIVE_TEAM, m.RECEIVE_BOOK, ka.KICK_RETURN_NAME, ka.KICK_RETURN_XZ_2026),
                ):
                    ref = refs[name]
                    form = forms + ref.index * ka.FORMATION_SIZE
                    m.uc.mem_write(form + ka.SLOT_BASE, ka.with_xz(ref.slots, xz))
                    m.put(runtime_book + 0x34, 50)
                    m.put(runtime_book + 0x44, forms)
                    m.put(team + 0x308, form)
                for name, xz in ((ka.KICKOFF_NAME, ka.kickoff_xz_2026()),
                                 (ka.KICK_RETURN_NAME, ka.KICK_RETURN_XZ_2026)):
                    for slot, (x, z) in enumerate(xz):
                        with self.subTest(book=book.name, formation=name, direction=direction, slot=slot):
                            who = (m.KICKER if slot == 0 else m.COVERAGE) if name == ka.KICKOFF_NAME else m.BLOCKER
                            m.uc.mem_write(who + 0x2E, bytes([slot]))
                            for reader in (0x18B210, 0x1840B0):
                                m.run(reader, ecx=who, edx=m.CONTACT,
                                      args=(m.SCALAR,) if reader == 0x18B210 else ())
                                self.assertAlmostEqual(m.readf(m.CONTACT + 8),
                                                       m.readf(m.CTX + 0x18) + direction * z, places=3)
                                if slot or name != ka.KICKOFF_NAME or reader == 0x18B210:
                                    self.assertAlmostEqual(m.readf(m.CONTACT), direction * x, places=3)

    def test_ready_and_approach_hold_before_launch_without_stalling_lineup(self):
        for direction in (-1, 1):
            for event in ("ground", "touch"):
                m = Machine(self.payload, direction=direction)
                m.put(m.CTX + 0x1C4, 0)  # last-kicker pointer is not available yet
                m.put(dk.PLAY_STATE, 12)
                m.run(0x158C90)  # neither team is ready; keep lining up
                self.assertEqual(m.get(dk.PLAY_STATE), 12)
                m.put(m.KICK_TEAM + 0x324, 2)
                m.put(m.RECEIVE_TEAM + 0x324, 2)
                m.put(0xE5FC28, m.KICK_TEAM + 0x400)
                m.put(0xE5FC68, m.RECEIVE_TEAM + 0x400)
                m.stub_pops[0xB45A0] = 0  # unrelated game-record bookkeeping
                for who, slots in ((m.COVERAGE, range(1, 11)), (m.BLOCKER, range(2, 11))):
                    for slot in slots:
                        with self.subTest(direction=direction, event=event, who=who, slot=slot):
                            m.uc.mem_write(who + 0x2E, bytes([slot]))
                            m.put(dk.PLAY_STATE, 12)
                            old = m.get(m.COUNTER)
                            m.run(dk.HOOKS["plan"][0], ecx=who)
                            self.assertEqual(m.get(m.COUNTER), old + 1)
                            xz = ka.kickoff_xz_2026()[slot] if who == m.COVERAGE else ka.KICK_RETURN_XZ_2026[slot]
                            args = tuple(struct.unpack("<2I", struct.pack("<2f", direction * xz[0],
                                         m.readf(m.CTX + 0x18) + direction * xz[1])))
                            m.run(dk.HOOKS["position"][0], ecx=who, args=args)
                            m.put(0xE60268, who)
                            m.run(0x28DFE0)
                            previous = bytes(m.uc.mem_read(who + 0xB30, 48))
                            for state in (13, 14):
                                if state == 13:
                                    m.run(0x158C90)  # actual readiness queries and state-13 write
                                else:
                                    m.run(0xB6F30, stop=0xB6FBD)  # actual state-14 transition
                                self.assertEqual(m.get(dk.PLAY_STATE), state)
                                old = m.get(m.COUNTER)
                                m.run(dk.HOOKS["plan"][0], ecx=who)
                                m.run(dk.HOOKS["motion"][0], esi=who)
                                m.uc.mem_write(who + 0xB30, bytes(48))
                                m.run(dk.HOOKS["position"][0], ecx=who, args=(0, 0))
                                self.assertEqual(m.get(m.COUNTER), old)
                                self.assertEqual(bytes(m.uc.mem_read(who + 0xB30, 48)), previous)
                                self.assertEqual(m.flags(), 0)
                for who, slot in ((m.KICKER, 0), (m.RETURNER, 0), (m.RETURNER, 1)):
                    m.uc.mem_write(who + 0x2E, bytes([slot]))
                    old = m.get(m.COUNTER)
                    m.run(dk.HOOKS["plan"][0], ecx=who)
                    self.assertEqual(m.get(m.COUNTER), old + 1)
                m.put(m.CTX + 0x1C4, m.KICKER)
                m.launch()
                m.position(0, direction * 3600)
                m.event(event)
                for who in (m.COVERAGE, m.BLOCKER):
                    old = m.get(m.COUNTER)
                    m.run(dk.HOOKS["plan"][0], ecx=who)
                    self.assertEqual(m.get(m.COUNTER), old + 1)

    def test_lineup_exception_is_scoped_to_normal_kickoff_coverage(self):
        for phase, kind, who_name in ((1, 8, "COVERAGE"), (4, 8, "COVERAGE"),
                                      (2, 10, "COVERAGE"), (2, 8, "KICKER")):
            outputs = []
            for payload in (self.base, self.payload):
                m = Machine(payload, phase=phase, onside=kind == 10)
                who = getattr(m, who_name)
                m.f32(m.CONTACT, 1000)
                m.f32(m.CONTACT + 8, 914.4)  # force the retail clamp to run
                m.run(0x183F60, ecx=who, edx=m.CONTACT)
                outputs.append(bytes(m.uc.mem_read(m.CONTACT, 16)))
            self.assertEqual(outputs[0], outputs[1], (phase, kind, who_name))

    def test_first_contact_and_touchback_spots_2024_2025(self):
        for direction in (-1, 1):
            for tb in (30, 35):
                for event in ("ground", "touch"):
                    for landing_first in (False, True):
                        with self.subTest(direction=direction, tb=tb, event=event, landing_first=landing_first):
                            m = self.machine(settings=dict(touchback_yard=tb), direction=direction)
                            if landing_first:
                                m.position(0, direction * 3657.6)
                                m.event(event)
                            m.position(0, direction * 4800)
                            m.event(event)
                            self.assertEqual(m.flags() & 7, dk.LANDING if landing_first else dk.END_ZONE)
                            self.assertAlmostEqual(m.spot(), 20 if landing_first else tb, places=4)
                            self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_ESP), m.STACK + 4)

    def test_short_out_of_bounds_and_end_line_execute_retail_whistle_and_spot(self):
        for direction in (-1, 1):
            for name, x, z, event, first, spot in (
                ("short", 0, 2500, "ground", dk.SHORT, 40),
                ("sideline", 2500, 3500, "ground", dk.OUT, 40),
                ("out_in_flight", 2500, 3500, "dead", dk.OUT, 40),
                ("through_end", 0, 5600, "dead", dk.END_ZONE, 35),
            ):
                with self.subTest(direction=direction, case=name):
                    m = self.machine(direction=direction)
                    m.position(x, direction * z)
                    if event == "dead": m.run(dk.HOOKS[event][0], ecx=m.BALL)
                    else: m.event(event)
                    self.assertEqual(m.flags() & 7, first)
                    self.assertEqual(m.get(dk.PLAY_STATE), 0x12)
                    self.assertAlmostEqual(50 - abs(m.readf(m.CTX + 0x38)) / 91.44, spot, places=4)

    def test_cpu_and_human_returner_and_possession_changes(self):
        for direction in (-1, 1):
            for human in (False, True):
                for probability in (0, 100):
                    with self.subTest(direction=direction, human=human, probability=probability):
                        m = self.machine(settings=dict(cpu_touchback_probability=probability),
                                         direction=direction, human_returner=human)
                        m.position(0, direction * 4800, m.RETURNER)
                        m.event("touch")
                        m.run(dk.HOOKS["plan"][0], ecx=m.RETURNER)
                        self.assertEqual(m.get(dk.PLAY_STATE), 0x12 if probability and not human else 14)
                        if probability and not human:
                            self.assertAlmostEqual(m.spot(), 35, places=4)
        m = self.machine()
        m.position(0, 3600, m.RETURNER)
        m.event("touch")
        m.run(dk.HOOKS["plan"][0], ecx=m.RETURNER)
        self.assertTrue(m.flags() & dk.RETURNED)
        m.position(0, 4800, m.RETURNER)
        m.run(dk.HOOKS["plan"][0], ecx=m.RETURNER)
        self.assertEqual(m.get(dk.PLAY_STATE), 14)  # running back into own end zone is not a touchback
        m.position(0, 4800, m.KICKER)
        m.run(dk.HOOKS["plan"][0], ecx=m.KICKER)
        self.assertEqual(m.get(dk.PLAY_STATE), 14)

    def test_whistle_spot_reaches_real_next_play_record_and_receiving_possession(self):
        for direction in (-1, 1):
            for tb in (30, 35):
                for kind, first_z, final_z, expected in (
                    ("direct", None, 4800, tb), ("landing", 3600, 4800, 20),
                    ("short", None, 2500, 40), ("sideline", None, 3600, 40),
                ):
                    with self.subTest(direction=direction, tb=tb, kind=kind):
                        m = self.machine(settings=dict(touchback_yard=tb), direction=direction)
                        if first_z is not None:
                            m.position(0, direction * first_z)
                            m.event("ground")
                        m.position(2500 if kind == "sideline" else 0, direction * final_z)
                        if kind in ("short", "sideline"):
                            m.event("ground")
                        else:
                            m.run(dk.HOOKS["dead"][0], ecx=m.BALL)
                        self.assertEqual(m.get(dk.PLAY_STATE), 0x12)
                        record = 0x2016000
                        # Execute 22EB70's kickoff dispatch, 22EA20's ownership
                        # decision, 22DF90's team flip and 22E3A0's snap setup.
                        m.run(0x22EB70, ecx=record, edx=m.CTX + 0x30, args=(m.KICK_TEAM, 0))
                        self.assertEqual(m.get(record), 4)  # next play is scrimmage
                        self.assertEqual(m.get(record + 0x14), m.RECEIVE_TEAM)
                        self.assertEqual(m.get(record + 8), 1)  # first down
                        self.assertAlmostEqual(50 - abs(m.readf(record + 0x48)) / 91.44, expected, places=4)
                        self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_ESP), m.STACK + 12)

    def test_short_player_contact_finishes_after_bookkeeping_and_touchback_roll_boundary(self):
        for direction in (-1, 1):
            m = self.machine(direction=direction)
            m.position(0, direction * 2500, m.RETURNER)
            m.event("touch")
            self.assertEqual(m.flags() & 7, dk.SHORT)
            self.assertEqual(m.get(dk.PLAY_STATE), 14)
            m.run(dk.HOOKS["plan"][0], ecx=m.RETURNER)
            self.assertEqual(m.get(dk.PLAY_STATE), 0x12)
            self.assertAlmostEqual(50 - abs(m.readf(m.CTX + 0x38)) / 91.44, 40, places=4)
        for roll, downed in ((89, True), (90, False), (99, False)):
            m = self.machine(rolls=(roll, 0, 0))
            m.position(0, 4800, m.RETURNER)
            m.event("touch")
            m.run(dk.HOOKS["plan"][0], ecx=m.RETURNER)
            self.assertEqual(m.get(dk.PLAY_STATE), 0x12 if downed else 14)

    def test_safety_onside_scrimmage_and_reset_bypass(self):
        for phase, onside in ((1, False), (2, True), (4, False)):
            m = self.machine(phase=phase, onside=onside)
            self.assertEqual(m.flags(), 0)
            m.position(0, 4800)
            m.event("ground")
            m.event("touch")
            self.assertEqual(m.flags(), 0)
            m.run(dk.HOOKS["plan"][0], ecx=m.COVERAGE)
            m.run(dk.HOOKS["motion"][0], esi=m.COVERAGE)
            self.assertEqual(m.get(m.COUNTER), 2)
            self.assertAlmostEqual(m.spot(), 35 if phase == 2 else 20, places=4)
        m = self.machine()
        m.position(0, 3600)
        m.event("ground")
        va, original = dk.HOOKS["reset"]
        m.run(va, stop=va + len(original))
        self.assertEqual(m.flags(), 0)
        m.launch()
        self.assertEqual(m.flags() & 7, dk.NONE)

    def test_cpu_aim_human_bypass_probabilities_directions_and_penalty_spots(self):
        for direction in (-1, 1):
            for kick_yard in (20, 35, 40, 50):
                for human in (False, True):
                    with self.subTest(direction=direction, kick_yard=kick_yard, human=human):
                        m = self.machine(settings=dict(cpu_landing_probability=100, cpu_target_yards=(10, 10)),
                                         direction=direction, kick_yard=kick_yard, human_kicker=human)
                        original_spot = -direction * (50 - kick_yard) * 91.44
                        self.assertAlmostEqual(m.readf(dk.KICK_SPOT), original_spot, places=3)
                        m.f32(m.STACK + 0x38, 7777)
                        m.put(m.STACK + 0x14, 0x1800)
                        m.put(m.STACK + 0x18, 0x1111)
                        va, original = dk.HOOKS["aim"]
                        m.run(va, stop=va + len(original), esi=m.KICKER)
                        self.assertAlmostEqual(m.readf(m.STACK + 0x38),
                                               7777 if human else abs(direction * 40 * 91.44 - original_spot), places=3)
                        self.assertEqual(m.get(m.STACK + 0x14), 0x1800 if human else 0x2000)
                        self.assertEqual(m.get(m.STACK + 0x18), 0x1111 if human else 0x8000 if direction < 0 else 0)
                        self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_ESP), m.STACK - 4)
        for roll, changed in ((89, True), (90, False), (99, False)):
            m = self.machine(rolls=(0, roll, 10))
            m.f32(m.STACK + 0x38, 7777)
            va, original = dk.HOOKS["aim"]
            m.run(va, stop=va + len(original), esi=m.KICKER)
            self.assertEqual(m.readf(m.STACK + 0x38) != 7777, changed)

    def test_real_launch_range_solver_and_velocity_in_both_directions(self):
        """Real meter, curve lookups, square root, floor, launch and trig routines.

        Attribute getter is a fixture (1.0); ownership/scene notifications and
        1C9850's stadium-boundary adjustment are stubs. This proves the launch
        solve, not a complete physical flight under wind/collisions.
        """
        for direction in (-1, 1):
            for yard in (20, 35, 50):
                with self.subTest(direction=direction, kick_yard=yard):
                    m = self.machine(settings=dict(cpu_landing_probability=100, cpu_target_yards=(10, 10)),
                                     direction=direction, kick_yard=yard)
                    m.fpu_stubs[0x17B010] = 4
                    m.stub_pops.update({0xDDCD0: 0, 0xDDCA0: 0, 0x5D740: 4, 0x1C9850: 4, 0xA0210: 4})
                    m.put(0xB72714, 0)
                    m.put(0xB72718, 0x2000)
                    m.f32(0xB7271C, 1)
                    m.f32(0xB72728, 1)
                    m.position(0, m.readf(dk.KICK_SPOT))
                    m.run(0x222CA0, args=(0, m.KICKER))
                    vy, vz = m.readf(m.BALL_POS + 0x14), m.readf(m.BALL_POS + 0x18)
                    self.assertGreater(vy, 0)
                    self.assertGreater(vz * direction, 0)
                    projected_z = m.readf(m.BALL_POS + 8) + vz * 2 * vy / 980.6635131835938
                    # Retail trig uses interpolated lookup tables; allow two
                    # hundredths of a yard (1.83 cm), not exact analytic sin().
                    self.assertAlmostEqual(projected_z / direction / 91.44, 40, delta=0.02)
                    self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_ESP), m.STACK + 12)

    def test_loose_end_zone_cpu_downing_needs_ground_and_preserves_human_control(self):
        for direction in (-1, 1):
            for human in (False, True):
                for landing_first in (False, True):
                    with self.subTest(direction=direction, human=human, landing_first=landing_first):
                        m = self.machine(settings=dict(cpu_touchback_probability=100), direction=direction,
                                         human_returner=human)
                        m.position(0, direction * 4800)
                        m.run(dk.HOOKS["plan"][0], ecx=m.RETURNER)
                        self.assertEqual(m.get(dk.PLAY_STATE), 14)
                        self.assertEqual(m.flags() & 7, 0)
                        if landing_first:
                            m.position(0, direction * 3600)
                            m.event("ground")
                        m.position(0, direction * 4800)
                        m.event("ground")
                        m.run(dk.HOOKS["plan"][0], ecx=m.RETURNER)
                        self.assertEqual(m.get(dk.PLAY_STATE), 14 if human else 0x12)
                        self.assertAlmostEqual(m.spot(), 20 if landing_first else 35, places=4)

    def test_boundaries_history_normal_return_and_storage_neighbours(self):
        for direction in (-1, 1):
            for x, z, expected in ((0, 4572, dk.END_ZONE), (0, 4571.5, dk.LANDING),
                                    (0, 2743.2, dk.LANDING), (0, 2743, dk.SHORT),
                                    (2438.4, 3600, dk.OUT), (2438, 3600, dk.LANDING)):
                with self.subTest(direction=direction, x=x, z=z):
                    m = self.machine(direction=direction)
                    m.uc.mem_write(0xA69970, b"\x5a")
                    m.uc.mem_write(0xA69974, b"neighbours!!")
                    m.position(x, z * direction)
                    m.event("ground")
                    self.assertEqual(m.flags() & 7, expected)
                    self.assertEqual(bytes(m.uc.mem_read(0xA69970, 1)), b"\x5a")
                    self.assertEqual(bytes(m.uc.mem_read(0xA69974, 12)), b"neighbours!!")
            m = self.machine(direction=direction)
            m.position(0, direction * 3600)
            m.event("ground")
            m.position(0, direction * 2600)
            m.event("ground")  # backspin after a legal first landing is not a short kick
            self.assertEqual(m.get(dk.PLAY_STATE), 14)
            self.assertEqual(m.flags() & 7, dk.LANDING)
            m.position(2500, direction * 3600)
            m.event("ground")
            self.assertEqual(m.flags() & 7, dk.LANDING)
            self.assertAlmostEqual(m.spot(), 40, places=4)
            m = self.machine(direction=direction)
            m.position(0, direction * 3600, m.RETURNER)
            m.event("touch")
            m.run(dk.HOOKS["plan"][0], ecx=m.RETURNER)
            m.put(m.CTX + 0x170, 1)
            m.f32(m.CTX + 0x184, direction * 2100)
            self.assertAlmostEqual(m.spot(touchback=False), 50 - 2100 / 91.44, places=4)
            va, original = dk.HOOKS["dead"]
            m.position(2500, direction * 2100, m.RETURNER)
            m.run(va, stop=va + len(original), ecx=m.BALL)
            self.assertEqual(m.get(dk.PLAY_STATE), 14)

    def test_final_position_setter_restores_frame_snapshot_then_releases(self):
        for direction in (-1, 1):
            m = self.machine(direction=direction)
            m.put(0xE60268, m.COVERAGE)
            # A selected human coverage player is subject to the same rule.
            m.put(m.COVERAGE + 0x100, 0)
            transform = m.COVERAGE + 0xB00
            previous = struct.pack("<12f", 200, 0, direction * 914.4, 1, 2, 0, 3, 0, 0, 0, 0, 0)
            m.uc.mem_write(transform + 0x30, previous)
            m.run(0x28DFE0)  # execute the real per-frame snapshot, not a fabricated snapshot
            self.assertEqual(bytes(m.uc.mem_read(transform, 48)), previous)
            m.uc.mem_write(transform + 0x30, struct.pack("<12f", *([1234] * 12)))
            m.run(dk.HOOKS["position"][0], ecx=m.COVERAGE, args=(0, 0))
            self.assertEqual(bytes(m.uc.mem_read(transform + 0x30, 48)), previous)
            self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_ESP), m.STACK + 12)
            m.position(0, direction * 3600)
            m.event("ground")
            m.run(dk.HOOKS["position"][0], ecx=m.COVERAGE,
                  args=tuple(struct.unpack("<2I", struct.pack("<2f", 300, direction * 1000))))
            self.assertEqual(m.readf(transform + 0x30), 300)
            self.assertEqual(m.readf(transform + 0x38), direction * 1000)


if __name__ == "__main__":
    unittest.main()
