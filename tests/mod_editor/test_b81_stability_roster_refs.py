"""b81 long-franchise stability: the thirteen references follow the roster on the disc (stability review
rev-pos3/REVIEW_STABILITY.md, Medium finding; coordinator's order to the [refs] helper, 2026-11-20).

The references R were measured on one roster, the base disc's franchise roster (ROST body sha256 70813bd9). A disc built
with another roster (a player's own edits, a total conversion, a roster update) got a clamped step at season 3 that is the
roster difference, not drift. Now every route that installs the stage (Build's own step, edit-sim-qb, update-v09)
measures the disc's own roster at rest with stability.S's starter rule and writes R x static(disc) / static(70813bd9) per
class. On roster 70813bd9 the references are exactly R, so that roster builds the same executable as before.

- RosterStatistic: the rule and the scaling on synthetic clubs (no private data). Shifting every Durability shifts the
  references in proportion; the calibration statistic gives the frozen R exactly.
- NativeWalkMatchesTheReplica: the Python walk equals stability.S's own walk (Unicorn) on a varied league, and the factor
  the piece computes from the written references is the model's, bit for bit.
- CalibrationRoster (private fixtures, NFL2K5_B81_STABILITY_FIXTURES): roster 70813bd9 on the base executable bda1e4a4
  gives Realistic 33cd2a36, what 6185ad6c0 gives; the same roster with every club player's Durability lowered by 10 gives
  references shifted in proportion; Retail restores every byte; a re-apply keeps the installed references.
- Routes: each route asks for the roster of its own disc (Build's step: the output disc; edit-sim-qb and update-v09: the
  source disc, which the copy keeps) and installs what that roster gives. The real private discs (the reviewed test disc,
  the released v0.9 disc) read back the calibration statistic.
- LineupRolesKeepTheReferences: the lineup owner's re-apply of the option keeps the installed references.

Known limit (stated in REVIEW_ME and the release notes): a roster loaded from a save inside the game, after the disc was
built, still uses the disc's references.
"""
import hashlib
import inspect
import os
from pathlib import Path
import random
import struct
import tempfile
import unittest
from unittest.mock import patch

from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_sim_qb_injuries as qb, nfl2k5_sim_qb_injuries_code as rules
from tests.mod_editor.test_b81_sim_pos_injuries_native import (
    POSITION_RULE, STABILITY_CLASSES, ZERO_K, StabilityGate, factor_bits)

CALIBRATION_ROSTER = "70813bd95d1265b40009fb611569e2e1ffcce02bf17a5f73476e8f55ffa3d157"
BASE_XBE = "bda1e4a408f19cc30f0916e03b158b0accc46e0ccb6a39e134c1ce79ba3ab6ea"
# Realistic on bda1e4a4 with 6185ad6c0's own code (git archive of that commit; pos3/work/stability/merge/apply_realistic.py)
# was 33cd2a36. With the frozen combined levers (merge queue item 15: QB_CHANCE_SCALE 1.06, breakaway stop 68) it is
# aa1e29e1: 731 bytes differ, all in the QB bank's tables, the scoring site's stop byte, the registry hash and digests.
REALISTIC_AT_6185AD6C0 = "aa1e29e1846ae8e094631283b1a122f3cf3a6dc95a5f617bbf7a19a6eb9669c7"
V09_ROSTER = "8d2b2f50aa19679e4e3a6a783d7137acef96a5975b2ce22bef8ede037c26f42c"
SHIFT = 10
# sha256 of repr((STABILITY_REFERENCE, STABILITY_CALIBRATION, STABILITY_CALIBRATION_ROSTER, STABILITY_REFERENCE_ROSTER)).
PAIR_PIN = "284865cb52b8f5f3bc6d35c2a506c08c02a8be374591ae6b82511ecd53839128"


def _sha(data):
    return hashlib.sha256(bytes(data)).hexdigest()


def _float32(values):
    return struct.unpack(f"<{len(values)}f", struct.pack(f"<{len(values)}f", *values))


def synthetic_durability(generator, position):
    """A Durability like the shipped roster's: K - Durability within 8 points of the calibration mean of the position's
    class (so a league of them is inside the reference bound, and 5 points either way keep every player below K);
    kickers and punters anywhere from 60 to 90."""
    index = rules.STABILITY_POSITION_CLASS[position]
    if index is None:
        return generator.randrange(60, 91)
    total, count = rules.STABILITY_CALIBRATION[index]
    return rules.STABILITY_ZERO_POINTS[index] - round(total / count) + generator.randrange(-8, 9)


def synthetic_clubs(seed):
    """32 clubs of 65 listed players: every stored position at ranks 0-3, shuffled and cut to the list limit."""
    generator = random.Random(seed)
    clubs = []
    for _ in range(32):
        players = [(position, rank, synthetic_durability(generator, position)) for position in range(17) for rank in range(4)]
        generator.shuffle(players)
        clubs.append(players[:rules.STABILITY_MAX_LISTED])
    return clubs


def shifted_clubs(clubs, shift):
    return [[(position, rank, max(0, durability + shift)) for position, rank, durability in club] for club in clubs]


