"""b777 sc1: route kinds 9 and 10 end behind the line; screen blockers and back stems no longer reverse.

The GOLDEN rows are the real retail route initializer (0x229AE0) run under Unicorn on the retail executable
(role, start x, start depth yd, field direction, route segments (kind, feet), native end depth yd per segment); the
rows are recorded here so the test needs no retail bytes.  PROVED OFFLINE; gameplay is for Noah to judge.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_offense_concepts as oc  # noqa: E402
from mod_editor.core import nfl2k5_offense_modern as om  # noqa: E402
from mod_editor.core import nfl2k5_play_codec as codec  # noqa: E402
from mod_editor.core import nfl2k5_route_reversal as rr  # noqa: E402

GOLDEN = [
    (9, -17, 0, 1, ((0, 18), (10, 3)), (6.0, -1.0)),
    (9, -17, 0, 1, ((0, 27), (10, 3)), (9.0, -1.0)),
    (9, -17, 0, 1, ((0, 12), (10, 3)), (4.0, -1.0)),
    (9, 17, 0, 1, ((0, 18), (10, 3)), (6.0, -1.0)),
    (9, 17, 0, 1, ((0, 27), (10, 3)), (9.0, -1.0)),
    (9, 17, 0, 1, ((0, 12), (10, 3)), (4.0, -1.0)),
    (8, 5, 0, 1, ((0, 18), (10, 3)), (6.0, -1.0)),
    (8, 5, 0, 1, ((0, 27), (10, 3)), (9.0, -1.0)),
    (8, 5, 0, 1, ((0, 12), (10, 3)), (4.0, -1.0)),
    (8, 5, 0, 1, ((10, 9),), (-1.0,)),
    (9, 9, -1.5, 1, ((0, 18), (10, 3)), (4.5, -1.0)),
    (9, 9, -1.5, 1, ((0, 27), (10, 3)), (7.5, -1.0)),
    (9, 9, -1.5, 1, ((0, 12), (10, 3)), (2.5, -1.0)),
    (10, 0, -7, 1, ((0, 18), (10, 3)), (-1.0, -1.0)),
    (10, 0, -7, 1, ((0, 27), (10, 3)), (2.0, -1.0)),
    (10, 0, -7, 1, ((0, 12), (10, 3)), (-3.0, -1.0)),
    (10, 0, -7, 1, ((10, 9),), (-1.0,)),
    (10, 0, -5.3, 1, ((0, 18), (10, 3)), (0.7, -1.0)),
    (10, 0, -5.3, 1, ((0, 27), (10, 3)), (3.7, -1.0)),
    (10, 0, -5.3, 1, ((0, 12), (10, 3)), (-1.3, -1.0)),
    (10, 0, -5.3, 1, ((10, 9),), (-1.0,)),
    (10, 2, -5.3, 1, ((0, 18), (10, 3)), (0.7, -1.0)),
    (10, 2, -5.3, 1, ((0, 27), (10, 3)), (3.7, -1.0)),
    (10, 2, -5.3, 1, ((0, 12), (10, 3)), (-1.3, -1.0)),
    (10, 2, -5.3, 1, ((10, 9),), (-1.0,)),
    (11, 0, -4.5, 1, ((0, 18), (10, 3)), (1.5, -1.0)),
    (11, 0, -4.5, 1, ((0, 27), (10, 3)), (4.5, -1.0)),
    (11, 0, -4.5, 1, ((0, 12), (10, 3)), (-0.5, -1.0)),
    (11, 0, -4.5, 1, ((10, 9),), (-1.0,)),
    (10, 0, -7, 1, ((9, 33),), (-1.5,)),
    (10, 0, -7, 1, ((9, -33),), (-1.5,)),
    (10, 0, -7, 1, ((9, 63),), (-1.5,)),
    (10, 0, -7, 1, ((9, -63),), (-1.5,)),
    (10, 0, -7, 1, ((9, 18),), (-1.5,)),
    (10, -2.5, -5.3, 1, ((9, 33),), (-1.5,)),
    (10, -2.5, -5.3, 1, ((9, -33),), (-1.5,)),
    (10, -2.5, -5.3, 1, ((9, 63),), (-1.5,)),
    (10, -2.5, -5.3, 1, ((9, -63),), (-1.5,)),
    (10, -2.5, -5.3, 1, ((9, 18),), (-1.5,)),
    (10, 2.5, -5.3, 1, ((9, 33),), (-1.5,)),
    (10, 2.5, -5.3, 1, ((9, -33),), (-1.5,)),
    (10, 2.5, -5.3, 1, ((9, 63),), (-1.5,)),
    (10, 2.5, -5.3, 1, ((9, -63),), (-1.5,)),
    (10, 2.5, -5.3, 1, ((9, 18),), (-1.5,)),
    (11, 0, -4.5, 1, ((9, 33),), (-1.5,)),
    (11, 0, -4.5, 1, ((9, -33),), (-1.5,)),
    (11, 0, -4.5, 1, ((9, 63),), (-1.5,)),
    (11, 0, -4.5, 1, ((9, -63),), (-1.5,)),
    (11, 0, -4.5, 1, ((9, 18),), (-1.5,)),
    (8, 5, 0, 1, ((9, 33),), (-1.5,)),
    (8, 5, 0, 1, ((9, -33),), (-1.5,)),
    (8, 5, 0, 1, ((9, 63),), (-1.5,)),
    (8, 5, 0, 1, ((9, -63),), (-1.5,)),
    (8, 5, 0, 1, ((9, 18),), (-1.5,)),
    (10, 11, -1.5, 1, ((9, 33),), (-1.5,)),
    (10, 11, -1.5, 1, ((9, -33),), (-1.5,)),
    (10, 11, -1.5, 1, ((9, 63),), (-1.5,)),
    (10, 11, -1.5, 1, ((9, -63),), (-1.5,)),
    (10, 11, -1.5, 1, ((9, 18),), (-1.5,)),
    (9, -17, 0, 1, ((0, 45),), (30.0,)),
    (9, -17, 0, 1, ((0, 30), (2, 30)), (10.0, 16.67)),
    (8, 5, 0, 1, ((0, 45),), (30.0,)),
    (8, 5, 0, 1, ((0, 30), (2, 30)), (10.0, 24.14)),
    (10, 0, -7, 1, ((0, 45),), (23.0,)),
    (10, 0, -7, 1, ((0, 30), (2, 30)), (3.0, 17.14)),
    (9, -17, 0, -1, ((0, 18), (10, 3)), (6.0, -1.0)),
    (9, -17, 0, -1, ((0, 27), (10, 3)), (9.0, -1.0)),
    (9, -17, 0, -1, ((0, 12), (10, 3)), (4.0, -1.0)),
    (9, 17, 0, -1, ((0, 18), (10, 3)), (6.0, -1.0)),
    (9, 17, 0, -1, ((0, 27), (10, 3)), (9.0, -1.0)),
    (9, 17, 0, -1, ((0, 12), (10, 3)), (4.0, -1.0)),
    (8, 5, 0, -1, ((0, 18), (10, 3)), (6.0, -1.0)),
    (8, 5, 0, -1, ((0, 27), (10, 3)), (9.0, -1.0)),
    (8, 5, 0, -1, ((0, 12), (10, 3)), (4.0, -1.0)),
    (8, 5, 0, -1, ((10, 9),), (-1.0,)),
    (9, 9, -1.5, -1, ((0, 18), (10, 3)), (4.5, -1.0)),
    (9, 9, -1.5, -1, ((0, 27), (10, 3)), (7.5, -1.0)),
    (9, 9, -1.5, -1, ((0, 12), (10, 3)), (2.5, -1.0)),
    (10, 0, -7, -1, ((0, 18), (10, 3)), (-1.0, -1.0)),
    (10, 0, -7, -1, ((0, 27), (10, 3)), (2.0, -1.0)),
    (10, 0, -7, -1, ((0, 12), (10, 3)), (-3.0, -1.0)),
    (10, 0, -7, -1, ((10, 9),), (-1.0,)),
    (10, 0, -5.3, -1, ((0, 18), (10, 3)), (0.7, -1.0)),
    (10, 0, -5.3, -1, ((0, 27), (10, 3)), (3.7, -1.0)),
    (10, 0, -5.3, -1, ((0, 12), (10, 3)), (-1.3, -1.0)),
    (10, 0, -5.3, -1, ((10, 9),), (-1.0,)),
    (10, 2, -5.3, -1, ((0, 18), (10, 3)), (0.7, -1.0)),
    (10, 2, -5.3, -1, ((0, 27), (10, 3)), (3.7, -1.0)),
    (10, 2, -5.3, -1, ((0, 12), (10, 3)), (-1.3, -1.0)),
    (10, 2, -5.3, -1, ((10, 9),), (-1.0,)),
    (11, 0, -4.5, -1, ((0, 18), (10, 3)), (1.5, -1.0)),
    (11, 0, -4.5, -1, ((0, 27), (10, 3)), (4.5, -1.0)),
    (11, 0, -4.5, -1, ((0, 12), (10, 3)), (-0.5, -1.0)),
    (11, 0, -4.5, -1, ((10, 9),), (-1.0,)),
    (10, 0, -7, -1, ((9, 33),), (-1.5,)),
    (10, 0, -7, -1, ((9, -33),), (-1.5,)),
    (10, 0, -7, -1, ((9, 63),), (-1.5,)),
    (10, 0, -7, -1, ((9, -63),), (-1.5,)),
    (10, 0, -7, -1, ((9, 18),), (-1.5,)),
    (10, -2.5, -5.3, -1, ((9, 33),), (-1.5,)),
    (10, -2.5, -5.3, -1, ((9, -33),), (-1.5,)),
    (10, -2.5, -5.3, -1, ((9, 63),), (-1.5,)),
    (10, -2.5, -5.3, -1, ((9, -63),), (-1.5,)),
    (10, -2.5, -5.3, -1, ((9, 18),), (-1.5,)),
    (10, 2.5, -5.3, -1, ((9, 33),), (-1.5,)),
    (10, 2.5, -5.3, -1, ((9, -33),), (-1.5,)),
    (10, 2.5, -5.3, -1, ((9, 63),), (-1.5,)),
    (10, 2.5, -5.3, -1, ((9, -63),), (-1.5,)),
    (10, 2.5, -5.3, -1, ((9, 18),), (-1.5,)),
    (11, 0, -4.5, -1, ((9, 33),), (-1.5,)),
    (11, 0, -4.5, -1, ((9, -33),), (-1.5,)),
    (11, 0, -4.5, -1, ((9, 63),), (-1.5,)),
    (11, 0, -4.5, -1, ((9, -63),), (-1.5,)),
    (11, 0, -4.5, -1, ((9, 18),), (-1.5,)),
    (8, 5, 0, -1, ((9, 33),), (-1.5,)),
    (8, 5, 0, -1, ((9, -33),), (-1.5,)),
    (8, 5, 0, -1, ((9, 63),), (-1.5,)),
    (8, 5, 0, -1, ((9, -63),), (-1.5,)),
    (8, 5, 0, -1, ((9, 18),), (-1.5,)),
    (10, 11, -1.5, -1, ((9, 33),), (-1.5,)),
    (10, 11, -1.5, -1, ((9, -33),), (-1.5,)),
    (10, 11, -1.5, -1, ((9, 63),), (-1.5,)),
    (10, 11, -1.5, -1, ((9, -63),), (-1.5,)),
    (10, 11, -1.5, -1, ((9, 18),), (-1.5,)),
]


def chain_of(segs):
    return [oc.start(3)] + [oc.seg(k, ft) for k, ft in segs]


def validate(design, flags=0x640E):
    enc = [[n.to_bytes() for n in codec.encode_chain(c)] for c in design.chains]
    asg = [(0, e) for e in enc]
    for i in range(11):
        asg[i] = (codec.build_descriptor(flags, asg, i, 0), asg[i][1])
    codec.validate_sync(asg)
    return codec.validate_play(flags, asg)


class NativeModelTests(unittest.TestCase):
    def test_model_matches_the_native_trace(self):
        """Kinds 0, 9 and 10 land exactly where the real route initializer put them."""
        checked = 0
        for role, x, z, direction, segs, ends in GOLDEN:
            path = rr.segment_depths(z, chain_of(segs))
            for (kind, _before, after), native, seg in zip(path, ends, segs):
                terminal = seg is segs[-1]
                if kind in (9, 10) or (kind == 0 and not terminal):      # a terminal straight keeps running natively
                    self.assertAlmostEqual(after, native, delta=0.06, msg=(role, x, z, segs))
                    checked += 1
        self.assertGreater(checked, 100)

    def test_kind_10_after_a_stem_runs_back_for_a_receiver_on_the_line(self):
        for stem_ft in (12, 18, 27):
            chain = chain_of([(0, stem_ft), (10, 3)])
            found = rr.reversals(0.0, chain)
            self.assertEqual(len(found), 1, stem_ft)
            kind, a, b = found[0]
            self.assertEqual((kind, b), (10, -1.0))
            self.assertGreaterEqual(a - b, stem_ft / 3 + 1.0 - 0.01)

    def test_retail_back_steps_up_to_block_without_reversing(self):
        self.assertEqual(rr.reversals(-7.0, chain_of([(0, 18), (10, 3)])), [])
        self.assertEqual(rr.reversals(-6.9, chain_of([(0, 15), (10, 3)])), [])

    def test_gun_back_with_the_retail_stem_overshoots_and_the_clamp_fixes_it(self):
        chain = chain_of([(0, 18), (10, 3)])
        self.assertTrue(rr.reversals(-5.3, chain))
        fixed = rr.clamp_stem(-5.3, chain)
        self.assertEqual(rr.reversals(-5.3, fixed), [])
        self.assertEqual([int(n[1][0]) for n in fixed if n[0] == 0x12], [0, 10])
        self.assertEqual(round(fixed[1][1][2] / codec.FT_CM), 12)       # four whole yards
        self.assertEqual(rr.clamp_stem(-7.0, chain), chain)                # retail geometry untouched

    def test_back_that_cannot_step_up_gets_a_plain_pass_set(self):
        fixed = rr.clamp_stem(-1.5, chain_of([(0, 18), (10, 3)]))
        self.assertEqual([n for n in fixed if n[0] == 0x12], [])

    def test_screen_target_kind_9_is_not_a_reversal_from_any_formation_depth(self):
        for z in (-7.0, -5.3, -4.5, -1.5):
            for dist in (33, -33, 63, -63):
                self.assertEqual(rr.reversals(z, chain_of([(9, dist)])), [], (z, dist))

    def test_designed_comebacks_are_not_flagged(self):
        self.assertEqual(rr.reversals(0.0, chain_of([(0, 30), (7, 9)])), [])
        self.assertEqual(rr.reversals(0.0, chain_of([(0, 30), (11, 6)])), [])

    def test_engine_end_depth_follows_the_native_endpoint(self):
        ctx = oc.FORMATIONS["Singleback Doubles"].context()
        wr = next(p for p in ctx.players if p.kind == oc.WR and p.on_los)
        self.assertEqual(oc.route_end_depth_yd(ctx, wr.slot, chain_of([(0, 27), (10, 3)])), -1.0)


class LintModelTests(unittest.TestCase):
    def test_playbook_lint_uses_the_native_kind_10_endpoint(self):
        from mod_editor.core import nfl2k5_playbook_lint as lint
        nodes = codec.encode_chain(chain_of([(0, 12), (10, 3)]))
        self.assertAlmostEqual(lint.route_end_depth(nodes, -7.0 * codec.YD_CM), -codec.YD_CM, delta=1.0)
        self.assertAlmostEqual(lint.route_end_depth(codec.encode_chain(chain_of([(10, 9)])), -7.0 * codec.YD_CM),
                               -codec.YD_CM, delta=1.0)


def _screens(spec):
    ctx = spec.context()
    codes = spec.codes()
    out = []
    for label, weak in (("B", False), ("B", True), ("B2", False)):
        try:
            out.append((ctx, om.back_screen(ctx, label, weak, codes)))
        except oc.ConceptUnavailable:
            pass
    for name in ("Bubble Screen", "WR Slip Screen", "TE Screen"):
        try:
            out.append((ctx, oc.design(name, ctx)))
        except oc.ConceptUnavailable:
            pass
    return out


def _old_stem_blocks(ctx, design):
    """pb1's b776 screen_blockers, kept here to prove the lint sees the defect it created."""
    for p in ctx.players:
        if p.slot == design.primary or p.kind not in (oc.WR, oc.TE):
            continue
        ch = design.chains[p.slot] or []
        kinds = tuple(int(n[1][0]) for n in ch if n[0] == 0x12)
        if kinds in ((0,), (6, 0), (1, 0), (0, 2), (0, 1), (2,), (1,)):
            design.chains[p.slot] = oc.route_chain("Stem Block", 6 if abs(p.x) < 10 else 9)


