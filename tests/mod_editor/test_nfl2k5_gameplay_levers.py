"""Coverage and slow-QB owners: pins, transactions, allocation and composition."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import nfl2k5_coverage_slider as coverage
from mod_editor.core import nfl2k5_scramble_tuning as scramble
from mod_editor.core import nfl2k5_gameplay_lever as lever
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core import nfl2k5_rdata_sites as rdata
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.nfl2k5_gameplay_levers_fixture import XBE, HAVE_CAPSTONE, replace

MODULES = (coverage, scramble)


class MappingTests(unittest.TestCase):
    def test_coverage_neutral_and_endpoints(self):
        rows = coverage.mapping()["points"]
        self.assertAlmostEqual(rows[1]["retail_contribution"], rows[1]["patch_contribution"])
        self.assertEqual([p["patch_contribution"] for p in rows], [0.0, .1125, .225])
        self.assertIn("does not set interception", coverage.HELP_TEXT)
        self.assertEqual(struct.pack("<f", .75 * coverage.RETAIL_SLOPE),
                         struct.pack("<f", .5 * coverage.PATCH_SLOPE))

    def test_scramble_curve_keeps_count_abscissas_and_endpoint(self):
        old, new = scramble.RETAIL_CURVE, scramble.table_bytes()
        self.assertEqual(len(old), len(new))
        self.assertEqual(old[:4], new[:4])
        for offset in range(4, len(old), 8):
            self.assertEqual(old[offset:offset + 4], new[offset:offset + 4])
            before = struct.unpack_from("<f", old, offset + 4)[0]
            after = struct.unpack_from("<f", new, offset + 4)[0]
            self.assertAlmostEqual(after, before * .65, places=7)
        self.assertEqual(new[-4:], b"\0" * 4)
        self.assertEqual(scramble.SPEED_THRESHOLD, 60)

    def test_malformed_payloads_refuse(self):
        for module in MODULES:
            for payload in (b"", b"XBEH" + b"\0" * 4092):
                self.assertEqual(module.status(payload), "foreign")
                with self.assertRaises(ValueError):
                    module.apply(payload)

    @unittest.skipUnless(HAVE_CAPSTONE, "capstone is not installed")
    def test_selector_preserves_flags_uses_no_floating_arithmetic_or_absolute_writes(self):
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        instructions = list(Cs(CS_ARCH_X86, CS_MODE_32).disasm(scramble.code_for(0x14BA000), 0x14BA000))
        body = instructions[:next(i for i, ins in enumerate(instructions) if ins.mnemonic == "int3")]
        self.assertEqual([i.mnemonic for i in body[:2]], ["pushfd", "push"])
        self.assertEqual([i.mnemonic for i in body[-3:]], ["pop", "popfd", "jmp"])
        self.assertFalse(any(i.mnemonic.startswith("f") for i in body))
        self.assertEqual(body[-1].op_str, "0x1b0ae0")


@unittest.skipUnless(XBE.is_file(), "pinned retail default.xbe extraction is absent")
class RetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        cls.allocated, _ = space.apply(cls.retail, coverage.REQUESTS + scramble.REQUESTS)
        cls.patched, _ = coverage.apply(cls.allocated)
        cls.patched, _ = scramble.apply(cls.patched)

    def test_retail_applied_replay_and_exact_receipts(self):
        for module in MODULES:
            self.assertEqual(module.status(self.retail), "retail")
            patched, receipt = module.apply(self.retail)
            self.assertEqual(module.status(patched), "applied")
            self.assertEqual(module.apply(patched)[0], patched)
            self.assertEqual(module.apply(patched)[1]["changed_bytes"], 0)
            self.assertFalse(receipt["runtime_witnessed"])
            self.assertEqual(receipt["runtime_state_bytes"], 0)
            for edit in receipt["edits"]:
                after = bytes.fromhex(edit["after"])
                offset = int(edit["file_offset"], 0)
                self.assertEqual(patched[offset:offset + len(after)], after)
            for section in _sections(patched):
                self.assertEqual(patched[section.header_offset + 36:section.header_offset + 56], section_digest(patched, section))

    def test_both_orders_are_identical(self):
        reverse, _ = scramble.apply(self.allocated)
        reverse, _ = coverage.apply(reverse)
        self.assertEqual(reverse, self.patched)
        for module in MODULES:
            self.assertEqual(module.status(reverse), "applied")

    def test_new_allocations_append_after_the_beta61_reservations(self):
        from tests.nfl2k5_allocator_stack import REQUESTS
        base_requests = tuple(r for r in REQUESTS if r[0] not in {m.OWNER for m in MODULES})
        old = {a["owner"] + a["kind"]: a for a in space._allocations(base_requests)}
        new = {a["owner"] + a["kind"]: a for a in space._allocations(REQUESTS)}
        for key, allocation in old.items():
            self.assertEqual(new[key], allocation)

    def test_no_runtime_storage_shared_constants_or_unrelated_readers_changed(self):
        image, old = XbeImage(self.patched), XbeImage(self.retail)
        for va, size in ((0x4E696C, 4), (0x4E88D8, 4), (0x50A5B4, 44), (0x2E91F0, 1021),
                         (0x75CD5, 6), (0x1E0F90, 0x320)):
            self.assertEqual(image.read(va, size), old.read(va, size), hex(va))
        for module in MODULES:
            a = lever.allocation(self.patched, module.OWNER, module.CODE_SIZE)
            self.assertFalse(image.runtime_writable(a["va"], a["size"]))
            self.assertEqual(a["kind"], "code")

    def test_mixed_hook_constants_and_prerequisites_refuse(self):
        for module in MODULES:
            a = lever.allocation(self.patched, module.OWNER, module.CODE_SIZE)
            for _, va, before, _ in module.sites(a["va"]):
                mixed = replace(self.patched, va, before)
                self.assertEqual(module.status(mixed), "foreign")
                with self.assertRaises(ValueError):
                    module.apply(mixed)
            broken = replace(self.patched, a["va"], b"\xab")
            self.assertEqual(module.status(broken), "foreign")
            # A valid section digest cannot hide a changed dependency.
            va = module.GUARDS[-1][0]
            broken = replace(self.retail, va, b"\xab")
            self.assertEqual(module.status(broken), "foreign")
            with self.assertRaises(ValueError):
                module.apply(broken)

    def test_no_unreserved_address_is_used(self):
        empty, _ = space.apply(self.retail)
        for module in MODULES:
            with self.assertRaisesRegex(ValueError, "owner union"):
                module.apply(empty)

    def test_coverage_side_lookup_and_second_consumer_correct_the_memo(self):
        image = XbeImage(self.retail)
        self.assertEqual(image.read(0x17B8FD, 7), bytes.fromhex("d9048dc0b8aa00"))
        self.assertEqual(image.read(0x2E9356, 5), b"\xb9\x03\0\0\0")
        self.assertEqual(image.read(0x2E9366, 5), b"\xb9\x06\0\0\0")

    def test_manifest_recorder_covers_allocations_and_complete_hooks(self):
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        recorder = Recorder(self.retail)
        current = self.retail
        allocated, receipt = space.apply(current, coverage.REQUESTS + scramble.REQUESTS)
        recorder.observe(space, "apply", current, allocated, receipt)
        current = allocated
        for module in MODULES:
            updated, receipt = module.apply(current)
            recorder.observe(module, "apply", current, updated, receipt)
            current = updated
        rows = recorder.finish(current)
        for module in MODULES:
            a = lever.allocation(current, module.OWNER, module.CODE_SIZE)
            self.assertTrue(any(row["owner"] == module.OWNER and int(row["start"], 0) <= a["va"]
                                and int(row["end"], 0) >= a["va"] + a["size"] for row in rows))
            for _, va, before, _ in module.sites(a["va"]):
                self.assertTrue(any(row["owner"] == module.OWNER and int(row["start"], 0) <= va
                                    and int(row["end"], 0) >= va + len(before) for row in rows))


if __name__ == "__main__":
    unittest.main()
