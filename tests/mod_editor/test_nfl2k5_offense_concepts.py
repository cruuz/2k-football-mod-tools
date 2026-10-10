"""PROVED OFFLINE: the modern offense concept engine (beta 77 p48o) and its wizard catalog.

Retail-grammar routes, 43 legal formations, every concept x formation design passes the
ported retail validator and the forward-target / handoff / screen geometry rules, and the
Create a Play wizard gets the same routes, concepts, formations and the flea flicker.
No game data is needed; gameplay is unwitnessed.
"""
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_offense_concepts as oc  # noqa: E402
from mod_editor.core import nfl2k5_play_codec as codec  # noqa: E402
from mod_editor.core import nfl2k5_play_library as lib  # noqa: E402

YD = codec.YD_CM
HEADERS = {"quick": 0x0400220E, "dropback": 0x0000620E, "pa": 0x0020640E, "pa_rollout": 0x0020660E,
           "rollout": 0x0000640E, "screen": 0x0000640E, "quick_screen": 0x0400260E, "run": 0x0000820E,
           "run_toss": 0x0200840E, "draw": 0x0000860E, "qb_sneak": 0x0400880E, "qb_draw": 0x0000860E,
           "reverse": 0x0000940E, "flea": 0x0600340E}
SIGNATURES = {"pass": {"pass"}, "pa_pass": {"pa_pass"}, "run": {"run", "draw"}, "sneak": {"qb_run"},
              "keeper": {"qb_run"}, "reverse": {"run"}, "flea": {"flea"}}


def validate(flags, chains):
    assignments = []
    for chain in chains:
        nodes = codec.encode_chain(chain)
        assignments.append((0, [n.to_bytes() for n in nodes]))
    for s in range(11):
        assignments[s] = (codec.build_descriptor(flags, assignments, s, 0), assignments[s][1])
    codec.validate_sync(assignments)
    return codec.validate_play(flags, assignments)


def all_designs():
    for fname, spec in oc.FORMATIONS.items():
        ctx = spec.context()
        for cname in oc.CONCEPTS:
            try:
                yield fname, ctx, oc.design(cname, ctx)
            except oc.ConceptUnavailable:
                continue


class RouteTreeTests(unittest.TestCase):
    def test_screen_clearout_override_preserves_target_blocking_and_timing(self):
        for concept, formation in (("RB Screen", "Gun Doubles"),
                                   ("Bubble Screen", "Gun Trips"),
                                   ("TE Screen", "Ace Wing"),
                                   ("WR Slip Screen", "Gun Doubles")):
            with self.subTest(concept=concept):
                ctx = oc.FORMATIONS[formation].context()
                base = oc.design(concept, ctx)
                slot = next(s for s in range(6, 11) if s != base.primary and
                            any(n[0] == 0x12 and n[1][0] == 0 for n in base.chains[s]))
                label = next(label for label, s in ctx.labels.items() if s == slot)
                variant = oc.design(concept, ctx, {"routes": {label: ["route", "Comeback", 18]}})
                self.assertNotEqual(base.chains[slot], variant.chains[slot])
                self.assertEqual(base.primary, variant.primary)
                self.assertEqual(base.reads, variant.reads)
                self.assertEqual(base.header, variant.header)
                for other in range(11):
                    if other != slot:
                        self.assertEqual(base.chains[other], variant.chains[other])
                self.assertIsNone(validate(HEADERS[variant.header], variant.chains))

    def test_routes_use_only_retail_segment_kinds_and_whole_feet(self):
        kinds = set()
        for name, route in oc.ROUTES.items():
            with self.subTest(route=name):
                chain = oc.route_chain(name)
                self.assertEqual(chain[0], lib.start(3))
                nodes = codec.encode_chain(chain)
                self.assertTrue(nodes[-1].flags & codec.NODE_FLAG_TERM)
                for op, vals in chain[1:]:
                    self.assertEqual(op, 0x12)
                    self.assertIn(int(vals[0]), range(12))
                    self.assertNotEqual(int(vals[0]), 9, "type 9 is a block or screen, not a route")
                    feet = vals[2] / codec.FT_CM
                    self.assertAlmostEqual(feet, round(feet), places=6)
                    kinds.add(int(vals[0]))
                self.assertTrue(route.retail, "every route names the retail chain it copies")
        # every break the engine supports except block types: straight, 30/45/60 in, laterals,
        # 45 out, comebacks out/in and the 30 degree settle
        self.assertTrue({0, 1, 2, 3, 4, 5, 6, 7, 8, 11} <= kinds)
        self.assertGreaterEqual(sum(1 for r in oc.ROUTES.values() if len(r.build()) >= 3), 10)

    def test_back_routes_gain_depth_before_flattening(self):
        for name in oc.route_names("back"):
            with self.subTest(route=name):
                first = oc.ROUTES[name].build()[0]
                self.assertIn(int(first[1][0]), (0, 6))