class ScreenRepairTests(unittest.TestCase):
    def test_every_formation_screen_is_clean_after_the_generator_rule_and_the_old_rule_was_not(self):
        old_bad = designs = 0
        for name, spec in oc.FORMATIONS.items():
            for ctx, design in _screens(spec):
                oc.fill_unassigned(ctx, design)
                designs += 1
                old = om_copy(design)
                _old_stem_blocks(ctx, old)
                if any(rr.reversals(p.z, old.chains[p.slot] or []) for p in ctx.players
                       if p.slot != old.primary and old.chains[p.slot]):
                    old_bad += 1
                rr.decoys_to_blockers(oc, ctx, design, {(0,), (6, 0), (1, 0)}, {(0, 2), (0, 1), (2,), (1,)})
                rr.repair_design(oc, ctx, design)
                for p in ctx.players:
                    if p.slot != design.primary:
                        self.assertEqual(rr.reversals(p.z, design.chains[p.slot] or []), [], (name, design.name, p.slot))
                self.assertIsNone(validate(design), (name, design.name))
        self.assertGreater(designs, 300)
        self.assertGreater(old_bad, 100)      # the defect existed in the old rule across many screens

    def test_decoys_become_retail_blockers_and_the_target_keeps_its_route(self):
        spec = oc.FORMATIONS["Gun Doubles"]
        ctx = spec.context()
        d = om.back_screen(ctx, "B", False, spec.codes())
        oc.fill_unassigned(ctx, d)
        target = d.chains[d.primary]
        rr.decoys_to_blockers(oc, ctx, d, {(0,), (6, 0), (1, 0)}, {(0, 2), (0, 1), (2,), (1,)})
        self.assertIs(d.chains[d.primary], target)
        for p in ctx.players:
            if p.slot != d.primary and p.kind in (oc.WR, oc.TE):
                ops = [n[0] for n in d.chains[p.slot]]
                self.assertNotIn(0x12, ops, p.slot)
                self.assertIn(0x11, ops, p.slot)


