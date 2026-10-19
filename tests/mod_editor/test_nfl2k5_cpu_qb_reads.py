"""CPU QB reads writer: exact bytes, replay, refusal and composition. No game boot, no disc build.

The pinned USA retail default.xbe is read from NFL2K5_RETAIL_EXTRACTION (skipped when absent). The b775 test-disc
executable is optional: NFL2K5_B775_XBE names an extracted default.xbe (sha256 cd367b3b...), skipped when unset.
"""
from pathlib import Path
import hashlib
import os
import shutil
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_cpu_qb_reads as reads
from mod_editor.core import nfl2k5_cpu_qb_reads_code as assembly
from mod_editor.core import nfl2k5_cpu_scrambles as scrambles
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe, repin_edit

B775_SHA256 = "cd367b3bb4ef2e47b4267af3b9c1fb9d9607e6b3359414f32917a3b4ebc304c6"


def b775_xbe():
    path = os.environ.get("NFL2K5_B775_XBE")
    if not path or not Path(path).is_file():
        raise unittest.SkipTest("NFL2K5_B775_XBE (the extracted b775 test-disc default.xbe) is not set")
    payload = Path(path).read_bytes()
    if hashlib.sha256(payload).hexdigest() != B775_SHA256:
        raise unittest.SkipTest("NFL2K5_B775_XBE does not match the b775 evidence pin")
    return payload


def differing_spans(a, b):
    spans, start = [], None
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y and start is None:
            start = i
        elif x == y and start is not None:
            spans.append((start, i)); start = None
    if start is not None:
        spans.append((start, len(a)))
    return spans


class WriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.zone, cls.zone_receipt = reads.apply(cls.retail, zone_windows=True)
        cls.recheck, cls.recheck_receipt = reads.apply(cls.retail, recheck=True)
        cls.both, cls.both_receipt = reads.apply(cls.retail, zone_windows=True, recheck=True)

    def test_retail_reads_retail_and_options_default_off(self):
        self.assertEqual(reads.read_settings(self.retail), {"status": "retail", "zone_windows": False, "recheck": False})
        with self.assertRaises(reads.CpuQbReadsError):
            reads.apply(self.retail)

    def test_zone_option_is_one_curve_and_no_allocation(self):
        self.assertEqual(len(self.zone), len(self.retail))
        self.assertEqual(space.status(self.zone), "retail")
        image = XbeImage(self.zone)
        off = image.offset(reads.ZONE_CURVE_VA, 44)
        changed = [s for s in differing_spans(self.retail, self.zone)]
        # the four y values that move (x = -0.1 keeps -0.05 is unchanged), plus section digests in the header
        body = [(a, b) for a, b in changed if a >= 0x1000]
        self.assertTrue(all(off <= a and b <= off + 44 for a, b in body), body)
        values = struct.unpack_from("<I10f", self.zone, off)
        self.assertEqual(values[0], 5)
        self.assertEqual(values[1::2], tuple(struct.unpack("<f", struct.pack("<f", x))[0] for x in reads.ZONE_X))
        self.assertEqual(values[2::2], tuple(struct.unpack("<f", struct.pack("<f", y))[0] for y in reads.ZONE_Y))
        self.assertEqual(reads.read_settings(self.zone), {"status": "applied", "zone_windows": True, "recheck": False})
        for s in _sections(self.zone):
            self.assertEqual(section_digest(self.zone, s), s.stored_digest)

    def test_recheck_installs_owned_code_three_hooks_and_zero_state(self):
        owned = reads.allocations(self.recheck)
        c, d = owned["code"]["va"], owned["data"]["va"]
        image = XbeImage(self.recheck)
        self.assertEqual(image.read(c, reads.CODE_SIZE), reads.code_for(c, d))
        self.assertEqual(image.read(d, reads.DATA_SIZE), bytes(reads.DATA_SIZE))
        self.assertLessEqual(len(assembly.CODE), reads.CODE_SIZE)
        for name, va, before, after in reads.hook_sites(c):
            raw = image.read(va, len(before))
            self.assertEqual(raw, after, name)
            width = 2 if name == "hold" else 1
            target = va + width + 4 + struct.unpack_from("<i", raw, width)[0]
            self.assertEqual(target, c + assembly.LABELS[name], name)
        self.assertEqual(image.read(reads.ZONE_CURVE_VA, 44), reads.RETAIL_ZONE_CURVE)
        self.assertEqual(reads.read_settings(self.recheck), {"status": "applied", "zone_windows": False, "recheck": True})
        self.assertEqual(space.status(self.recheck), "applied")

    def test_both_replay_exactly_and_refuse_a_different_selection(self):
        self.assertEqual(reads.read_settings(self.both), {"status": "applied", "zone_windows": True, "recheck": True})
        again, receipt = reads.apply(self.both, zone_windows=True, recheck=True)
        self.assertEqual(again, self.both)
        self.assertEqual(receipt["status"], "already_applied")
        for payload, wanted in ((self.zone, dict(recheck=True)), (self.recheck, dict(zone_windows=True)),
                                (self.both, dict(zone_windows=True))):
            with self.assertRaises(reads.CpuQbReadsError):
                reads.apply(payload, **wanted)
        self.assertEqual(self.both_receipt["runtime_witnessed"], False)
        self.assertEqual({e["label"] for e in self.both_receipt["edits"]}, {"stamp", "pick", "hold", "covered_window_curve"})

    def test_foreign_hooks_code_state_curve_and_prerequisites_refuse_before_mutation(self):
        owned = reads.allocations(self.both)
        c, d = owned["code"]["va"], owned["data"]["va"]
        cases = {
            "hook": (0x19BD8C, b"\xe8\x00\x00\x00\x00"),
            "half hook": (0x19BC72, reads.HOOKS[2][2]),
            "code": (c + 3, b"\x90"),
            "state": (d + 8, b"\x01"),
            "curve": (reads.ZONE_CURVE_VA + 4 + 8 * 3 + 4, struct.pack("<f", -0.3)),
            "openness": (0x199F50, b"\x90"),
            "picker": (0x1985F0, b"\x90"),
            "updater": (0x19B300, b"\x90"),
            "qb tick": (0x19BC00, b"\x90"),
        }
        for label, (va, content) in cases.items():
            bad = repin_edit(self.both, va, content)
            self.assertEqual(reads.status(bad), "foreign", label)
            with self.assertRaises(reads.CpuQbReadsError):
                reads.apply(bad, zone_windows=True, recheck=True)
        retail_bad = repin_edit(self.retail, reads.ZONE_CURVE_VA + 8, struct.pack("<f", 0.07))
        self.assertEqual(reads.status(retail_bad), "foreign")
        with self.assertRaises(reads.CpuQbReadsError):
            reads.apply(retail_bad, zone_windows=True)

    def test_neighbor_normalization_only_for_the_verified_installation(self):
        self.assertEqual(reads.normalized_sites(self.retail), [])
        self.assertEqual(len(reads.normalized_sites(self.both)), 3)
        # a changed owned byte breaks the allocator seal itself; any ValueError means "foreign" to a neighbor
        bad = repin_edit(self.both, reads.allocations(self.both)["code"]["va"] + 1, b"\x90")
        with self.assertRaises(ValueError):
            reads.normalized_sites(bad)
        self.assertEqual(scrambles.status(bad), "foreign")  # its guard view refuses the unverifiable neighbor

    @unittest.skipUnless(shutil.which("as"), "GNU as is required to reproduce the byte template")
    def test_assembler_reproduces_shipped_bytes(self):
        from nfl2k5_cpu_ai_assemble import template
        self.assertEqual((ROOT / "mod_editor/core/nfl2k5_cpu_qb_reads_code.py").read_text(encoding="utf-8"),
                         template("nfl2k5_cpu_qb_reads"))