class FormationTests(unittest.TestCase):
    def test_every_formation_is_legal_with_two_eligible_ends(self):
        self.assertGreaterEqual(len(oc.FORMATIONS), 40)
        for name, spec in oc.FORMATIONS.items():
            with self.subTest(formation=name):
                self.assertEqual(oc.formation_problems(spec), [])
                self.assertLessEqual(len(spec.name), 40)
                self.assertEqual(len(spec.skills), 5)
                ctx = spec.context()
                self.assertEqual(ctx.gun, spec.align in ("gun", "pistol"))
                backs = len(ctx.backs())
                self.assertEqual(min(backs, 2), spec.backs)

    def test_personnel_spread_covers_heavy_base_spread_and_empty(self):
        groups = {spec.personnel for spec in oc.FORMATIONS.values()}
        self.assertEqual(groups, {"23", "22", "21", "12", "11", "20", "10", "01", "00"})
        for personnel in ("23", "22", "21", "12", "11", "10", "00"):
            with self.subTest(personnel=personnel):
                self.assertTrue(any(s.personnel == personnel and s.align == "uc" for s in oc.FORMATIONS.values()),
                                "the CPU calls under-centre sets between the 20s (native 0x207EF0 rule)")

    def test_x_is_left_outside_and_z_right_outside_in_receiver_groups(self):
        # nfl2k5_depth_roles assigns WR1/WR2/WR3 from the group's mean geometry
        for name, spec in oc.FORMATIONS.items():
            codes = oc.PERSONNEL_CODES[spec.personnel]
            xs = {code: spec.skills[i][0] for i, code in enumerate(codes)}
            if 9 in xs and 41 in xs and 73 in xs:
                with self.subTest(formation=name):
                    self.assertLess(xs[9], 0)
                    self.assertGreater(xs[41], 0)
                    self.assertLess(abs(xs[73]), max(abs(xs[9]), abs(xs[41])))


