"""Independent formation-substitution gates, using authored and private books."""
from collections import Counter
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / "tests/mod_editor"):
    sys.path.insert(0, str(path))

from test_nfl2k5_depth_roles import fixture, RETAIL
from mod_editor.core import nfl2k5_depth_roles as roles
from mod_editor.core import nfl2k5_special_roles as special
from mod_editor.core import nfl2k5_play_library as lib
from mod_editor.core import nfl2k5_play_codec as codec
from mod_editor.core import nfl2k5_playbook_inspector as insp


def offense(codes, *, gun=False, second_gun=None, wide_hb=False):
    raw = bytearray(fixture(xs=((-15, 15, 9),) * (2 if second_gun is not None else 1)))
    raw[32 + insp.CATEGORY_BASE + 5:32 + insp.CATEGORY_BASE + 16] = bytes(codes)
    for index, shotgun in enumerate([gun] if second_gun is None else [gun, second_gun]):
        rec = lib.formation_record(raw[32:], index)
        rec.set_qb_alignment(shotgun)
        rec.set_position(0, 0, -600 if shotgun else -185)
        rec.set_position(10, 6 * codec.YD_CM if wide_hb else 0, -100 if wide_hb else -632)
        off = 32 + insp.FORMATION_BASE + index * insp.FORMATION_SIZE
        raw[off:off + insp.FORMATION_SIZE] = rec.to_bytes()
    return bytes(raw)


BASE = [0, 5, 37, 6, 7, 39, 9, 41, 8, 11, 10]


class ClassificationTests(unittest.TestCase):
    def test_base_shotgun_three_receiver_heavy_and_receiving_back(self):
        passing = BASE.copy()
        passing[9] = 73
        power = BASE.copy()
        power[6] = 40
        for raw, ordinal in ((offense(BASE), 0), (offense(BASE, gun=True), 1),
                             (offense(passing), 1), (offense(power), 2),
                             (offense(BASE, wide_hb=True), 1)):
            result = roles.normalise(raw)
            self.assertEqual(lib.category_positions(result.replacement[32:], 0)[10], 10 | ordinal << 5)
            self.assertTrue(result.report["special"]["gate"]["ok"])
            self.assertEqual(roles.normalise(result.replacement).replacement, result.replacement)

    def test_shared_base_and_shotgun_group_refuses_hb_without_changing_base(self):
        raw = offense(BASE, second_gun=True)
        result = roles.normalise(raw)
        self.assertEqual(result.replacement, raw)
        self.assertEqual(result.report["special"]["refused"][0]["refused_reason"], "shared_group_hb_classes_disagree")

    def test_geometry_conflicts_multiple_backs_and_power_passing_conflicts_refuse(self):
        conflict = bytearray(offense(BASE))
        off = 32 + insp.FORMATION_BASE + 4
        flags = struct.unpack_from("<I", conflict, off)[0]
        struct.pack_into("<I", conflict, off, flags | codec.FORMATION_FLAG_SHOTGUN)
        multiple = BASE.copy()
        multiple[9] = 42
        power = BASE.copy()
        power[6] = 40
        for raw, reason in ((bytes(conflict), "shotgun_flag_geometry_disagree"),
                            (offense(multiple), "multiple_halfbacks"),
                            (offense(power, gun=True), "passing_and_power_personnel")):
            result = roles.normalise(raw)
            self.assertEqual(result.replacement, raw)
            self.assertEqual(result.report["special"]["refused"][0]["refused_reason"], reason)


@unittest.skipUnless((RETAIL / "vc_53450030/0").is_file(), "private retail PLAY books required for SPECIAL census")
class RetailSpecialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.books = roles._resources(RETAIL)
        cls.results = {key: roles.normalise(raw) for key, raw in cls.books.items()}

    def test_retail_back_ordinals_and_special_personnel_are_measured_not_assumed(self):
        hist = Counter()
        exceptions = Counter()
        snaps = Counter()
        for key, raw in self.books.items():
            book = roles._parse(raw)
            for form in special.formations(raw, book):
                if form["offense"]:
                    for slot in form["hb_slots"]:
                        ordinal = form["codes"][slot] >> 5
                        hist[ordinal] += 1
                        if ordinal:
                            exceptions[book.book_name] += 1
                elif form["special"]:
                    self.assertEqual(len(form["snap_slots"]), 1)
                    snaps[form["codes"][form["snap_slots"][0]]] += 1
        self.assertEqual(hist, {0: 885, 1: 13, 2: 4, 3: 3})
        self.assertEqual(exceptions, {"MIN": 11, "PRACTICE": 9})
        self.assertEqual(snaps, {38: 72})  # second center already snaps every punt/FG/PAT

    def test_every_accepted_role_and_refused_slot_on_all_books(self):
        coverage = Counter()
        for key, result in self.results.items():
            raw = self.books[key]
            self.assertEqual(roles.book_status(raw), "retail")
            self.assertEqual(roles.book_status(result.replacement), "applied")
            for entry in result.report["special"]["entries"]:
                old = lib.category_positions(raw[32:], entry["group"])
                new = lib.category_positions(result.replacement[32:], entry["group"])
                if entry["role"] == "gadget" and entry["refused_reason"]:
                    # A refused gadget assignment leaves the independent
                    # X/Z/SLOT pass responsible for these receiver ordinals.
                    for group in roles._groups(raw, roles._parse(raw)):
                        if group["index"] == entry["group"] and not group["refused_reason"]:
                            old = group["after"]
                for slot, expected in entry["after"].items():
                    self.assertEqual(new[slot], old[slot] if entry["refused_reason"] else expected)
                if not entry["refused_reason"]:
                    coverage[entry["role"]] += len(entry["formations"])
        self.assertEqual(coverage["gunners"], 36)
        self.assertEqual(coverage["ls"], 72)
        self.assertGreater(coverage["3db"], 300)
        self.assertGreater(coverage["pwr"], 100)
        self.assertGreater(coverage["gadget"], 40)

    def test_gadget_audit_uses_handoff_nodes_and_reports_slot_conflicts(self):
        forms, plays, refused = 0, set(), Counter()
        for key, result in self.results.items():
            before = result.report["before_special"]
            forms += before["gadget_formations"]
            for f in before["formations"]:
                plays.update((key, p) for p in f["gadget_plays"])
            refused.update(e["refused_reason"] for e in before["refused"])
        self.assertEqual(forms, 242)
        self.assertGreater(len(plays), 100)
        self.assertGreater(refused["gadget_conflicts_with_x_z_slot_ordinals"], 0)
        self.assertGreater(refused["shared_group_gadget_carriers_disagree"], 0)

    def test_hb_and_gunner_tampering_are_foreign_and_reapply_is_idempotent(self):
        for key, result in self.results.items():
            raw = self.books[key]
            for entry in result.report["special"]["entries"]:
                if entry["role"] not in ("3db", "pwr", "gunners") or entry["refused_reason"]:
                    continue
                slot = next(iter(entry["after"]))
                off = 32 + insp.CATEGORY_BASE + entry["group"] * insp.CATEGORY_SIZE + 5 + slot
                for source in (raw, result.replacement):
                    changed = bytearray(source)
                    changed[off] ^= 0xE0
                    self.assertEqual(roles.book_status(bytes(changed)), "foreign")
            self.assertEqual(roles.normalise(result.replacement).replacement, result.replacement)
