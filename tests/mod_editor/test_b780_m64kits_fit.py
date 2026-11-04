"""b780 m64kits: at 64 MB every kit at every venue fits, by memory_budget.predict.

The model counted the RC's composed Ravens era kit (BAL style 1, 2008-2025; 2,859,648 B in game) at every plan, so the
64 MB pack's hardest game (a player-picked BAL alternate at NRG Stadium) came out 57,280 B over. The 64 MB build never
composes that kit: its donor is the Ravens' historic spare style, which the historic team styles step makes only with
ESPN Anniversary more moments, which the 64 MB profile turns off. ship10's 64 MB disc (9c85db35) shows 02H1/02A1
donor_absent at their retail size. The model now counts the composed kit only when the plan composes it.
"""
from __future__ import annotations

import dataclasses
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_memory_budget as mb  # noqa: E402


def preset_plan(name):
    return mod_build.apply_preset(mod_build.BuildPlan("retail.iso", "out.iso"), name)


def plans_64():
    yield "the v0.9 pack", mb.profile_64_plan(None)
    for name in mod_build.PRESETS:
        yield name, mb.profile_64_plan(preset_plan(name))


def every_game(opts):
    """(total main-heap charge, venue, home kit, away kit) of every venue x every home kit x every away kit."""
    composed = mb._era_kits(opts)
    for venue in mb.VENUES:
        charge = mb.venue_charge(opts, venue)
        number = int(venue[1:])
        for home in ((number,) if number in mb.TEAMS else mb.TEAMS):
            for hs in range(6):
                home_kit = f"{home:02d}h{hs}"
                for away in mb.TEAMS:
                    if away == home:
                        continue
                    for aws in range(6):
                        away_kit = f"{away:02d}a{aws}"
                        yield (charge + mb._kit(home_kit, composed) + mb._kit(away_kit, composed), venue, home_kit,
                               away_kit)


class EveryVenueEveryKit(unittest.TestCase):
    def test_every_venue_and_every_kit_fits_at_64_mb(self):
        need = mb.needed_room()
        for label, opts in plans_64():
            prediction = mb.predict(opts, 64)
            self.assertTrue(prediction["fits"], f"{label}: {prediction['over_bytes']} B over at {prediction['hardest']}")
            self.assertEqual(prediction["over_bytes"], 0, label)
            self.assertGreaterEqual(prediction["primary_uniforms"]["margin"], mb.SAFETY_MARGIN, label)
            matchup = prediction["matchup"]
            hardest = matchup["venue_bytes"] + matchup["kit_bytes"]
            worst = max(every_game(opts))
            self.assertEqual(worst[0], hardest, f"{label}: the model's hardest game is not the heaviest of all {worst}")
            for total, venue, home_kit, away_kit in every_game(opts):
                room = prediction["room"] + hardest - total
                self.assertGreaterEqual(room, need, f"{label}: {venue} {home_kit} v {away_kit} is short")

    def test_the_ravens_era_kit_counts_only_when_the_plan_composes_it(self):
        opts = mb.profile_64_plan(None)
        self.assertFalse(mb.on(opts, "espn25_more_moments"))
        self.assertEqual(mb._kit("02a1", mb._era_kits(opts)), mb.KIT)
        with_moments = dict(opts, espn25_more_moments=True)
        self.assertEqual(mb._kit("02a1", mb._era_kits(with_moments)), mb.KITS_RC["02a1"])
        self.assertEqual(mb.predict(with_moments, 64)["matchup"]["away_kit"], "02a1")
        self.assertEqual(mb.predict(opts, 64)["matchup"]["away_kit"], "03a4")

    def test_the_model_rule_is_the_build_rule(self):
        """The Ravens era kit's donor is a historic spare style, made only inside the more moments step."""
        recipes = json.loads((ROOT / "data/nfl2k5_moment_era_kits.json").read_text(encoding="utf-8"))["items"]
        ravens = next(r for r in recipes if r["id"] == "G3")
        self.assertEqual((ravens["code"], ravens["style"]), ("02", 1))
        self.assertEqual(ravens["kits"], {"H": "02H4", "A": "02A4"})       # the historic spare donors
        self.assertEqual(set(mb.ERA_KIT_NEEDS), {"02h1", "02a1"})
        source = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        at = source.index('_step("historic_styles")')
        block = [m.group(1) for m in re.finditer(r"\n    if (plan\.\w+):", source[:at])][-1]
        self.assertEqual(block, "plan.espn25_more_moments")

    def test_the_128_mb_pack_prediction_is_unchanged(self):
        """The pack composes every era kit: its 128 MB and 64 MB predictions count the composed Ravens kit as before."""
        rc = mb.rc_plan()
        self.assertTrue(mb.on(rc, "espn25_more_moments"))
        self.assertEqual(mb._era_kits(rc), frozenset(mb.ERA_KIT_NEEDS))
        self.assertEqual(mb.predict(None, 128)["matchup"]["away_kit"], "02a1")


if __name__ == "__main__":
    unittest.main()