def om_copy(design):
    import copy
    return copy.deepcopy(design)


class PlayActionBackTests(unittest.TestCase):
    def test_play_action_backs_do_not_overshoot_from_any_formation(self):
        fixed_any = 0
        for name, spec in oc.FORMATIONS.items():
            ctx = spec.context()
            if ctx.slot("B") is None:
                continue
            for call in om.combo_calls(ctx):
                if call.drop != "pa":
                    continue
                try:
                    d = om.combo_design(ctx, call, spec.codes())
                except oc.ConceptUnavailable:
                    continue
                b = ctx.slot("B")
                oc.fill_unassigned(ctx, d)
                had = rr.reversals(ctx.player(b).z, d.chains[b])
                rr.repair_design(oc, ctx, d)
                fixed_any += bool(had)
                for p in ctx.players:
                    self.assertEqual(rr.reversals(p.z, d.chains[p.slot] or []), [], (name, d.name, p.slot))
                break
        self.assertGreater(fixed_any, 5)       # gun and pistol backs start at -4.3..-5.5, shallower than retail's -7


class GeneratorTests(unittest.TestCase):
    def test_generator_screen_blockers_uses_the_repair(self):
        from pb.v2 import generator as gen
        spec = oc.FORMATIONS["Pistol Doubles"]
        ctx = spec.context()
        d = om.back_screen(ctx, "B", True, spec.codes())
        oc.fill_unassigned(ctx, d)
        gen.screen_blockers(ctx, d)
        for p in ctx.players:
            if p.slot != d.primary and p.kind in (oc.WR, oc.TE):
                self.assertEqual(rr.reversals(p.z, d.chains[p.slot]), [])
                self.assertNotIn(10, [int(n[1][0]) for n in d.chains[p.slot] if n[0] == 0x12])


if __name__ == "__main__":
    unittest.main()
