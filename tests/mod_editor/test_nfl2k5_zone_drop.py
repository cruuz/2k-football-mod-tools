"""Standalone patch integrity, allocation and receipt proofs; no game boot."""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_zone_drop as zone
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core import nfl2k5_dynamic_kickoff_relocated as kickoff
from mod_editor.core import nfl2k5_scorebug_runtime as runtime
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, DEFAULT_MANIFEST, ReservationManifest, RETAIL_SHA256

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)/default.xbe"
HAVE_CS = importlib.util.find_spec("capstone") is not None


def repin(buf):
    for s in _sections(buf):
        buf[s.header_offset + 36:s.header_offset + 56] = section_digest(buf, s)
    return bytes(buf)


class PublicTests(unittest.TestCase):
    def test_configuration_bounds_and_bad_inputs(self):
        for cap in (0.5, 0.6, 0.75, 0.84):
            self.assertEqual(len(zone.code_for(space.CODE_VA, cap)), 80)
        for cap in (True, "0.84", None, -1, 0.499999, 0.840001, 0.90, 1, float("nan"), float("inf")):
            with self.subTest(cap=cap), self.assertRaises(ValueError):
                zone.code_for(space.CODE_VA, cap)
        for payload in (b"", b"XBEH", b"bad", None):
            self.assertEqual(zone.status(payload), "foreign")
            with self.assertRaises((ValueError, TypeError, struct.error)):
                zone.apply(payload)

    @unittest.skipUnless(HAVE_CS, "capstone missing: wrapper instruction proof requires it")
    def test_complete_78_byte_body_both_relocations_and_stack_only_writes(self):
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32, CS_AC_WRITE
        from capstone.x86 import X86_OP_MEM, X86_REG_ESP
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        md.detail = True
        for va in (space.CODE_VA, space.CODE_VA + 0xA60):
            code = zone.code_for(va)
            instructions = list(md.disasm(code[:zone.BODY_SIZE], va))
            self.assertEqual(sum(i.size for i in instructions), 78)
            self.assertEqual(code[78:], b"\xcc\xcc")
            self.assertEqual([(i.mnemonic, i.op_str) for i in instructions if i.mnemonic == "call"],
                             [("call", hex(zone.CURVE_VA))])
            hook = list(md.disasm(zone.hook_bytes(va), zone.HOOK_VA))
            self.assertEqual([(i.mnemonic, i.op_str, i.size) for i in hook], [("call", hex(va), 5)])
            self.assertEqual(instructions[-1].mnemonic, "ret")
            self.assertEqual(instructions[-1].op_str, "4")
            for i in instructions:
                for operand in i.operands:
                    if operand.type == X86_OP_MEM and operand.access & CS_AC_WRITE:
                        self.assertEqual(operand.mem.base, X86_REG_ESP, str(i))