def roster_with_lower_durability(body, shift=SHIFT):
    """The roster body as a document with every listed player of clubs 0-31 at Durability - shift (kept to 0-99)."""
    from mod_editor.core import nfl2k5_roster_records as rosters
    document = rosters.load_body(body)
    for club in range(rules.STABILITY_CLUBS):
        for player in document.team_players(club):
            player.record.set("durability", min(99, max(0, player.record.values["durability"] - shift)))
    return document


def roster_without_fullbacks(body, shift=0):
    """Every club fullback moved to halfback (and every Durability shift lower): a roster with no fullback starters."""
    document = roster_with_lower_durability(body, shift)
    for club in range(rules.STABILITY_CLUBS):
        for player in document.team_players(club):
            if player.record.values["position"] == 8:
                player.record.set("position", 7)
    return document


def private_fixtures(test):
    root = os.environ.get("NFL2K5_B81_STABILITY_FIXTURES")
    xbe, body = Path(root or "") / "default.xbe", Path(root or "") / "rost.body"
    if not root or not xbe.is_file() or not body.is_file():
        test.skipTest("private stability fixtures (default.xbe bda1e4a4, rost.body 70813bd9) are absent")
    xbe, body = xbe.read_bytes(), body.read_bytes()
    test.assertEqual((_sha(xbe), _sha(body)), (BASE_XBE, CALIBRATION_ROSTER))
    return xbe, body


