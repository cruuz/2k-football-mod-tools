"""b780 m64kits: at 64 MB every kit at every venue fits, by memory_budget.predict; era slots left retail get their label.

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
from mod_editor.core import nfl2k5_era_kits as era  # noqa: E402
from mod_editor.core import nfl2k5_memory_budget as mb  # noqa: E402

import os  # noqa: E402
RETAIL = Path(os.environ.get("NFL2K5_RETAIL_XISO", "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))
V06 = Path(os.environ.get("B771_V06_DISC", "/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.6 (2026-10-09).xiso.iso"))
SPARE_DONORS = ("16H12.IFF", "16A12.IFF", "02H4.IFF", "02A4.IFF")   # the historic spare styles (NE, BAL)


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



def era_label(code, style):
    recipe = next(r for r in era.recipes() if (r["code"], r["style"]) == (code, style))
    return tuple(recipe["label"]), tuple(recipe["retail_pair"])


class EraLabels(unittest.TestCase):
    """b780 m64kits: "Uniform select shows the right era label for kits a build leaves at their retail look"."""

    def rows(self, states):
        return [(selector, None, dict(selector=selector, id=r["id"], state=states.get(r["id"], "composed")))
                for r in era.recipes() for selector in era.targets(r).values()]

    def test_a_slot_left_retail_gets_its_retail_label(self):
        labels = {(r["code"], r["style"]): tuple(r["label"]) for r in era.recipes()}
        got = era.retail_labels(self.rows({"G1": "donor_absent", "G3": "donor_absent"}), labels)
        self.assertEqual(got, {("16", 11): (2004, 1), ("02", 1): (1997, 1999)})

    def test_composed_kits_keep_their_era_label(self):
        """The 128 MB pack composes all ten kits (ship10's final receipt), so its roster is never touched."""
        labels = {(r["code"], r["style"]): tuple(r["label"]) for r in era.recipes()}
        self.assertEqual(era.retail_labels(self.rows({}), labels), {})
        self.assertEqual(era.retail_labels(self.rows({r["id"]: "applied" for r in era.recipes()}), labels), {})

    def test_a_slot_not_labelled_with_the_era_years_is_left_alone(self):
        labels = {(r["code"], r["style"]): tuple(r["retail_pair"]) for r in era.recipes()}
        self.assertEqual(era.retail_labels(self.rows({"G3": "donor_absent"}), labels), {})

    def test_every_64_mb_plan_has_no_more_moments_so_the_spare_donors_are_absent(self):
        for label, opts in plans_64():
            self.assertFalse(mb.on(opts, "espn25_more_moments"), label)

    @unittest.skipUnless(RETAIL.is_file() and V06.is_file(), "retail ISO or the v0.6 disc absent")
    def test_without_more_moments_bal_1_and_ne_11_read_their_retail_labels(self):
        """The era kits stage on a build with no historic spare styles (every 64 MB plan, any build without more
        moments): NE 11 and BAL 1 stay retail and the roster then reads their retail labels; every other byte kept."""
        from mod_editor.core import nfl2k5_bump_texture_writer as bump

        def read(path, names):
            with bump._Image.open(path, writable=False) as image:
                index = bump._parsed_index(image)
                entries = {bump.logical_name_for(e.name_id): e for e in index.entries}
                found = {n: image.read_segments(index.sub_extents(entries[n], 0, entries[n].size))
                         for n in names if n in entries}
                roster = image.read_segments(index.sub_extents(index.entries[5], 0, index.entries[5].size))
                return found, roster
        copy, retail_names = era.needed_packages()
        targets = {s + ".IFF" for s in era.pins()["kits"]}
        retail, retail_roster = read(RETAIL, sorted(set(copy) | set(retail_names)))
        v06, v06_roster = read(V06, sorted(copy))
        stage = {n: (retail[n] if n in targets else v06[n]) for n in copy if n not in SPARE_DONORS}
        labels = era.roster_labels(v06_roster)              # the SOFTDRINK roster labels the era years
        for recipe in era.recipes():                         # the recipes' retail pairs are the retail roster's
            self.assertEqual(era.roster_labels(retail_roster)[(recipe["code"], recipe["style"])],
                             tuple(recipe["retail_pair"]))
        rows = era.plan(stage, labels, {n: retail[n] for n in retail_names})
        states = {row["id"]: row["state"] for _s, _d, row in rows}
        self.assertEqual((states["G1"], states["G3"]), ("donor_absent", "donor_absent"))
        self.assertEqual({states["G1b"], states["G2"], states["G4"]}, {"composed"})
        wanted = era.retail_labels(rows, labels)
        fixed = era.relabel_roster(v06_roster, wanted)
        after = era.roster_labels(fixed)
        self.assertEqual(after[("02", 1)], era_label("02", 1)[1])        # the 1997-99 throwback
        self.assertEqual(after[("16", 11)], era_label("16", 11)[1])
        for key in (("21", 14), ("17", 6), ("22", 4)):
            self.assertEqual(after[key], labels[key])
        self.assertEqual(len(fixed), len(v06_roster))
        self.assertEqual(sum(a != b for a, b in zip(fixed, v06_roster)), sum(
            a != b for a, b in zip(b"".join(bytes(__import__("struct").pack("<HH", *p)) for p in wanted.values()),
                                   b"".join(bytes(__import__("struct").pack("<HH", *labels[k])) for k in wanted))))
        self.assertEqual(era.retail_labels(era.plan(stage, after, {n: retail[n] for n in retail_names}), after), {})


if __name__ == "__main__":
    unittest.main()