class CompositionTests(unittest.TestCase):
    """The QB tick 0x19BB60 is guarded by both this owner and cpu_scrambles; each accepts only the other's
    complete verified installation. This owner is a late allocator owner, installed after every other writer."""

    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()

    def test_cpu_scrambles_then_reads_both_applied_and_replay(self):
        base, _ = scrambles.apply(self.retail)
        final, _ = reads.apply(base, zone_windows=True, recheck=True)
        self.assertEqual(scrambles.status(final), "applied")
        self.assertEqual(reads.status(final), "applied")
        self.assertEqual(reads.apply(final, zone_windows=True, recheck=True)[0], final)
        self.assertEqual(scrambles.apply(final)[0], final)
        # a foreign scramble hook makes both recognizers refuse
        bad = repin_edit(final, 0x19C36C, b"\xd8\x0d\x00\x00\x00\x00")
        self.assertEqual(reads.status(bad), "foreign")
        self.assertEqual(scrambles.status(bad), "foreign")
        # a foreign reads hook inside the scramble guard makes cpu_scrambles refuse too
        bad = repin_edit(final, 0x19BD8C, b"\xe8\x00\x00\x00\x00")
        self.assertEqual(scrambles.status(bad), "foreign")

    def test_reads_cannot_be_appended_before_or_twice(self):
        final, _ = reads.apply(self.retail, recheck=True)
        with self.assertRaises(ValueError):
            space.extend_scaleout(final, reads.REQUESTS)


class B775Tests(unittest.TestCase):
    """The real build path's input: the b775 test-disc executable with every shipped owner installed."""

    @classmethod
    def setUpClass(cls):
        cls.b775 = b775_xbe()
        cls.final, cls.receipt = reads.apply(cls.b775, zone_windows=True, recheck=True)

    def test_late_allocation_moves_no_owner_and_neighbors_stay_applied(self):
        before = {(a["owner"], a["kind"]): a for a in space.layout(self.b775)["allocations"]}
        after = {(a["owner"], a["kind"]): a for a in space.layout(self.final)["allocations"]}
        for key, row in before.items():
            if key[0] != space.DIRECTORY_OWNER:
                self.assertEqual(after[key], row, key)
        self.assertEqual(set(after) - set(before), {(reads.OWNER, "code"), (reads.OWNER, "data")})
        self.assertEqual(len(self.final), len(self.b775))
        from mod_editor.core import (nfl2k5_cpu_money_downs as money, nfl2k5_screen_hooks as screen,
                                     nfl2k5_qb_spy_runtime as spy)
        for module in (scrambles, money, screen, spy):
            self.assertEqual(module.status(self.final), module.status(self.b775), module.__name__)
        self.assertEqual(reads.read_settings(self.final), {"status": "applied", "zone_windows": True, "recheck": True})


if __name__ == "__main__":
    unittest.main()