class RosterStatistic(unittest.TestCase):
    def test_the_calibration_statistic_gives_the_frozen_references_exactly(self):
        self.assertEqual(rules.stability_reference_for(rules.STABILITY_CALIBRATION), rules.STABILITY_REFERENCE)
        # The same means from other counts are still exactly R.
        doubled = tuple((2 * total, 2 * count) for total, count in rules.STABILITY_CALIBRATION)
        self.assertEqual(rules.stability_reference_for(doubled), rules.STABILITY_REFERENCE)

    def test_every_durability_shifted_shifts_the_references_in_proportion(self):
        clubs = synthetic_clubs(81071)
        base = rules.stability_starters(clubs)
        self.assertTrue(all(count >= rules.STABILITY_MIN_STARTERS for _, count in base))
        before = rules.stability_reference_for(base)
        for index, ((total, count), (total0, count0), frozen) in enumerate(
                zip(base, rules.STABILITY_CALIBRATION, rules.STABILITY_REFERENCE)):
            self.assertAlmostEqual(before[index], frozen * (total / count) / (total0 / count0), delta=1e-12)
        for shift in (-SHIFT, -3, 5):
            with self.subTest(shift=shift):
                moved = rules.stability_starters(shifted_clubs(clubs, shift))
                # Every Durability stays below its zero point, so each starter's gap moves by exactly -shift.
                self.assertEqual(moved, tuple((total - shift * count, count) for total, count in base))
                after = rules.stability_reference_for(moved)
                for index, ((total, count), (total1, _)) in enumerate(zip(base, moved)):
                    self.assertAlmostEqual(after[index] / before[index], total1 / total, delta=1e-12)
                    self.assertEqual(after[index] > before[index], shift < 0)

    def test_the_rule_counts_listed_starters_of_the_thirteen_classes_only(self):
        clubs = [[] for _ in range(32)]
        clubs[0] = [(14, 0, 80), (14, 1, 90), (14, 2, 10),      # tackles: ranks 0 and 1 count, rank 2 does not
                    (1, 0, 10), (2, 0, 10),                      # kicker and punter: never counted
                    (10, 2, 99), (11, 2, 99), (11, 3, 5),        # OLB and ILB rank 2 count (3 each), rank 3 does not
                    (0, 0, 120), (17, 0, 10)]                    # QB above K counts as 0; position 17 is not a position
        starters = rules.stability_starters(clubs)
        self.assertEqual(starters[0], (110 - 80 + 110 - 90, 2))
        self.assertEqual(starters[9], (2, 2))
        self.assertEqual(starters[12], (0, 1))
        self.assertEqual(sum(count for _, count in starters), 5)
        at = rules.LABELS["stab_starters"]
        self.assertEqual(tuple(rules._TEMPLATE[at:at + 17]), (1, 0, 0, 3, 3, 1, 1, 2, 1, 1, 3, 3, 1, 2, 2, 2, 2))
        self.assertEqual({position: (index, rules._TEMPLATE[at + position]) for position, index
                          in enumerate(rules.STABILITY_POSITION_CLASS) if index is not None}, POSITION_RULE)

    def test_a_small_class_keeps_r_and_a_measurement_that_looks_wrong_is_refused(self):
        statistic = list(rules.STABILITY_CALIBRATION)
        statistic[7] = (300, 7)          # fullback: 1 to 7 starters, which the game leaves at 1.0: frozen R
        statistic[0] = (3 * 1077, 128)   # tackle: 1.5 times the calibration mean
        reference = rules.stability_reference_for(statistic)
        self.assertEqual(reference[7], rules.STABILITY_REFERENCE[7])
        self.assertEqual(reference[0], 1.5 * rules.STABILITY_REFERENCE[0])
        self.assertEqual(reference[1:7] + reference[8:], rules.STABILITY_REFERENCE[1:7] + rules.STABILITY_REFERENCE[8:])
        # A class the game leaves at 1.0 keeps its R and the other twelve are still derived (review finding 3).
        for label, (index, row) in {"no fullback starters": (7, (0, 0)),
                                    "every center at or above K (zero sum)": (2, (0, 32))}.items():
            with self.subTest(label):
                statistic = list(rules.STABILITY_CALIBRATION)
                statistic[index] = row
                statistic[0] = (3 * 1077, 128)
                reference = rules.stability_reference_for(statistic)
                self.assertEqual(reference[index], rules.STABILITY_REFERENCE[index])
                self.assertEqual(reference[0], 1.5 * rules.STABILITY_REFERENCE[0])
        wrong = {"no starters in any class": [(0, 0)] * 13,
                 "a mean above K": (2, (111 * 32, 32)),
                 "a mean that is not a number": (5, (float("nan"), 96)),
                 "an infinite mean": (5, (float("inf"), 96)),
                 "a negative count": (5, (100, -1))}
        for label, change in wrong.items():
            with self.subTest(label), self.assertRaises(ValueError):
                bad = list(rules.STABILITY_CALIBRATION)
                if isinstance(change, list):
                    bad = change
                else:
                    bad[change[0]] = change[1]
                rules.stability_reference_for(bad)

    def test_a_reference_outside_the_bound_is_refused(self):
        self.assertEqual(rules.STABILITY_REFERENCE_BOUND, (0.25, 4.0))
        total, count = rules.STABILITY_CALIBRATION[3]                      # defensive ends, 64 starters
        for factor, accepted in ((4.0, True), (4.0625, False), (0.25, True), (0.234375, False), (2.5, True)):
            with self.subTest(factor=factor):
                statistic = list(rules.STABILITY_CALIBRATION)
                statistic[3] = (round(total * factor * 64), count * 64)    # exactly factor x the calibration mean
                if accepted:
                    reference = rules.stability_reference_for(statistic)
                    self.assertEqual(reference[3], float(rules.STABILITY_REFERENCE[3] * factor))
                else:
                    with self.assertRaises(rules.StabilityOutOfRange):
                        rules.stability_reference_for(statistic)
        clubs = synthetic_clubs(81074)
        rules.stability_reference_for(rules.stability_starters(clubs))

    def test_the_frozen_references_and_their_calibration_statistic_change_together(self):
        """R (measured in game) and STABILITY_CALIBRATION (its roster at rest) are one pair: re-measure both on the same
        roster in the same commit, then update this pin (review finding 6)."""
        self.assertEqual(rules.STABILITY_REFERENCE_ROSTER, rules.STABILITY_CALIBRATION_ROSTER)
        pair = repr((rules.STABILITY_REFERENCE, rules.STABILITY_CALIBRATION, rules.STABILITY_CALIBRATION_ROSTER,
                     rules.STABILITY_REFERENCE_ROSTER)).encode()
        self.assertEqual(hashlib.sha256(pair).hexdigest(), PAIR_PIN,
                         "R and STABILITY_CALIBRATION must be re-measured together on one roster (then update PAIR_PIN)")
        # The static-to-seasons-1-2 ratio of the calibration roster stays near 1 in every class (0.96 to 1.07).
        for name, frozen, (total, count) in zip(rules.STABILITY_CLASS_NAMES, rules.STABILITY_REFERENCE,
                                                rules.STABILITY_CALIBRATION):
            self.assertTrue(0.9 < frozen / (total / count) < 1.1, name)

    def test_a_league_the_walk_cannot_read_is_refused(self):
        with self.assertRaises(ValueError):
            rules.stability_starters([[]] * 31)
        clubs = [[] for _ in range(32)]
        clubs[5] = [(3, 0, 80)] * (rules.STABILITY_MAX_LISTED + 1)
        with self.assertRaises(ValueError):
            rules.stability_starters(clubs)
        with self.assertRaises(ValueError):
            rules.stability_reference_for(rules.STABILITY_CALIBRATION[:12])

    def test_invalid_references_are_refused_by_the_installer(self):
        for bad in ((0.0,) * 13, (256.0,) * 13, (float("nan"),) * 13, (20.0,) * 12, ("20",) * 13):
            with self.subTest(bad=bad[:1] + (len(bad),)), self.assertRaises(qb.SimQbInjuriesError):
                qb._reference32(bad)


