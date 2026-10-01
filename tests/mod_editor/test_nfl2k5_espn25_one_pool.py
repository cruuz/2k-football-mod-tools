"""e1 (2026-09-23): "Historic moments: real rosters" composes with One-pool positions and the EDGE rename.

The One-pool reclassify (tools/nfl2k5_roster_reclassify.py, historic 4-3 rule) writes each historic player's position
byte (+0x35) and front-pool rank/side word (+0x28). The EDGE rename writes the 16-byte "Def End" placeholder
surnames. The real-rosters writer replaces names, jerseys and college indices. These tests prove, on the user's
retail resources, that the reclassify and the rosters writer commute byte for byte, that the module's one-pool pins
are exactly the reclassify's output, and that the rosters compile on the One-pool layout (with or without the EDGE
placeholders) lands on the pinned profile. The native part runs all 25 moments, with the real exit event between
them, on a practice squad + One-pool executable with the composed resources.

Offline evidence only; nothing here is a played game.
"""
import hashlib
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / "tests", ROOT / "tools"):
    sys.path.insert(0, str(path))
from mod_editor.core import nfl2k5_espn25_rosters as e  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from tests.mod_editor.test_nfl2k5_espn25_rosters import RETAIL  # noqa: E402
try:
    import nfl2k5_roster_reclassify as rc  # noqa: E402
    RECLASSIFY_ERROR = None
except ImportError as exc:
    RECLASSIFY_ERROR = str(exc)
try:
    from nfl2k5_espn25_in_game import LiveCPU, evidence  # noqa: E402
    NATIVE_ERROR = None
except ImportError as exc:  # Unicorn is optional
    NATIVE_ERROR = str(exc)

#: Optional private evidence: a disc built with "Historic moments: real rosters" (for example main's v7).
BUILT_DISC = os.environ.get("NFL2K5_E1_REAL_ROSTERS_DISC", "")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def reclassified(outer, raw):
    resource = rc.parse_resource(outer, 0, raw)
    moves, _ = rc.plan_resource(resource, {})
    body = bytearray(resource.body)
    rc.apply_moves(body, moves)
    return raw[:32] + bytes(body), [(m.player.offset, m.new_position, m.new_word) for m in moves if m.changed]


def with_edge_placeholders(raw):
    """The EDGE rename's disc change, applied in memory: every exact "Def End" surname slot becomes "Edge"."""
    doc = rr.RosterDocument(raw[32:])
    out = bytearray(raw)
    field = rr.FIELD_BY_NAME["last_name_pointer"]
    count = 0
    for p in doc.players:
        at = 32 + p.offset + field.offset
        target = at + struct.unpack_from("<i", raw, at)[0] - 1
        if raw[target:target + 16] == e.EDGE_PLACEHOLDER_BEFORE:
            out[target:target + 16] = e.EDGE_PLACEHOLDER_AFTER
            count += 1
    return bytes(out), count


class Retail:
    cached = None

    @classmethod
    def load(cls):
        if cls.cached is None:
            if RECLASSIFY_ERROR:
                raise unittest.SkipTest("reclassify tool unavailable: " + RECLASSIFY_ERROR)
            if not (RETAIL / "vc_53450030/0").is_file():
                raise unittest.SkipTest("user-owned USA pack 0 absent")
            manifest, _ = e.dataset()
            from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
            require_nfl_retail_packs(RETAIL)
            with rr._outer_image()(RETAIL) as archive:
                retail = {t["outer"]: archive.read_entry(t["outer"]) for t in manifest["resources"]}
            if e.status(retail) != "retail":
                raise unittest.SkipTest("USA historic resources differ from the pinned retail profile")
            applied, _ = e._compile_resources(retail)
            cls.cached = (manifest, retail, applied)
        return cls.cached


class OnePoolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest, cls.retail, cls.applied = Retail.load()

    def test_edge_constants_are_the_edge_owners_bytes(self):
        from mod_editor.core import nfl2k5_edge_rename as edge
        self.assertEqual(e.EDGE_PLACEHOLDER_BEFORE, edge.ROST_BEFORE)
        self.assertEqual(e.EDGE_PLACEHOLDER_AFTER, edge.ROST_AFTER)

    def test_pins_are_exactly_the_reclassify_output(self):
        self.assertEqual(set(e.ONE_POOL_PINS), {t["outer"] for t in self.manifest["resources"]})
        for t in self.manifest["resources"]:
            outer = t["outer"]
            with self.subTest(file=t["filename"]):
                base, _ = reclassified(outer, self.retail[outer])
                done, _ = reclassified(outer, self.applied[outer])
                self.assertEqual((sha(base), sha(done)), e.ONE_POOL_PINS[outer])

    def test_reclassify_and_real_rosters_commute_byte_for_byte(self):
        for t in self.manifest["resources"]:
            outer = t["outer"]
            with self.subTest(file=t["filename"]):
                base, base_moves = reclassified(outer, self.retail[outer])
                done, done_moves = reclassified(outer, self.applied[outer])
                self.assertTrue(base_moves)
                self.assertEqual(base_moves, done_moves)  # the reclassify reads nothing the rosters change
                combined = bytearray(base)
                for i, (a, b) in enumerate(zip(self.retail[outer], self.applied[outer])):
                    if a != b:
                        combined[i] = b
                self.assertEqual(bytes(combined), done)

    def test_compile_on_the_one_pool_layout_reaches_the_pinned_profile(self):
        one_pool = {o: reclassified(o, raw)[0] for o, raw in self.retail.items()}
        self.assertEqual(e.status(one_pool), "one_pool")
        output, receipt = e.apply(one_pool)
        self.assertEqual(e.status(output), "one_pool_applied")
        self.assertEqual((receipt["before"], receipt["after"], receipt["layout"]),
                         ("one_pool", "one_pool_applied", "one_pool"))
        for outer, raw in output.items():
            self.assertEqual(raw, reclassified(outer, self.applied[outer])[0])
        again, receipt = e.apply(output)
        self.assertEqual(again, output)
        self.assertTrue(receipt["already_applied"])

    def test_edge_placeholders_are_read_through_on_both_layouts(self):
        renamed_retail, renamed_pool, slots = {}, {}, 0
        for outer, raw in self.retail.items():
            renamed_retail[outer], count = with_edge_placeholders(raw)
            renamed_pool[outer], _ = with_edge_placeholders(reclassified(outer, raw)[0])
            slots += count
        self.assertGreater(slots, 0)
        self.assertEqual(e.status(renamed_retail), "retail")
        self.assertEqual(e.status(renamed_pool), "one_pool")
        self.assertEqual(e.apply(renamed_retail)[0], self.applied)
        self.assertEqual(e.status(e.apply(renamed_pool)[0]), "one_pool_applied")

    def test_mixed_layouts_and_partial_edges_refuse(self):
        mixed = dict(self.retail)
        first = next(iter(mixed))
        mixed[first] = reclassified(first, mixed[first])[0]
        self.assertEqual(e.status(mixed), "foreign")
        with self.assertRaisesRegex(e.Espn25RostersError, "missing, mixed or foreign"):
            e.apply(mixed)
        mixed = dict(self.applied)
        mixed[first] = reclassified(first, self.applied[first])[0]
        self.assertEqual(e.status(mixed), "foreign")

    def test_box_score_linebackers_keep_the_retail_formation_trio(self):
        """A 4-3 formation fields ILB rank 0, OLB rank 0 and OLB side 0 in the retail layout; the merged LB pool
        puts exactly those three first, so the reclassify does not change who plays linebacker."""
        for t in self.manifest["resources"]:
            outer = t["outer"]
            with self.subTest(file=t["filename"]):
                before = rr.RosterDocument(self.applied[outer][32:])
                after = rr.RosterDocument(reclassified(outer, self.applied[outer])[0][32:])
                def pick(doc, name, key):
                    rows = [p for p in doc.players if p.record.position_name == name and p.record.values[key] == 0]
                    return {(p.first, p.last) for p in rows[:1]}
                retail_trio = pick(before, "ILB", "depth_rank") | pick(before, "OLB", "depth_rank") | \
                    pick(before, "OLB", "depth_side")
                pooled = sorted((p for p in after.players if p.record.position_name == "ILB"),
                                key=lambda p: p.record.values["depth_rank"])
                self.assertEqual({(p.first, p.last) for p in pooled[:3]}, retail_trio)