@unittest.skipUnless(XBE.is_file(), f"pinned USA default.xbe absent: {XBE}")
class RetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise AssertionError("retail evidence hash differs from pinned USA executable")
        cls.base, _ = space.apply(cls.retail, zone.REQUESTS)
        cls.patched, cls.receipt = zone.apply(cls.base)

    def test_exact_hook_idempotence_receipts_and_section_digests(self):
        self.assertEqual(zone.status(self.retail), "retail")
        self.assertEqual(zone.status(self.base), "retail")
        self.assertEqual(zone.status(self.patched), "applied")
        self.assertEqual(zone.apply(self.retail)[0], self.patched)
        self.assertEqual(zone.apply(self.patched)[0], self.patched)
        self.assertEqual(zone.apply(self.patched)[1]["changed_bytes"], 0)
        self.assertTrue(self.receipt["experimental"])
        self.assertFalse(self.receipt["runtime_witnessed"])
        self.assertEqual(self.receipt["persistent_data_bytes"], 0)
        self.assertEqual(self.receipt["file_growth"], 0)
        self.assertEqual(self.receipt["before_sha256"], hashlib.sha256(self.base).hexdigest())
        self.assertEqual(self.receipt["after_sha256"], hashlib.sha256(self.patched).hexdigest())
        self.assertEqual(self.receipt["changed_bytes"], sum(a != b for a, b in zip(self.base, self.patched)))
        before, after = XbeImage(self.base), XbeImage(self.patched)
        a = zone.site(self.patched)
        self.assertEqual(after.read(zone.HOOK_VA, 5), zone.hook_bytes(a["va"]))
        self.assertEqual(after.read(a["va"], 80), zone.code_for(a["va"]))
        for s in _sections(self.patched):
            self.assertEqual(s.stored_digest, section_digest(self.patched, s))
        # Every pre-existing section is byte-identical except the five-byte call.
        for s in before.sections:
            if s.start == space.CODE_VA:
                continue
            old = bytearray(before.read(s.start, s.raw_size))
            if s.start <= zone.HOOK_VA < s.end:
                off = zone.HOOK_VA - s.start
                old[off:off + 5] = after.read(zone.HOOK_VA, 5)
            self.assertEqual(bytes(old), after.read(s.start, s.raw_size), s.name)

    def test_settings_preserved_and_reconfiguration_refused(self):
        custom, _ = zone.apply(self.base, cap=0.6)
        settings = zone.read_settings(custom)
        self.assertAlmostEqual(settings["cap"], 0.6)
        self.assertEqual(zone.apply(custom)[0], custom)
        self.assertEqual(zone.apply(custom, cap=0.6)[0], custom)
        with self.assertRaisesRegex(ValueError, "different zone-drop cap"):
            zone.apply(custom, cap=0.84)

    def assert_refused(self, payload):
        before = bytes(payload)
        self.assertEqual(zone.status(payload), "foreign")
        with self.assertRaises(ValueError):
            zone.apply(payload)
        self.assertEqual(bytes(payload), before)

    def test_every_pin_hook_byte_and_mixed_install_refuses_even_with_fresh_digests(self):
        image = XbeImage(self.patched)
        for va, size, _ in zone.RETAIL_GUARDS:
            for index in (0, size - 1):
                bad = bytearray(self.patched)
                bad[image.offset(va) + index] ^= 1
                with self.subTest(va=hex(va), index=index):
                    self.assert_refused(repin(bad))
        for index in range(5):
            bad = bytearray(self.patched)
            bad[image.offset(zone.HOOK_VA) + index] ^= 1
            self.assert_refused(repin(bad))
        bad = bytearray(self.patched)
        off = image.offset(zone.HOOK_VA)
        bad[off:off + 5] = zone.RETAIL_HOOK
        self.assert_refused(repin(bad))  # owned body, retail hook
        bad = bytearray(self.base)
        bad[off:off + 5] = image.read(zone.HOOK_VA, 5)
        self.assert_refused(repin(bad))  # empty body, installed hook
        for length in (0, 4, 0x120, 4096, len(self.patched) - 1):
            self.assert_refused(self.patched[:length])
        self.assert_refused(self.patched + b"\0")

    def test_sealed_foreign_body_and_padding_cannot_masquerade_as_owned(self):
        a = zone.site(self.base)
        content = zone.code_for(a["va"])
        for index in (0, 4, 9, 15, 26, 37, 42, 50, 54, 65, 73, 75, 78, 79):
            bad = bytearray(content)
            bad[index] ^= 0x80
            # Seal with the allocator, to exercise this owner's recognition
            # independently from the directory/code-page hash check.
            sealed, _ = space.install_code(self.base, zone.OWNER, bytes(bad))
            buf = bytearray(sealed)
            off = XbeImage(sealed).offset(zone.HOOK_VA)
            buf[off:off + 5] = zone.hook_bytes(a["va"])
            self.assert_refused(repin(buf))
        for requests in (((zone.OWNER, "code", 79, 16),),
                         ((zone.OWNER, "code", 80, 8),),
                         ((zone.OWNER, "data", 80, 16),),
                         zone.REQUESTS + ((zone.OWNER, "data", 4, 4),)):
            bad = space.apply(self.retail, requests)[0]
            self.assert_refused(bad)

    def test_each_available_owner_composes_in_both_orders_with_stable_allocations(self):
        for other in (kickoff, runtime):
            with self.subTest(owner=other.OWNER):
                base, _ = space.apply(self.retail, zone.REQUESTS + other.REQUESTS)
                expected = space.layout(base)["allocations"]
                left = other.apply(zone.apply(base)[0])[0]
                right = zone.apply(other.apply(base)[0])[0]
                self.assertEqual(left, right)
                self.assertEqual(space.layout(left)["allocations"], expected)
                for module in (zone, other):
                    self.assertEqual(module.status(left), "applied")
                    self.assertEqual(module.apply(left)[0], left)
                for s in _sections(left):
                    self.assertEqual(s.stored_digest, section_digest(left, s))

    def test_extended_allocator_fits_union_and_refuses_missing_owner(self):
        grown, _ = space.apply(self.retail, zone.REQUESTS + kickoff.REQUESTS + runtime.REQUESTS)
        self.assertEqual(space.status(grown), "applied")
        self.assertEqual(len([r for r in space.layout(grown)["regions"] if r["kind"] == "code"]), 2)
        grown = kickoff.apply(self.retail)[0]
        with self.assertRaisesRegex(ValueError, "missing zone-drop allocation"):
            zone.apply(grown)
        self.assertEqual(kickoff.status(grown), "applied")

    def test_cave_manifest_records_whole_owned_body_and_call(self):
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        recorder = Recorder(self.retail)
        recorder.observe(space, "apply", self.retail, self.base, {})
        recorder.observe(zone, "apply", self.base, self.patched, self.receipt)
        spans = recorder.finish(self.patched)
        a = zone.site(self.patched)
        for va, size in ((zone.HOOK_VA, 5), (a["va"], 80)):
            self.assertTrue(any(row["owner"] == zone.OWNER and int(row["start"], 0) == va
                                and row["size"] == size for row in spans))
        manifest = ReservationManifest.load(DEFAULT_MANIFEST, XbeImage(self.retail))
        self.assertEqual(manifest.overlaps(zone.HOOK_VA, zone.CONTINUE_VA, exclude_owner=zone.OWNER), [])
        self.assertEqual(space.allocation_evidence(self.retail, manifest)["encoded_references"], [])
        self.assertFalse(XbeImage(self.patched).runtime_writable(a["va"], a["size"]))
        self.assertEqual([r for r in space.layout(self.patched)["allocations"] if r["owner"] == zone.OWNER], [a])


if __name__ == "__main__":
    unittest.main()