class NativeWalkMatchesTheReplica(StabilityGate):
    """stability.S's walk over a varied league equals stability_starters on the same lists, and with the references
    stability_reference_for writes, the factor the piece computes is the model's bit for bit."""

    def test_the_replica_walk_and_the_written_references_match_the_piece(self):
        generator = random.Random(81072)
        for club in range(32):
            for _ in range(generator.randrange(40, rules.STABILITY_MAX_LISTED + 1)):
                position = generator.randrange(17)
                durability = synthetic_durability(generator, position) + generator.choice((0, 0, 0, 0, -12, 25))
                self.league.player(club, position, generator.randrange(5), max(0, durability),
                                   noise=generator.randrange(1 << 16))
            for _ in range(3):           # off the list (IR, released): not walked
                self.league.player(club, 14, 0, 1, listed=False)
        self.install()
        clubs = [[(entry["position"], entry["word"] >> 10 & 7, entry["durability"]) for entry in self.league.lists[club]]
                 for club in range(32)]
        starters = rules.stability_starters(clubs)
        self.assertEqual(tuple(zip(*self.league.model())), starters)
        reference = rules.stability_reference_for(starters)
        self.assertNotEqual(reference, rules.STABILITY_REFERENCE)
        self.load_rate(rules.DEFAULT_RATE, reference=reference)
        factors = self.stability(2)
        self.assertEqual(list(self.table("stab_sum", STABILITY_CLASSES)), [total for total, _ in starters])
        self.assertEqual(list(self.table("stab_count", STABILITY_CLASSES)), [count for _, count in starters])
        written = _float32(reference)
        self.assertEqual(factors, [factor_bits(count, total, r) for (total, count), r in zip(starters, written)])
        # At rest the factor is R / static(calibration roster) per class: the roster difference itself is gone.
        for index, ((total0, count0), frozen) in enumerate(zip(rules.STABILITY_CALIBRATION, rules.STABILITY_REFERENCE)):
            value = struct.unpack("<f", struct.pack("<I", factors[index]))[0]
            self.assertAlmostEqual(value, frozen * count0 / total0, delta=2e-6)
        self.assertEqual(ZERO_K, rules.STABILITY_ZERO_POINTS)


class CalibrationRoster(unittest.TestCase):
    def test_the_calibration_roster_gives_the_frozen_references_and_the_same_executable(self):
        xbe, body = private_fixtures(self)
        starters, reference = qb.roster_stability(body)
        self.assertEqual(starters, rules.STABILITY_CALIBRATION)
        self.assertEqual(reference, rules.STABILITY_REFERENCE)
        realistic, _ = qb.apply(xbe, "realistic", reference=reference)
        self.assertEqual(_sha(realistic), REALISTIC_AT_6185AD6C0)
        self.assertEqual(qb.apply(xbe, "realistic")[0], realistic)
        for rate in (0, 100):
            with self.subTest(custom_rate=rate):
                self.assertEqual(qb.apply(xbe, "custom", custom_rate=rate, reference=reference)[0],
                                 qb.apply(xbe, "custom", custom_rate=rate)[0])

    def test_lower_durability_shifts_the_references_and_retail_restores_every_byte(self):
        xbe, body = private_fixtures(self)
        document = roster_with_lower_durability(body)
        starters, reference = qb.roster_stability(document)
        # Every starter of the shipped roster is rated at least 10 and below his zero point: each gap grows by 10.
        self.assertEqual(starters, tuple((total + SHIFT * count, count) for total, count in rules.STABILITY_CALIBRATION))
        for index, ((total0, count0), frozen) in enumerate(zip(rules.STABILITY_CALIBRATION, rules.STABILITY_REFERENCE)):
            self.assertAlmostEqual(reference[index], frozen * (total0 + SHIFT * count0) / total0, delta=1e-9)
        frozen_install = qb.apply(xbe, "realistic")[0]
        blank = qb.apply(frozen_install, "retail")[0]
        for mode, rate in (("realistic", .310), ("custom", 0), ("custom", 100)):
            with self.subTest(mode=mode, custom_rate=rate):
                result, _ = qb.apply(xbe, mode, custom_rate=rate, reference=reference)
                self.assertNotEqual(result, qb.apply(xbe, mode, custom_rate=rate)[0])
                self.assertEqual(qb.installed_reference(result), _float32(reference))
                bank, = (row for row in qb.space.layout(result)["allocations"] if row["owner"] == qb.OWNER)
                from mod_editor.core.nfl2k5_cave_oracle import XbeImage
                raw = XbeImage(result).read(bank["va"] + rules.LABELS["stab_reference"], 52)
                self.assertEqual(raw, struct.pack("<13f", *reference))
                # Retail restores every byte, whatever references were installed.
                self.assertEqual(qb.apply(result, "retail")[0], blank)
                self.assertEqual(qb.physical_view(result), blank)
                # A re-apply without a roster keeps them; another rate keeps them; a roster replaces them.
                self.assertEqual(qb.apply(result, mode, custom_rate=rate)[0], result)
                other = qb.apply(result, "custom", custom_rate=1.5)[0]
                self.assertEqual(qb.installed_reference(other), _float32(reference))
                self.assertEqual(qb.apply(result, "realistic", reference=rules.STABILITY_REFERENCE)[0], frozen_install)
                self.assertEqual(qb.read_settings(result)["revision"], 4)


