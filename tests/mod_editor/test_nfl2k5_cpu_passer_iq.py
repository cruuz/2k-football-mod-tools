"""CPU quarterbacks throw on time and check down: exact bytes, replay, refusal and composition. No game boot or disc build.

The pinned USA retail default.xbe is read from NFL2K5_RETAIL_EXTRACTION (skipped when absent). The released SOFTDRINK
2K28 v0.8 executable is optional: NFL2K5_V08_XBE names an extracted default.xbe (sha256 5f987568...), skipped when unset.
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

from mod_editor.core import nfl2k5_cpu_passer_iq as passer
from mod_editor.core import nfl2k5_cpu_passer_iq_code as assembly
from mod_editor.core import nfl2k5_cpu_qb_reads as reads
from mod_editor.core import nfl2k5_cpu_scrambles as scrambles
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe, repin_edit

V08_SHA256_PREFIX = "5f987568"


def v08_xbe():
    path = os.environ.get("NFL2K5_V08_XBE")
    if not path or not Path(path).is_file():
        raise unittest.SkipTest("NFL2K5_V08_XBE (the extracted v0.8 release default.xbe) is not set")
    payload = Path(path).read_bytes()
    if not hashlib.sha256(payload).hexdigest().startswith(V08_SHA256_PREFIX):
        raise unittest.SkipTest("NFL2K5_V08_XBE does not match the v0.8 release pin")
    return payload


def f32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


class WriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.applied, cls.receipt = passer.apply(cls.retail)

    def test_retail_reads_retail_and_the_option_is_one_late_owner(self):
        self.assertEqual(passer.status(self.retail), "retail")
        self.assertEqual(passer.read_settings(self.retail), {"status": "retail"})
        # a late owner after every late owner beta-79 / v0.8 shipped (its last was nfl2k5_sim_realism_state), so adding
        # it to a released executable moves nothing (ReleaseExecutableTests); later b780 owners may follow it (b780 n6)
        self.assertGreater(space.LATE_OWNERS.index(passer.OWNER), space.LATE_OWNERS.index("nfl2k5_sim_realism_state"))
        self.assertEqual(passer.REQUESTS, ((passer.OWNER, "code", 256, 16), (passer.OWNER, "data", 16, 16)))
        self.assertNotIn("—", passer.HELP_TEXT + passer.BUILD_CAPTION)

    def test_install_writes_the_hook_the_operands_the_curve_owned_code_and_zero_state(self):
        payload = self.applied
        self.assertEqual(passer.status(payload), "applied")
        self.assertEqual(space.status(payload), "applied")
        owned = passer.allocations(payload)
        c, d = owned["code"]["va"], owned["data"]["va"]
        image = XbeImage(payload)
        self.assertTrue(image.section(c).executable)
        self.assertTrue(image.section(d).writable)
        self.assertEqual(image.read(c, passer.CODE_SIZE), passer.code_for(c, d))
        self.assertEqual(image.read(d, passer.DATA_SIZE), bytes(passer.DATA_SIZE))
        self.assertLessEqual(len(assembly.CODE), passer.CODE_SIZE)
        hook = image.read(0x199F23, 5)
        self.assertEqual(hook[0], 0xE8)
        self.assertEqual(0x199F28 + struct.unpack_from("<i", hook, 1)[0], c + assembly.LABELS["short"])
        # the two holdoff adds read the retail 0.6 and the pump roll divides by 60
        for va in (0x19BFCF, 0x19C1C0):
            self.assertEqual(image.read(va, 6), b"\xd8\x05" + struct.pack("<I", passer.HOLDOFF_VA))
        self.assertEqual(struct.unpack("<f", image.read(passer.HOLDOFF_VA, 4))[0], f32(passer.PUMP_HOLDOFF))
        self.assertEqual(struct.unpack("<f", image.read(passer.RETAIL_HOLDOFF_VA, 4))[0], 1.5)
        self.assertEqual(image.read(0x19C193, 5), b"\xb9" + struct.pack("<I", 60))
        curve = struct.unpack("<I10f", image.read(passer.DWELL_CURVE_VA, 44))
        self.assertEqual(curve[0], 5)
        self.assertEqual(curve[1::2], tuple(f32(x) for x in passer.DWELL_X))
        self.assertEqual(curve[2::2], tuple(f32(y) for y in passer.DWELL_Y))
        self.assertEqual(passer.RETAIL_DWELL_CURVE, XbeImage(self.retail).read(passer.DWELL_CURVE_VA, 44))
        self.assertTrue(all(new < old for new, old in zip(passer.DWELL_Y[:2], passer.RETAIL_DWELL_Y[:2])))
        for section in _sections(payload):
            self.assertEqual(section_digest(payload, section), section.stored_digest)
        # the tuning constants the code reads
        for label, value in (("k_pressure", passer.PRESSURE), ("k_start", passer.FADE_START),
                             ("k_rate", passer.FADE_RATE), ("k_floor", passer.FLOOR), ("k_one", 1.0)):
            self.assertEqual(struct.unpack("<f", image.read(c + assembly.LABELS[label], 4))[0], f32(value), label)
        self.assertEqual([e["label"] for e in self.receipt["edits"]],
                         ["checkdown", "pump_holdoff_target", "pump_holdoff_open", "pump_chance", "read_dwell_curve"])
        self.assertEqual(self.receipt["runtime_witnessed"], False)
        self.assertEqual({r["owner"] for r in self.receipt["reservations"]}, {passer.OWNER})

    def test_code_writes_only_its_own_state(self):
        from mod_editor.core.nfl2k5_cave_oracle import absolute_writes
        owned = passer.allocations(self.applied)
        c, d = owned["code"]["va"], owned["data"]["va"]
        writes = absolute_writes(self.applied, [(c, c + assembly.LABELS["k_pressure"])])   # instructions, not constants
        self.assertTrue(all(w["target"] is not None for w in writes), writes)          # no register-relative store
        targets = {int(w["target"], 16) for w in writes}
        self.assertTrue(targets, writes)
        self.assertTrue(all(d <= t < d + passer.DATA_SIZE for t in targets), writes)
        self.assertTrue(all(w["writable"] for w in writes), writes)

    def test_replay_is_byte_identical(self):
        again, receipt = passer.apply(self.applied)
        self.assertEqual(again, self.applied)
        self.assertEqual(receipt["status"], "already_applied")
        self.assertEqual(receipt["changed_bytes"], 0)

    def test_foreign_sites_code_state_and_prerequisites_refuse_before_mutation(self):
        owned = passer.allocations(self.applied)
        c, d = owned["code"]["va"], owned["data"]["va"]
        cases = {
            "hook": (0x199F23, b"\xe8\x00\x00\x00\x00"),
            "holdoff operand": (0x19BFD1, struct.pack("<I", 0x004E6D10)),
            "second holdoff operand only retail": (0x19C1C2, struct.pack("<I", passer.RETAIL_HOLDOFF_VA)),
            "pump chance": (0x19C194, struct.pack("<I", 40)),
            "dwell curve": (passer.DWELL_CURVE_VA + 8, struct.pack("<f", 0.9)),
            "code": (c + 3, b"\x90"),
            "constant": (c + assembly.LABELS["k_floor"], struct.pack("<f", 0.5)),
            "state": (d + 4, b"\x01"),
            "field terms": (0x199D00, b"\x90"),
            "point score": (0x19A800, b"\x90"),
            "short-throw curve": (0x50C49C, struct.pack("<f", -0.4)),
            "qb tick": (0x19BC00, b"\x90"),
            "read advance": (0x199140, b"\x90"),
            "interpolator": (0x1B0AF0, b"\x90"),
            "0.6": (passer.HOLDOFF_VA, struct.pack("<f", 0.5)),
        }
        for label, (va, content) in cases.items():
            bad = repin_edit(self.applied, va, content)
            self.assertEqual(passer.status(bad), "foreign", label)
            with self.assertRaises(passer.CpuPasserIqError, msg=label):
                passer.apply(bad)
        for label, (va, content) in (("retail with a foreign operand", (0x19BFD1, struct.pack("<I", passer.HOLDOFF_VA))),
                                     ("retail with a foreign field term", (0x199D00, b"\x90")),
                                     ("retail with a foreign curve", (passer.DWELL_CURVE_VA + 8, struct.pack("<f", 0.9)))):
            bad = repin_edit(self.retail, va, content)
            self.assertEqual(passer.status(bad), "foreign", label)
            with self.assertRaises(passer.CpuPasserIqError, msg=label):
                passer.apply(bad)

    def test_neighbor_normalization_only_for_the_verified_installation(self):
        self.assertEqual(passer.normalized_sites(self.retail), [])
        sites = passer.normalized_sites(self.applied)
        self.assertEqual([s[0] for s in sites], ["checkdown", "pump_holdoff_target", "pump_holdoff_open", "pump_chance",
                                                 "read_dwell_curve"])
        bad = repin_edit(self.applied, passer.allocations(self.applied)["code"]["va"] + 1, b"\x90")
        with self.assertRaises(ValueError):
            passer.normalized_sites(bad)

    @unittest.skipUnless(shutil.which("as"), "GNU as is required to reproduce the byte template")
    def test_assembler_reproduces_shipped_bytes(self):
        from nfl2k5_cpu_ai_assemble import template
        self.assertEqual((ROOT / "mod_editor/core/nfl2k5_cpu_passer_iq_code.py").read_text(encoding="utf-8"),
                         template("nfl2k5_cpu_passer_iq"))


class CompositionTests(unittest.TestCase):
    """The QB tick 0x19BB60 is guarded by this owner, CPU QB reads and CPU scrambles; the read dwell curve by this owner
    and CPU QB reads. Each accepts only the others' complete verified installation."""

    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.seed, _ = space.apply(cls.retail, scrambles.REQUESTS + reads.REQUESTS + passer.REQUESTS, scaleout=True)

    def _apply(self, owner, payload):
        if owner is reads:
            return reads.apply(payload, zone_windows=True, recheck=True, tiers=True)[0]
        return owner.apply(payload)[0]

    def test_every_order_gives_the_same_bytes_and_all_three_read_applied(self):
        finals = set()
        for order in ((scrambles, reads, passer), (passer, reads, scrambles), (reads, passer, scrambles),
                      (passer, scrambles, reads)):
            payload = self.seed
            for owner in order:
                payload = self._apply(owner, payload)
            with self.subTest(order=[o.OWNER for o in order]):
                self.assertEqual(passer.status(payload), "applied")
                self.assertEqual(reads.read_settings(payload),
                                 {"status": "applied", "zone_windows": True, "recheck": True, "tiers": True})
                self.assertEqual(scrambles.status(payload), "applied")
                self.assertEqual(passer.apply(payload)[0], payload)
            finals.add(payload)
        self.assertEqual(len(finals), 1)

    def test_this_owner_alone_leaves_the_neighbors_retail(self):
        payload = passer.apply(self.retail)[0]
        self.assertEqual(reads.status(payload), "retail")
        self.assertEqual(scrambles.status(payload), "retail")

    def test_a_foreign_site_of_any_owner_makes_the_others_refuse(self):
        final = self.seed
        for owner in (scrambles, reads, passer):
            final = self._apply(owner, final)
        bad = repin_edit(final, 0x19C194, struct.pack("<I", 30))           # this owner's pump roll
        self.assertEqual(reads.status(bad), "foreign")
        self.assertEqual(scrambles.status(bad), "foreign")
        self.assertEqual(passer.status(bad), "foreign")
        bad = repin_edit(final, passer.DWELL_CURVE_VA + 12, struct.pack("<f", 0.7))   # the shared dwell curve
        self.assertEqual(reads.status(bad), "foreign")
        self.assertEqual(passer.status(bad), "foreign")
        bad = repin_edit(final, 0x19BD8C, b"\xe8\x00\x00\x00\x00")         # CPU QB reads' pick hook
        self.assertEqual(passer.status(bad), "foreign")
        bad = repin_edit(final, 0x19C36C, b"\xd8\x0d\x00\x00\x00\x00")     # CPU scrambles' hook
        self.assertEqual(passer.status(bad), "foreign")

    def test_appended_last_to_an_installed_image_moves_no_owner(self):
        base, _ = scrambles.apply(self.retail)
        base, _ = reads.apply(base, zone_windows=True, recheck=True, tiers=True)
        final, receipt = passer.apply(base)
        before = {(a["owner"], a["kind"]): a for a in space.layout(base)["allocations"]}
        after = {(a["owner"], a["kind"]): a for a in space.layout(final)["allocations"]}
        for key, row in before.items():
            if key[0] != space.DIRECTORY_OWNER:
                self.assertEqual(after[key], row, key)
        self.assertEqual(set(after) - set(before), {(passer.OWNER, "code"), (passer.OWNER, "data")})
        self.assertEqual(reads.status(final), "applied")
        self.assertEqual(scrambles.status(final), "applied")
        self.assertEqual(passer.apply(final)[0], final)
        # a late owner placed before this one in LATE_OWNERS cannot be appended after it
        with self.assertRaises(ValueError):
            space.extend_scaleout(passer.apply(scrambles.apply(self.retail)[0])[0], reads.REQUESTS)


