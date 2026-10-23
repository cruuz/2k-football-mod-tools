"""Real USA staging, featured-player lookup, replay getter and record swaps.

No lookup/swap routine is mocked. Synthetic team and recorded-event data
exercise stale source order and a prior native record swap. This is not a
replay of the stream save, a rendered highlight or a full game boot.
NFL2K5_SC2_XBE optionally repeats the native witnesses on an integrated XBE.
"""
from pathlib import Path
import os
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import mod_build as build
from mod_editor.core import nfl2k5_build_settings as settings
from mod_editor.core import nfl2k5_sportscenter_lineup as sc
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe

try:
    import unicorn as uc
    from unicorn import x86_const as r
except ImportError:
    uc = r = None


class WriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = retail_xbe()

    def test_exact_extent_replay_digests_and_no_allocator_request(self):
        out, receipt = sc.apply(self.base)
        self.assertEqual(sc.status(self.base), "retail")
        self.assertEqual(sc.status(out), "applied")
        self.assertEqual(len(out), len(self.base))
        self.assertEqual(len(sc.code()), sc.SIZE)
        self.assertEqual(sc.REQUESTS, ())
        self.assertEqual(receipt["new_cave_bytes"], 0)
        self.assertFalse(receipt["runtime_witnessed"])
        image = XbeImage(out)
        spans = [(image.offset(sc.VA), image.offset(sc.VA) + sc.SIZE)]
        for section in _sections(out):
            self.assertEqual(section.stored_digest, section_digest(out, section))
            spans.append((section.header_offset + 36, section.header_offset + 56))
        self.assertTrue(all(any(a <= i < b for a, b in spans)
                            for i, (a, b) in enumerate(zip(self.base, out)) if a != b))
        again, replay = sc.apply(out)
        self.assertEqual(again, out)
        self.assertEqual(replay["changed_bytes"], 0)

    def test_foreign_lookup_callers_and_truncations_refuse(self):
        out = sc.apply(self.base)[0]
        for payload in (self.base, out):
            for va in (sc.VA, sc.VA + sc.SIZE - 1, *(row[0] for row in sc.GUARDS)):
                data = bytearray(payload)
                data[XbeImage(payload).offset(va)] ^= 0x40
                self.assertEqual(sc.status(bytes(data)), "foreign", hex(va))
                with self.assertRaises(ValueError):
                    sc.apply(bytes(data))
        for payload in (b"", self.base[:4096]):
            self.assertEqual(sc.status(payload), "foreign")
            with self.assertRaises(ValueError):
                sc.apply(payload)

    def test_manifest_records_the_complete_existing_function(self):
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        out, receipt = sc.apply(self.base)
        recorder = Recorder(self.base)
        recorder.observe(sc, "apply", self.base, out, receipt)
        self.assertTrue(any(row["owner"] == sc.OWNER
                            and int(row["start"], 0) == sc.VA
                            and int(row["end"], 0) == sc.VA + sc.SIZE
                            for row in recorder.spans))

    def test_studio_writer_preflight_inspect_recipe_and_off_switch(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "default.xbe"
            source.write_bytes(self.base)
            target = Path(directory) / "built.xbe"
            full = build.build(build.BuildPlan(source, target, sportscenter_lineup=True))
            self.assertEqual(target.read_bytes(), sc.apply(self.base)[0])
            self.assertEqual(full["result"]["sportscenter_lineup"], "applied")
            plan = build.BuildPlan(source, source, sportscenter_lineup=True)
            receipt = {"steps": [], "result": {}}
            build._sportscenter_lineup_preflight(source, lambda *_: None)
            build._apply_sportscenter_lineup(plan, source, receipt, lambda *_: None)
            self.assertEqual(source.read_bytes(), sc.apply(self.base)[0])
            self.assertEqual(receipt["result"]["sportscenter_lineup"], "applied")
            self.assertEqual(receipt["steps"][0]["owner"], sc.OWNER)
            self.assertTrue(plan.to_recipe()["sportscenter_lineup"])
            self.assertEqual(build.inspect(source)["sportscenter_lineup"], "applied")
            plan.sportscenter_lineup = False
            with patch.object(build, "_write_xbe_bytes") as write:
                build._apply_sportscenter_lineup(plan, source, receipt, lambda *_: None)
            write.assert_not_called()
            data = bytearray(self.base)
            data[XbeImage(self.base).offset(sc.VA)] ^= 1
            source.write_bytes(data)
            with self.assertRaises(ValueError):
                build._sportscenter_lineup_preflight(source, lambda *_: None)


class SettingsTests(unittest.TestCase):
    def test_default_off_all_softdrink_presets_on_and_project_roundtrip(self):
        self.assertFalse(build.BuildPlan(Path("in.xbe"), Path("out.xbe")).sportscenter_lineup)
        self.assertIn("sportscenter_lineup", settings.FEATURE_KEYS)
        for name, preset in build.PRESETS.items():
            self.assertTrue(preset["sportscenter_lineup"], name)
        normalized = settings.build_settings({"sportscenter_lineup": True})
        self.assertTrue(normalized["sportscenter_lineup"])


class Machine:
    RAW = (0x2000000, 0x2001000)
    RECORDS = (0x2010000, 0x2020000)
    GAME = (0xB30864, 0xB30A58)
    COPIES = (0xB30C4C, 0xB321A0)
    STACK, STOP, CLIP = 0x2FF0000, 0x2FFF000, 0x2030000

    def __init__(self, payload):
        self.m = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        self.m.mem_map(0x10000, 0x3000000)
        image = XbeImage(payload)
        for section in image.sections:
            if section.raw_size:
                self.m.mem_write(section.start, image.read(section.start, section.raw_size))
        for section in image.sections:
            if section.name == ".text":
                self.m.mem_protect(section.start & -4096,
                                   ((section.end + 4095) & -4096) - (section.start & -4096),
                                   uc.UC_PROT_READ | uc.UC_PROT_EXEC)
        self.put(0xE5FE68, self.RAW[0])
        self.put(0xE5FE6C, self.RAW[1])
        self.put(0xE5FF80, 5)       # game-day path: no practice reserves
        self.put(0xB7593C, self.CLIP)
        # Actual D2B30 -> A7970 -> A7CD0 getter reads a synthetic recorded
        # event 3. Only its player pointer is input; no callback is stubbed.
        self.put(0xB6E7F0, 0)
        self.put(0xB6EC90, 0)
        self.put(0xB6EC94, 1)
        self.put(0xB667E0, 3)
        self.players = []
        for side, (team, pool) in enumerate(zip(self.RAW, self.RECORDS)):
            self.m.mem_write(team, b"\0" * 500)
            self.m.mem_write(team + 0x11C, b"\x05")
            group = []
            for i, (pos, jersey) in enumerate(((9, 82), (0, 10), (3, 3), (7, 38), (0, 19))):
                at = pool + i * 84
                data = bytearray(84)
                struct.pack_into("<H", data, 6, 100 + side * 10 + i)
                struct.pack_into("<II", data, 0x10, 0x2500000 + side * 0x1000 + i * 64,
                                 0x2500020 + side * 0x1000 + i * 64)
                struct.pack_into("<I", data, 0x18, 0x1234000 + i * 0x1000)
                struct.pack_into("<I", data, 0x20, jersey << 3)
                data[0x35] = pos
                self.m.mem_write(at, bytes(data))
                self.put(team + i * 4, at)
                group.append(at)
            self.players.append(group)
        self.call(0x61730, ecx=self.RAW[0], edx=self.RAW[1])

    def put(self, at, value):
        self.m.mem_write(at, struct.pack("<I", value & 0xFFFFFFFF))

    def get(self, at):
        return int.from_bytes(self.m.mem_read(at, 4), "little")

    def copy(self, side, index):
        return self.get(self.GAME[side] + index * 4)

    def jersey(self, at):
        return self.get(at + 0x20) >> 3 & 127

    def call(self, va, *, ecx=0, edx=0, ebx=0x12345678, eax=0, args=()):
        self.put(self.STACK, self.STOP)
        for i, value in enumerate(args):
            self.put(self.STACK + 4 + i * 4, value)
        preserved = {r.UC_X86_REG_EBX: ebx, r.UC_X86_REG_ESI: 0x11111111,
                     r.UC_X86_REG_EDI: 0x22222222, r.UC_X86_REG_EBP: 0x33333333}
        for reg, value in {**preserved, r.UC_X86_REG_ESP: self.STACK,
                           r.UC_X86_REG_ECX: ecx, r.UC_X86_REG_EDX: edx, r.UC_X86_REG_EAX: eax}.items():
            self.m.reg_write(reg, value)
        self.m.emu_start(va, self.STOP, count=200000, timeout=3000000)
        if self.m.reg_read(r.UC_X86_REG_EIP) != self.STOP:
            raise AssertionError("native instruction budget exhausted")
        if self.m.reg_read(r.UC_X86_REG_ESP) != self.STACK + 4 + 4 * len(args):
            raise AssertionError("native stack imbalance")
        for reg, value in preserved.items():
            if self.m.reg_read(reg) != value:
                raise AssertionError("nonvolatile register changed")
        return self.m.reg_read(r.UC_X86_REG_EAX)

    def feature(self, source, role):
        self.put(0xB667E0 + 0x20, role)
        return self.call(0xDE080, ecx=source, eax=0xD2B30)


@unittest.skipIf(uc is None, "Unicorn absent")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = [("retail", retail_xbe())]
        if os.environ.get("NFL2K5_SC2_XBE"):
            cls.inputs.append(("integrated", Path(os.environ["NFL2K5_SC2_XBE"]).read_bytes()))

    def test_qb_te_source_order_drift_reproduces_then_repairs(self):
        for name, base in self.inputs:
            for fixed in (False, True):
                for side in (0, 1):
                    with self.subTest(image=name, fixed=fixed, side=side):
                        m = Machine(sc.apply(base)[0] if fixed else base)
                        te, qb = m.players[side][:2]
                        te_role, qb_role = m.copy(side, 0), m.copy(side, 1)
                        # The real roster pointer setter changes source order
                        # after staging; the disposable copy retains its order.
                        m.call(0xC3D70, ecx=m.RAW[side], edx=qb, args=(0,))
                        m.call(0xC3D70, ecx=m.RAW[side], edx=te, args=(1,))
                        before = bytes(m.m.mem_read(m.RAW[side], 500))
                        m.feature(qb, qb_role)
                        self.assertEqual((m.jersey(qb_role), m.jersey(te_role)),
                                         (10, 82) if fixed else (82, 10))
                        self.assertEqual(bytes(m.m.mem_read(m.RAW[side], 500)), before)
        print("NATIVE source-order drift: base QB=82 / TE=10; repaired QB=10 / TE=82, both sides")

    def test_prior_native_record_swap_does_not_poison_the_next_lookup(self):
        for name, base in self.inputs:
            for fixed in (False, True):
                with self.subTest(image=name, fixed=fixed):
                    m = Machine(sc.apply(base)[0] if fixed else base)
                    te_role, qb_role = m.copy(0, 0), m.copy(0, 1)
                    qb = m.players[0][1]
                    # First native featured-role swap moves the QB's bytes.
                    m.feature(qb, te_role)
                    self.assertEqual((m.jersey(te_role), m.jersey(qb_role)), (10, 82))
                    m.feature(qb, qb_role)
                    self.assertEqual(m.jersey(qb_role), 10 if fixed else 82)
        print("NATIVE repeated swaps: base loses the moved QB identity; repaired lookup restores it")

    def test_all_identities_and_existing_game_pointers_preserve_rosters(self):
        for _, base in self.inputs:
            m = Machine(sc.apply(base)[0])
            original = bytes(m.m.mem_read(m.GAME[0], 0x4000))
            for side in (0, 1):
                for i, source in enumerate(m.players[side]):
                    expected = m.copy(side, i)
                    self.assertEqual(m.call(sc.VA, ebx=source), expected)
                    self.assertEqual(m.call(sc.VA, ebx=expected), expected)
            self.assertEqual(bytes(m.m.mem_read(m.GAME[0], 0x4000)), original)

    def test_mutable_fields_ignored_but_identity_mismatch_uses_native_copy_fallback(self):
        m = Machine(sc.apply(self.inputs[0][1])[0])
        source, dest = m.players[0][1], m.copy(0, 1)
        m.m.mem_write(dest + 4, struct.pack("<H", 0x4567))
        for off, value in ((0x20, 0x87654321), (0x28, 0xF123),
                           (0x30, 0x76543210), (0x36, 0x11223344)):
            m.put(dest + off, value)
        m.put(dest + 0x18, m.get(dest + 0x18) ^ 0xF0000FFF)
        self.assertEqual(m.call(sc.VA, ebx=source), dest)
        # The portrait is immutable identity, unlike the commentary cue.
        m.m.mem_write(dest + 6, b"\xff\xff")
        self.assertEqual(m.call(sc.VA, ebx=source), 0)
        m.feature(source, dest)
        self.assertEqual(bytes(m.m.mem_read(dest, 84)), bytes(m.m.mem_read(source, 84)))

    def test_ambiguous_missing_empty_and_over_capacity_lists(self):
        m = Machine(sc.apply(self.inputs[0][1])[0])
        source, dest = m.players[0][1], m.copy(0, 1)
        other = m.copy(0, 2)
        m.m.mem_write(other, bytes(m.m.mem_read(dest, 84)))
        self.assertEqual(m.call(sc.VA, ebx=source), 0)
        m.feature(source, dest)
        self.assertEqual(m.jersey(dest), 10)
        for side in (0, 1):
            m.m.mem_write(m.GAME[side] + 0x11C, b"\0")
        self.assertEqual(m.call(sc.VA, ebx=source), 0)
        for side in (0, 1):
            m.m.mem_write(m.GAME[side] + 0x11C, b"\xff")
        self.assertEqual(m.call(sc.VA, ebx=source), 0)

    def test_last_legal_roster_pointer_and_null_entries_are_bounded(self):
        m = Machine(sc.apply(self.inputs[0][1])[0])
        source, dest = m.players[0][1], m.copy(0, 1)
        m.m.mem_write(m.GAME[0], bytes(65 * 4))
        m.put(m.GAME[0] + 64 * 4, dest)
        # The following header field is outside the 65 player pointers.
        m.put(m.GAME[0] + 65 * 4, dest)
        m.m.mem_write(m.GAME[0] + 0x11C, b"\x41")
        self.assertEqual(m.call(sc.VA, ebx=source), dest)


if __name__ == "__main__":
    unittest.main()