class NativeTwentyFiveMomentsTests(unittest.TestCase):
    """All 25 moments, the exit event between them, on a practice squad + One-pool executable."""

    @classmethod
    def setUpClass(cls):
        if NATIVE_ERROR:
            raise unittest.SkipTest("Unicorn unavailable: " + NATIVE_ERROR)
        cls.manifest, cls.retail, cls.applied = Retail.load()
        from mod_editor.core import nfl2k5_throw_tuning as tt
        from mod_editor.core import nfl2k5_position_pools as pools
        payload = e.read_xbe(RETAIL)
        base, _ = tt._apply_all(payload, None, catch_slider=False, scheme_labels=True, practice_squad=True,
                                franchise_practice=True, depth_locks=True)
        cls.payload, _ = pools.apply(base, roster_has_olb=True)
        cls.resources, cls.context, cls.ids = evidence(RETAIL)
        composed = {o: with_edge_placeholders(reclassified(o, raw)[0])[0] for o, raw in cls.retail.items()}
        output, _ = e.apply(composed)
        cls.resources.update(output)

    def qb1(self, outer):
        doc = rr.RosterDocument(self.resources[outer][32:])
        return next((p.first, p.last) for p in doc.players
                    if p.record.position_name == "QB" and p.record.values["depth_rank"] == 0)

    def test_every_moment_loads_two_full_teams_after_the_exit_event(self):
        from mod_editor.core import nfl2k5_practice_squad as ps
        self.assertEqual(ps.status(self.payload), "applied")
        self.assertEqual(e.xbe_status(self.payload), "applied")
        cpu = LiveCPU(self.payload, self.resources, self.context, self.ids)
        by_moment = {m["moment"]: m for m in self.context["moments"]}
        for index in (*range(25), 0, 14, 0):
            with self.subTest(moment=index):
                before = len(cpu.imports)
                cpu.select(index)
                selected = cpu.selected()
                match = cpu.match()
                self.assertEqual([i["result"] for i in cpu.imports[before:]], [1, 1])
                self.assertNotEqual(selected["home"]["team"], selected["away"]["team"])
                self.assertEqual((selected["home"]["active"], selected["away"]["active"]), (53, 53))
                self.assertEqual(match["export_players"], 106)
                self.assertTrue(all(side["kit_exists"] for side in match["sides"].values()))
                for side in ("home", "away"):
                    qb = match["sides"][side]["quarterback"]
                    self.assertEqual((qb["first"], qb["last"]), self.qb1(by_moment[index][side]["outer"]))
                cpu.run(0x20C3C0)  # the details screen's exit event: release both teams
        self.assertTrue(all(r["pointers_after"] == 0 for r in cpu.releases))

    @unittest.skipUnless(BUILT_DISC and Path(BUILT_DISC).is_file(),
                         "optional built real-rosters disc absent (NFL2K5_E1_REAL_ROSTERS_DISC)")
    def test_built_disc_status_and_all_moments(self):
        self.assertEqual(e.image_status(BUILT_DISC), "applied")
        payload = e.read_xbe(BUILT_DISC)
        resources, context, ids = evidence(BUILT_DISC)
        self.assertIn(e.status({o: resources[o] for o in self.retail}), e.APPLIED_STATES)
        cpu = LiveCPU(payload, resources, context, ids)
        for index in (*range(25), 0, 14):
            with self.subTest(moment=index):
                before = len(cpu.imports)
                cpu.select(index)
                selected = cpu.selected()
                self.assertEqual([i["result"] for i in cpu.imports[before:]], [1, 1])
                self.assertNotEqual(selected["home"]["team"], selected["away"]["team"])
                self.assertEqual(cpu.match()["export_players"], 106)
                cpu.run(0x20C3C0)


if __name__ == "__main__":
    unittest.main()