class ConceptTests(unittest.TestCase):
    def test_every_design_validates_and_keeps_targets_in_front_of_the_qb(self):
        count = 0
        for fname, ctx, d in all_designs():
            count += 1
            with self.subTest(formation=fname, concept=d.concept):
                self.assertIsNone(validate(HEADERS[d.header], d.chains))
                self.assertIn(lib.qb_signature(d.chains[ctx.qb.slot]), SIGNATURES[d.play_type])
                self.assertLessEqual(len(d.name), 40)
                qb = d.chains[ctx.qb.slot]
                if any(n[0] == 0x06 for n in qb) and d.header not in ("screen",):
                    release = oc.qb_release_yd(ctx, qb)
                    for s in range(6, 11):
                        end = oc.route_end_depth_yd(ctx, s, d.chains[s])
                        if end is not None:
                            self.assertGreaterEqual(end, release + 1.0, f"slot {s} finishes behind the QB")
                for g, chain in enumerate(d.chains):
                    for node in chain:
                        if node[0] == 0x13:
                            t = int(node[1][0])
                            a, b = ctx.player(g), ctx.player(t)
                            sep = math.hypot(a.x - b.x, a.z - b.z)
                            self.assertTrue(any(n[0] == 0x16 for n in d.chains[t]))
                            limit = 10.0 if int(node[1][1]) in (1, 2, 3) or b.kind in (lib.WR, lib.TE) else 6.5
                            self.assertLessEqual(sep, limit + 0.6)
        self.assertGreater(count, 1400)

    def test_screens_start_in_front_of_the_throw_and_release_the_line(self):
        for fname, ctx, d in all_designs():
            if d.concept not in ("RB Screen", "TE Screen"):
                continue
            with self.subTest(formation=fname, concept=d.concept):
                qb = d.chains[ctx.qb.slot]
                release = oc.qb_release_yd(ctx, qb)
                target = ctx.player(d.primary)
                self.assertGreaterEqual(target.z - release, 2.0)
                releases = [s for s in range(1, 6) if any(n[0] == 0x18 for n in d.chains[s])]
                self.assertEqual(len(releases), 3)
                side = 1 if d.chains[d.primary][-1][1][2] > 0 else -1
                if abs(target.x) > 0.5:
                    self.assertEqual(side, 1 if target.x > 0 else -1)

    def test_flea_flicker_is_the_retail_give_take_throw_script(self):
        ctx = oc.FORMATIONS["I-Form Pro"].context()
        d = oc.design("Flea Flicker", ctx)
        qb_ops = [n[0] for n in d.chains[0]]
        self.assertEqual(qb_ops, [0x01, 0x03, 0x13, 0x16, 0x06])
        back = ctx.slot("B")
        self.assertEqual([n[0] for n in d.chains[back]], [0x01, 0x16, 0x15, 0x13, 0x11])
        self.assertEqual(int(d.chains[back][3][1][1]), 1, "the back pitches it back (kind 1)")
        self.assertEqual(lib.qb_signature(d.chains[0]), "flea")
        self.assertEqual(lib.play_class_label(HEADERS["flea"]), "pass")
        self.assertIsNone(validate(HEADERS["flea"], d.chains))
        with self.assertRaises(oc.ConceptUnavailable):
            oc.design("Flea Flicker", oc.FORMATIONS["Gun Doubles"].context())

    def test_end_around_stays_inside_the_retail_exchange_envelope(self):
        made = 0
        for fname, spec in oc.FORMATIONS.items():
            ctx = spec.context()
            try:
                d = oc.design("End Around", ctx)
            except oc.ConceptUnavailable:
                continue
            made += 1
            with self.subTest(formation=fname):
                self.assertTrue(ctx.under_center)
                runner = ctx.player(d.primary)
                self.assertLessEqual(math.hypot(runner.x - ctx.qb.x, runner.z - ctx.qb.z), 9.6)
                self.assertEqual(d.chains[0][-1][0], 0x13)
                self.assertEqual(int(d.chains[0][-1][1][1]), 2)
        self.assertGreater(made, 3)

    def test_overrides_change_one_role_only(self):
        ctx = oc.FORMATIONS["Gun Bunch"].context()
        base = oc.design("Mesh", ctx)
        alt = oc.design("Mesh", ctx, {"routes": {"B": ["route", "Back Wheel"]}, "name": "Mesh Wheel"})
        b = ctx.slot("B")
        self.assertEqual(alt.name, "Mesh Wheel")
        self.assertNotEqual(base.chains[b], alt.chains[b])
        for s in range(11):
            if s not in (b, ctx.qb.slot):
                self.assertEqual(base.chains[s], alt.chains[s])
        weak = oc.design("Power", oc.FORMATIONS["I-Form Pro"].context(), {"direction": "weak"})
        strong = oc.design("Power", oc.FORMATIONS["I-Form Pro"].context())
        self.assertNotEqual(weak.chains, strong.chains)