class ReleaseExecutableTests(unittest.TestCase):
    """The released v0.8 executable (every shipped owner of the SOFTDRINK recipe installed) takes the owner in place."""

    @classmethod
    def setUpClass(cls):
        cls.v08 = v08_xbe()
        cls.final, cls.receipt = passer.apply(cls.v08)

    def test_late_allocation_moves_no_owner_and_neighbors_stay_applied(self):
        before = {(a["owner"], a["kind"]): a for a in space.layout(self.v08)["allocations"]}
        after = {(a["owner"], a["kind"]): a for a in space.layout(self.final)["allocations"]}
        for key, row in before.items():
            if key[0] != space.DIRECTORY_OWNER:
                self.assertEqual(after[key], row, key)
        self.assertEqual(set(after) - set(before), {(passer.OWNER, "code"), (passer.OWNER, "data")})
        self.assertEqual(len(self.final), len(self.v08))
        self.assertEqual(passer.status(self.final), "applied")
        self.assertEqual(reads.read_settings(self.final), reads.read_settings(self.v08))
        self.assertEqual(scrambles.status(self.final), scrambles.status(self.v08))
        from mod_editor.core import (nfl2k5_cpu_money_downs as money, nfl2k5_qb_accuracy as accuracy,
                                     nfl2k5_pass_protection as protection, nfl2k5_ball_carrier_ai as carriers)
        for module in (money, accuracy, protection, carriers):
            self.assertEqual(module.status(self.final), module.status(self.v08), module.__name__)


if __name__ == "__main__":
    unittest.main()