class Routes(unittest.TestCase):
    """Each route asks for its own disc's roster and installs what that roster gives."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)

    def lowered(self, body):
        document = roster_with_lower_durability(body)
        return document, qb.roster_stability(document)[1]

    def _assert_copy(self, copy, receipt, expected):
        """b81 integration (qb34 merged): the edit also installs the quarterback room on the copy (injuries above zero
        carry its floor), so the copy is the route's quarterback executable (``expected``, checked by its hash) plus
        the room, and it holds the same injury references as ``expected``."""
        written = copy.read_bytes()
        self.assertEqual(receipt["sim_qb_source_update"]["result_sha256"], _sha(expected))
        room = receipt["qb_room_source_update"]
        self.assertEqual(room["level"], "realistic")
        self.assertEqual(_sha(written), room["result_sha256"])
        self.assertEqual(qb.installed_reference(written), qb.installed_reference(expected))
        self.assertIsNotNone(qb.installed_reference(written))

    def fake_disc(self, disc, document):
        asked = []

        def read(path):
            asked.append(Path(path))
            return document if Path(path) == Path(disc) else None
        return asked, patch.object(mod_build, "_disc_roster", side_effect=read)

    def test_build_step_measures_the_output_disc(self):
        xbe, body = private_fixtures(self)
        document, reference = self.lowered(body)
        target = self.folder / "output.xiso.iso"
        target.write_bytes(xbe)                       # the output disc's executable; its roster comes from _disc_roster
        plan = mod_build.BuildPlan(str(self.folder / "retail.iso"), str(target), console_memory=128,
                                   sim_qb_injuries="realistic", sim_realism=True, k128_memory=True)
        asked, seam = self.fake_disc(target, document)
        receipt = {"steps": [], "result": {}}
        with seam:
            mod_build._apply_sim_qb_injuries(plan, target, receipt, lambda *_: None)
        self.assertEqual(asked, [target])
        written = target.read_bytes()
        self.assertEqual(written, qb.apply(xbe, "realistic", reference=reference)[0])
        self.assertEqual(qb.installed_reference(written), _float32(reference))
        step, = receipt["steps"]
        self.assertEqual(step["stability_reference"]["source"], "disc roster")
        self.assertEqual(step["stability_reference"]["roster_sha256"], _sha(document.body))
        self.assertEqual(step["stability_reference"]["reference"], list(reference))
        # In a full build the step runs on the output disc after the last writer of its main roster.
        source = inspect.getsource(inspect.unwrap(mod_build._build))
        option = source.index("_apply_sim_qb_injuries(plan, target")
        for writer in ("_apply_champions_history(plan, target", "_apply_coach_carousel_pool(plan, target",
                       "nfl2k5_roster_ages.apply_image(target)", "_apply_lineup_roles(plan, target"):
            self.assertLess(source.index(writer), option, writer)
        self.assertNotIn("roster", source[option:source.index('_step("final_checks")', option)].replace(
            "_apply_sim_qb_injuries", ""))

    def test_edit_sim_qb_measures_the_source_disc(self):
        xbe, body = private_fixtures(self)
        document, reference = self.lowered(body)
        source = self.folder / "built.xiso.iso"
        plan = mod_build.sim_qb_disc_edit(str(source), str(self.folder / "copy.iso"), "realistic")
        asked, seam = self.fake_disc(source, document)
        receipt = {}
        with seam:
            self.assertTrue(mod_build._edit_installed_sim_qb(plan, source, self.folder / "copy.iso", xbe, receipt,
                                                             lambda *_: None, preflight=True, consume=False,
                                                             reference=None))
        self.assertEqual(asked, [source])
        # combined levers: the edit also updates the disc's legacy pass protection to this release's centre float
        from mod_editor.core import nfl2k5_pass_protection as pressure
        expected = mod_build._cpu_kick_aim_with_kicking(
            qb.apply(pressure.apply(xbe)[0], "realistic", reference=reference)[0])[0]
        update = receipt["sim_qb_source_update"]
        self.assertEqual(update["result_sha256"], _sha(expected))
        self.assertEqual(update["stability_reference"]["reference"], list(reference))
        self.assertFalse((self.folder / "copy.iso").exists())
        # The whole route: the copy gets those bytes, and the compaction still gets its own reference disc (the route's
        # `reference` argument; a first version reused that name for the references and the real run failed there).
        copy, compaction = self.folder / "copy.iso", []
        retail_reference = self.folder / "retail-reference.iso"
        def copied(src, dst, receipt, *_):
            Path(dst).write_bytes(xbe)
            receipt.setdefault("steps", [])
        full = {}
        with seam, patch.object(mod_build, "_copy_private_build_source", side_effect=copied), \
                patch.object(mod_build, "_compact_build_disc", side_effect=lambda *args: compaction.append(args)), \
                patch.object(mod_build, "inspect", return_value={}), \
                patch.object(mod_build, "_verify_finished_game_disc", return_value=None):
            self.assertTrue(mod_build._edit_installed_sim_qb(plan, source, copy, xbe, full, lambda *_: None,
                                                             preflight=False, consume=False,
                                                             reference=retail_reference))
        self._assert_copy(copy, full, expected)
        self.assertEqual([args[:2] for args in compaction], [(copy, retail_reference)])

    def test_update_v09_measures_the_released_disc(self):
        disc = os.environ.get("NFL2K5_V09_XISO")
        if not disc or not Path(disc).is_file():
            self.skipTest("the released v0.9 disc image is absent")
        _, body = private_fixtures(self)
        document, reference = self.lowered(body)
        written = []
        verify = mod_build._verify_sim_qb_injuries

        def keep(plan, module, payload):
            written.append(payload)
            return verify(plan, module, payload)
        plan = mod_build.v09_disc_update(disc, str(self.folder / "copy.iso"), sim_qb_injuries="realistic")
        release = mod_build._v09_reference(Path(disc), mod_build._xbe_bytes(Path(disc)))
        asked, seam = self.fake_disc(disc, document)
        with seam, patch.object(mod_build, "_verify_sim_qb_injuries", new=keep), \
                patch("mod_editor.core.modpack.hash_file", return_value=release["image_sha256"]):
            receipt = mod_build._update_v09_disc(plan, lambda *_: None, preflight=True, project=False)
        self.assertEqual(asked, [Path(disc)])
        self.assertEqual(qb.installed_reference(written[-1]), _float32(reference))
        self.assertEqual(receipt["v09_stability_reference"]["reference"], list(reference))

    def test_the_real_discs_read_their_own_roster(self):
        cases = (("NFL2K5_B81_REVIEWED_TEST_DISC", CALIBRATION_ROSTER), ("NFL2K5_V09_XISO", V09_ROSTER))
        if any(not Path(os.environ.get(variable, "")).is_file() for variable, _ in cases):
            self.skipTest("the private reviewed test disc and the released v0.9 disc are absent")
        for variable, roster in cases:
            with self.subTest(disc=variable):
                disc = os.environ[variable]
                plan = mod_build.sim_qb_disc_edit(disc, str(self.folder / "copy.iso"), "realistic")
                reference, record = mod_build._sim_qb_stability(plan, qb, disc)
                self.assertEqual((record["source"], record["roster_sha256"]), ("disc roster", roster))
                # Both rosters have the calibration roster's starters and Durability: the frozen references.
                self.assertEqual(tuple(map(tuple, record["starters"])), rules.STABILITY_CALIBRATION)
                self.assertEqual(reference, rules.STABILITY_REFERENCE)
        plan = mod_build.sim_qb_disc_edit("x.iso", "y.iso", "retail")
        self.assertEqual(mod_build._sim_qb_stability(plan, qb, "x.iso"), (None, None))

    def test_a_roster_that_cannot_be_measured_or_looks_wrong_gives_the_frozen_references_and_a_sentence(self):
        _, body = private_fixtures(self)
        from mod_editor.core import nfl2k5_roster_records as rosters
        plan = mod_build.sim_qb_disc_edit("x.iso", "y.iso", "realistic")
        bare = self.folder / "default.xbe"
        bare.write_bytes(b"\0" * 4096)
        damaged = rosters.load_body(body)
        damaged.teams[3].clean_parse = False             # a club whose count byte disagrees with its pointers
        nobody = rosters.load_body(body)
        for club in range(32):
            for player in nobody.team_players(club):
                player.record.set("depth_rank", 7)       # no starter in any class
        notes = mod_build.SIM_QB_STABILITY_NOTES
        cases = {
            "a bare executable": (None, None, None),
            "an unreadable roster": (None, rosters.RosterRecordError("foreign roster"), "unreadable"),
            "an exception in the replica": (rosters.load_body(body), None, "unreadable"),
            "a damaged club list": (damaged, None, "unreadable"),
            "no starters in any class": (nobody, None, "unreadable"),
            "a reference outside the bound": (roster_with_lower_durability(body, -25), None, "out_of_range"),
        }
        for label, (document, error, note) in cases.items():
            with self.subTest(label):
                seam = (patch.object(mod_build, "_disc_roster", side_effect=error) if error is not None
                        else patch.object(mod_build, "_disc_roster", return_value=document) if document is not None
                        else patch.object(mod_build, "_disc_roster", wraps=mod_build._disc_roster))
                replica = (patch.object(qb, "roster_stability", side_effect=KeyError("durability"))
                           if label == "an exception in the replica" else patch.object(qb, "_require", wraps=qb._require))
                with seam, replica:
                    reference, record = mod_build._sim_qb_stability(plan, qb, bare)
                    custom0, quiet = mod_build._sim_qb_stability(
                        mod_build.sim_qb_disc_edit("x.iso", "y.iso", "custom", custom_rate=0), qb, bare)
                self.assertEqual(reference, rules.STABILITY_REFERENCE)
                self.assertEqual(record["source"], "frozen calibration references")
                self.assertTrue(record["reason"])
                # The sentence says which case it is; none for a bare executable or Custom 0 percent (stage off).
                self.assertEqual(record.get("note"), notes.get(note))
                self.assertEqual((custom0, quiet.get("note")), (rules.STABILITY_REFERENCE, None))
        self.assertEqual(set(notes), {"unreadable", "out_of_range"})
        for text in notes.values():
            self.assertEqual(text.count(". "), 0)                                   # one sentence each
            self.assertIn("third season", text)

    def test_a_roster_without_fullbacks_keeps_that_class_and_measures_the_rest(self):
        _, body = private_fixtures(self)
        plan = mod_build.sim_qb_disc_edit("x.iso", "y.iso", "realistic")
        document = roster_without_fullbacks(body, SHIFT)
        with patch.object(mod_build, "_disc_roster", return_value=document):
            reference, record = mod_build._sim_qb_stability(plan, qb, self.folder / "x.iso")
        self.assertEqual(record["source"], "disc roster")
        self.assertNotIn("note", record)
        self.assertEqual(record["starters"][7], [0, 0])
        self.assertEqual(reference[7], rules.STABILITY_REFERENCE[7])
        _, lowered = self.lowered(body)
        self.assertEqual(reference[:4] + reference[5:7] + reference[8:], lowered[:4] + lowered[5:7] + lowered[8:])
        self.assertNotEqual(reference[4], rules.STABILITY_REFERENCE[4])            # halfbacks still measured

    def test_every_route_falls_back_to_the_frozen_references_with_the_sentence(self):
        xbe, body = private_fixtures(self)
        from mod_editor.core import nfl2k5_roster_records as rosters
        _, shifted = self.lowered(body)
        treated = qb.apply(xbe, "realistic", reference=shifted)[0]       # a disc whose option holds other references
        frozen = qb.apply(xbe, "realistic")[0]
        note = mod_build.SIM_QB_STABILITY_NOTES["unreadable"]
        unreadable = patch.object(mod_build, "_disc_roster", side_effect=rosters.RosterRecordError("foreign roster"))
        # Build's own step: the frozen references replace the installed ones; the report gets the sentence.
        target = self.folder / "output.xiso.iso"
        target.write_bytes(treated)
        plan = mod_build.BuildPlan(str(self.folder / "retail.iso"), str(target), console_memory=128,
                                   sim_qb_injuries="realistic", sim_realism=True, k128_memory=True)
        receipt, said = {"steps": [], "result": {}}, []
        with unreadable:
            mod_build._apply_sim_qb_injuries(plan, target, receipt, lambda text, *_: said.append(text))
        self.assertEqual(target.read_bytes(), frozen)
        self.assertEqual(receipt["user_notes"], [note])
        self.assertEqual(receipt["steps"][0]["user_notes"], [note])
        self.assertIn(note, said)
        # edit-sim-qb, the whole route with the copy and compaction stubbed.
        source, copy = self.folder / "built.xiso.iso", self.folder / "copy.iso"
        plan = mod_build.sim_qb_disc_edit(str(source), str(copy), "realistic")

        def copied(src, dst, receipt, *_):
            Path(dst).write_bytes(treated)
            receipt.setdefault("steps", [])
        receipt = {}
        with unreadable, patch.object(mod_build, "_copy_private_build_source", side_effect=copied), \
                patch.object(mod_build, "_compact_build_disc", return_value=None), \
                patch.object(mod_build, "inspect", return_value={}), \
                patch.object(mod_build, "_verify_finished_game_disc", return_value=None):
            self.assertTrue(mod_build._edit_installed_sim_qb(plan, source, copy, treated, receipt, lambda *_: None,
                                                             preflight=False, consume=False, reference=None))
        from mod_editor.core import nfl2k5_pass_protection as pressure   # combined levers: the legacy centre updated
        self._assert_copy(copy, receipt, mod_build._cpu_kick_aim_with_kicking(pressure.apply(frozen)[0])[0])
        # The sentence once, next to the floor's own notes (practice squad merge: this disc's earlier economy is
        # upgraded in place for the floor, and the report says so).
        floor_notes = receipt["qb_room_source_update"].get("added") or []
        self.assertEqual(sorted(receipt["user_notes"]), sorted(floor_notes + [note]))
        self.assertEqual(receipt["user_notes"].count(note), 1)
        self.assertEqual(receipt["sim_qb_source_update"]["stability_reference"]["note"], note)
        # update-v09 (released disc, preflight): the expected bytes carry the frozen references and the receipt says so.
        disc = os.environ.get("NFL2K5_V09_XISO")
        if not disc or not Path(disc).is_file():
            self.skipTest("the released v0.9 disc image is absent")
        written, verify = [], mod_build._verify_sim_qb_injuries

        def keep(plan, module, payload):
            written.append(payload)
            return verify(plan, module, payload)
        plan = mod_build.v09_disc_update(disc, str(self.folder / "v09-copy.iso"), sim_qb_injuries="realistic")
        release = mod_build._v09_reference(Path(disc), mod_build._xbe_bytes(Path(disc)))
        with unreadable, patch.object(mod_build, "_verify_sim_qb_injuries", new=keep), \
                patch("mod_editor.core.modpack.hash_file", return_value=release["image_sha256"]):
            receipt = mod_build._update_v09_disc(plan, lambda *_: None, preflight=True, project=False)
        self.assertEqual(qb.installed_reference(written[-1]), _float32(rules.STABILITY_REFERENCE))
        self.assertEqual(receipt["v09_stability_reference"]["note"], note)


class RosterEditorDiscCopy(unittest.TestCase):
    """The roster editor's Save disc copy changes a built disc's roster; it now measures the copy's roster again and
    rewrites only the references of its installed option, with the same fail safe (review finding 1)."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)

    def test_the_rewrite_changes_only_the_references(self):
        xbe, body = private_fixtures(self)
        document = roster_with_lower_durability(body)
        _, lowered = qb.roster_stability(document)
        frozen_install = qb.apply(xbe, "realistic")[0]
        for mode, rate in (("realistic", .310), ("custom", 0), ("custom", 1.5)):
            with self.subTest(mode=mode, custom_rate=rate):
                before = qb.apply(xbe, mode, custom_rate=rate)[0]
                copy = self.folder / f"{mode}-{rate}.xbe"
                copy.write_bytes(before)
                with patch.object(mod_build, "_disc_roster", return_value=document):
                    record = mod_build.restabilize_sim_qb_disc(copy)
                after = copy.read_bytes()
                self.assertEqual((record["source"], record["changed"]), ("disc roster", True))
                self.assertEqual(after, qb.apply(xbe, mode, custom_rate=rate, reference=lowered)[0])
                self.assertEqual(qb.read_settings(after), qb.read_settings(before))
                self.assertEqual(qb.apply(after, "retail")[0], qb.apply(frozen_install, "retail")[0])
                with patch.object(mod_build, "_disc_roster", return_value=document):
                    again = mod_build.restabilize_sim_qb_disc(copy)
                self.assertEqual((again["changed"], copy.read_bytes()), (False, after))
        # No current option: nothing to do, the executable stays as it is.
        retail = self.folder / "retail.xbe"
        retail.write_bytes(qb.apply(frozen_install, "retail")[0])
        self.assertIsNone(mod_build.restabilize_sim_qb_disc(retail))
        # The roster cannot be read: the frozen references and the sentence, as on the build routes.
        treated = self.folder / "treated.xbe"
        treated.write_bytes(qb.apply(xbe, "realistic", reference=lowered)[0])
        from mod_editor.core import nfl2k5_roster_records as rosters
        with patch.object(mod_build, "_disc_roster", side_effect=rosters.RosterRecordError("foreign roster")):
            record = mod_build.restabilize_sim_qb_disc(treated)
        self.assertEqual(treated.read_bytes(), frozen_install)
        self.assertEqual(record["note"], mod_build.SIM_QB_STABILITY_NOTES["unreadable"])

    def test_save_disc_copy_measures_the_edited_roster_and_says_so(self):
        xbe, body = private_fixtures(self)
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from mod_editor.gui import roster_editor_panel_qt as panel
        document = roster_with_lower_durability(body)
        _, lowered = qb.roster_stability(document)
        source, destination = self.folder / "built.xiso.iso", self.folder / "edited.xiso.iso"
        source.write_bytes(qb.apply(xbe, "realistic")[0])          # a built disc's executable (frozen references)
        with patch.object(panel.rr, "apply", side_effect=lambda staged, edits: {"target": str(staged)}), \
                patch.object(mod_build, "_disc_roster", return_value=document):
            receipt = panel.RosterEditorPanel._write_disc_copy(source, destination, {"edits": []}, False)
        self.assertEqual(qb.installed_reference(destination.read_bytes()), _float32(lowered))
        self.assertEqual(source.read_bytes(), qb.apply(xbe, "realistic")[0])          # the source is never written
        self.assertEqual(receipt["sim_qb_stability"]["source"], "disc roster")
        message = panel.RosterEditorPanel.disc_copy_message(receipt, str(destination))
        self.assertIn("measured again on your edited roster", message)
        fallback = {"sim_qb_stability": {"note": mod_build.SIM_QB_STABILITY_NOTES["out_of_range"]}}
        self.assertIn(mod_build.SIM_QB_STABILITY_NOTES["out_of_range"],
                      panel.RosterEditorPanel.disc_copy_message(fallback, "d.iso"))
        self.assertEqual(panel.RosterEditorPanel.disc_copy_message({}, "d.iso"), "Disc ready: d.iso. Open it in xemu.")