class WizardCatalogTests(unittest.TestCase):
    def test_modern_entries_are_registered_without_renaming_classic_ones(self):
        for classic in ("Mesh", "Smash", "4 Verts", "HB Screen", "Y-Cross"):
            self.assertNotIn("engine", lib.PASS_CONCEPTS[classic])
        self.assertEqual(lib.PASS_CONCEPTS["Mesh (modern)"]["engine"], "Mesh")
        self.assertEqual(lib.PASS_CONCEPTS["Yankee"]["engine"], "Yankee")
        self.assertEqual(lib.RUN_SCHEMES["Duo"]["engine"], "Duo")
        self.assertIn("Inside Zone (modern)", lib.RUN_SCHEMES)
        for name in oc.ROUTES:
            self.assertIn(name, lib.ROUTES_BY_NAME)
        self.assertIn("Gun Trey (2K28)", lib.FORMATION_TEMPLATES)
        self.assertEqual(lib.WANTED_SIGNATURE["flea"], "flea")

    def _spec(self, template, play_type):
        _blurb, players = lib.FORMATION_TEMPLATES[template]
        positions = [(round(p.x * YD), round(p.z * YD)) for p in players]
        return lib.PlaySpec("t", play_type, positions, [p.kind for p in players], {})

    def test_engine_concepts_fill_every_slot_and_follow_play_action(self):
        spec = self._spec("Singleback Doubles (2K28)", "pass")
        lib.default_assignments(spec, concept="PA Boot")
        self.assertEqual(spec.play_type, "pa_pass")
        self.assertEqual({a.kind for a in spec.assignments.values()}, {"custom"})
        chains = lib.build_chains(spec)
        self.assertEqual(lib.qb_signature(chains[0]), "pa_pass")
        self.assertIsNone(validate(HEADERS["pa"], chains))

    def test_wizard_flea_flicker_and_modern_run(self):
        spec = self._spec("I-Form Pro (2K28)", "flea")
        lib.default_assignments(spec)
        chains = lib.build_chains(spec)
        self.assertEqual(lib.qb_signature(chains[0]), "flea")
        self.assertIsNone(validate(HEADERS["flea"], chains))
        run = self._spec("I-Form Pro (2K28)", "run")
        lib.default_assignments(run, scheme="Power (modern)")
        chains = lib.build_chains(run)
        self.assertEqual(lib.qb_signature(chains[0]), "run")
        self.assertIsNone(validate(HEADERS["run"], chains))

    def test_unavailable_concept_is_a_plain_error(self):
        spec = self._spec("Gun Empty (2K28)", "run")
        with self.assertRaises(ValueError):
            lib.default_assignments(spec, scheme="Inside Zone (modern)")


class FormationRatingTests(unittest.TestCase):
    """The v2 generator's CPU situation ratings (formation flag bits 21-29) and formation mix."""

    @classmethod
    def setUpClass(cls):
        import json
        cls.core = json.loads((ROOT / "pb" / "v2" / "core.json").read_text(encoding="utf-8"))

    def test_pack_formation_situation_round_trips_and_is_range_checked(self):
        from mod_editor.core import nfl2k5_playbook_pack as packs
        f = packs.PackFormation("f01", "Singleback Doubles", tuple((0, 0) for _ in range(11)), tuple(range(11)),
                                packs.PackDonor(3, "Doubles"), 4, "Doubles", 2, situation=(1, 0, 1))
        doc = f.to_json()
        self.assertEqual(doc["situation"], [1, 0, 1])
        self.assertEqual(packs.PackFormation.from_json(doc, 0).situation, (1, 0, 1))
        self.assertNotIn("situation", packs.PackFormation.from_json({**doc, "situation": None}, 0).to_json())
        for bad in ([1, 0], [1, 0, 8], [-1, 0, 1], ["1", 0, 1], [1.0, 0, 1]):
            with self.assertRaises(packs.PlaybookPackError):
                packs.PackFormation.from_json({**doc, "situation": bad}, 0)

    def test_every_catalog_formation_has_an_ordered_rating(self):
        ratings = self.core["formation_ratings"]
        self.assertEqual(set(ratings), set(oc.FORMATIONS))
        for name, (short, medium, long_) in ratings.items():
            self.assertTrue(all(0 <= v <= 7 for v in (short, medium, long_)), name)
            tag = oc.FORMATIONS[name].tag
            if tag in ("goal", "short"):        # heavy sets are best on short yardage, worst on long
                self.assertLessEqual(short, medium, name)
                self.assertLessEqual(medium, long_, name)
            if tag in ("spread", "empty"):      # spread / empty sets are best on long yardage
                self.assertLessEqual(long_, medium, name)
                self.assertLessEqual(medium, short, name)

    def test_core_has_no_under_centre_spread_or_empty_sets(self):
        # 0x207EF0 scores every shotgun/pistol set 0.05 outside the 10, so an under-centre 10 or 00
        # personnel set would take the 3rd-and-long calls from the shotgun sets of its group.
        for name in self.core["core_formations"] + list(self.core["optional_formations"]):
            spec = oc.FORMATIONS[name]
            self.assertFalse(spec.align == "uc" and spec.personnel in ("10", "00", "01"), name)
        self.assertEqual(self.core["max_gun_sets"], {"11": 5})


if __name__ == "__main__":
    unittest.main()