class LineupRolesKeepTheReferences(unittest.TestCase):
    def test_installing_lineup_roles_on_a_treated_executable_keeps_the_references(self):
        from mod_editor.core import nfl2k5_edge_rename as edge, nfl2k5_k128 as memory
        from mod_editor.core import nfl2k5_lineup_roles as lineup, nfl2k5_modern_positions as positions
        from mod_editor.core import nfl2k5_position_pools as pools, nfl2k5_sim_realism as simulator
        from mod_editor.core import nfl2k5_xbe_space as space
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes

        paired = pools.apply(positions.apply(edge.apply(retail_bytes())[0])[0], roster_has_olb=True)[0]
        standard = space.apply(paired, (*memory.REQUESTS, *simulator.REQUESTS, *lineup.REQUESTS), scaleout=True)[0]
        standard = simulator.apply(memory.apply(standard, require=True)[0])[0]
        roles = lineup.apply(standard, third_down=False)[0]
        reference = rules.stability_reference_for(rules.stability_starters(shifted_clubs(synthetic_clubs(81073), -SHIFT)))
        clinical = qb.apply(standard, "realistic", reference=reference)[0]
        result = lineup.apply(clinical, third_down=False)[0]
        self.assertEqual(qb.installed_reference(result), _float32(reference))
        self.assertEqual(result, qb.apply(roles, "realistic", reference=reference)[0])


if __name__ == "__main__":
    unittest.main()
