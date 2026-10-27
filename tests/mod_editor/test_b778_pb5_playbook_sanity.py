"""b778 pb5: playbook sanity rules from Noah's 10/21 stream, checked on the shipped SOFTDRINK offense packs.

* page one: the formation picker opens on book slot 0, so the first three slots hold normal-down sets, never Goal Line
  Sneak / Goal Line / Gun Wildcat (failed on origin/main: every book opened on GOAL LINE SNEAK);
* play-action boots keep their QB alignment and faking backfield, and "Pistol ..." plays stay in pistol sets
  (failed on origin/main: TEN "Pistol Boot" listed in Gun Tight Slots and four more non-pistol sets);
* the direct snap decoy's release is mode 1, as retail's "H Direct Snap" (failed on origin/main: mode 0 in 33 plays);
* no route settles inside and then slides out across its own stem (failed on origin/main: 203 route chains);
* every pass play runs at least three routes unless it is a screen, a trick or a max-protect concept;
* every menu ends on a whole page.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from pb.v2 import sanity_b778 as sanity  # noqa: E402
from mod_editor.core import nfl2k5_offense_concepts as oc  # noqa: E402
from mod_editor.core import nfl2k5_offense_modern as om  # noqa: E402

MANIFEST = ROOT / "pb" / "v2" / "manifest.json"
WR, TE, HB, FB = 9, 8, 10, 11
MAX_PROTECT_CONCEPTS = ("Yankee", "Flea Flicker")


def shipped():
    for row in json.loads(MANIFEST.read_text(encoding="utf-8"))["teams"]:
        doc = json.loads((ROOT / row["pack"]).read_text(encoding="utf-8"))
        cat = json.loads((ROOT / "pb" / "v2" / "catalogs" / f"{row['team']}.json").read_text(encoding="utf-8"))
        yield row["team"], doc, cat


def slot_order(doc):
    return [f["custom_name"] for f in sorted(doc["formations"], key=sanity._slot_key)]


def runs_route(chain) -> bool:
    if any(n[0] == 0x18 for n in chain or []):
        return True
    return any(n[0] == 0x12 and int(n[1][0]) not in (8, 9, 10) for n in chain or [])


class PageOne(unittest.TestCase):
    def test_first_pages_are_normal_down_sets(self):
        bad = {}
        for team, doc, _cat in shipped():
            first = slot_order(doc)[:sanity.PAGE]
            if any(sanity.is_special(n) for n in first):
                bad[team] = first
        self.assertEqual(bad, {})

    def test_goal_line_sets_stay_out_of_the_first_down_lottery(self):
        # LT Coach's Pick runs the CPU lottery: goal line sets must weigh the minimum on 1st & 10
        for team, doc, _cat in shipped():
            for f in doc["formations"]:
                if sanity._tag(f["custom_name"]) == "goal":
                    self.assertLessEqual(sanity.first_down_weight(f["situation"]), 0.1, (team, f["custom_name"]))

    def test_page_one_slots_only_swaps_specials(self):
        names = ["Goal Line Sneak", "Goal Line", "Gun Wildcat", "Empty Trey", "Gun Doubles", "Singleback Ace", "Wing T"]
        out = sanity.page_one_slots(names, ["Singleback Ace", "Gun Doubles", "Empty Trey"])
        self.assertEqual(out[:3], ["Singleback Ace", "Gun Doubles", "Empty Trey"])
        self.assertEqual(sorted(out), sorted(names))
        self.assertEqual(out[6], "Wing T")
        self.assertEqual(sanity.page_one_slots(["Gun Doubles", "Goal Line"], ["Gun Doubles"]), ["Gun Doubles", "Goal Line"])

    def test_pack_slots_are_a_permutation(self):
        for team, doc, _cat in shipped():
            idx = [f["replace_index"] for f in doc["formations"] if f.get("replace_index") is not None]
            self.assertEqual(len(idx), len(set(idx)), team)
            self.assertIn(0, idx, team)


class Backfield(unittest.TestCase):
    def test_pa_boots_keep_their_backfield(self):
        bad = []
        for team, doc, cat in shipped():
            home = {r["play"]: r["home"] for r in cat["plays"]}
            by_name = {f["custom_name"]: f for f in doc["formations"]}
            forms = {f["id"]: f for f in doc["formations"]}
            plays = {p["id"]: p for p in doc["plays"]}
            for fid, menu in doc["menus"].items():
                for pid in menu:
                    p = plays[pid]
                    if not sanity.is_pa_boot(p) or forms[fid]["custom_name"] == home[pid]:
                        continue
                    if not sanity.backfield_compatible(by_name[home[pid]], forms[fid]):
                        bad.append((team, p["custom_name"], forms[fid]["custom_name"]))
        # a menu that cannot otherwise end on a whole page may keep a mismatched link; none does today
        self.assertEqual(bad, [])

    def test_pistol_named_plays_stay_in_pistol_sets(self):
        bad = []
        for team, doc, _cat in shipped():
            forms = {f["id"]: f for f in doc["formations"]}
            plays = {p["id"]: p for p in doc["plays"]}
            for fid, menu in doc["menus"].items():
                for pid in menu:
                    if sanity.alignment_named(plays[pid]["custom_name"]) == "pistol" and \
                            sanity.qb_alignment(forms[fid]) != "pistol":
                        bad.append((team, plays[pid]["custom_name"], forms[fid]["custom_name"]))
        self.assertEqual(bad, [])

    def test_generator_refuses_the_pistol_boot_in_the_gun(self):
        from pb.v2 import generator as gen
        spec = oc.FORMATIONS["Pistol Doubles"]
        c = gen.make_cand(spec, oc.design("PA Boot", spec.context()), "boot", 1.0)
        self.assertTrue(gen.is_pa_boot(c.design))
        self.assertTrue(gen.same_alignment_ok(c, oc.FORMATIONS["Pistol Trey"]))
        for other in ("Gun Tight Slots", "Gun Bunch X Nasty", "Singleback Bunch"):
            self.assertFalse(gen.same_alignment_ok(c, oc.FORMATIONS[other]), other)


class DirectSnap(unittest.TestCase):
    def test_shipped_decoy_release_is_relative(self):
        n = 0
        for team, doc, _cat in shipped():
            for p in doc["plays"]:
                if p["play_type"] != "direct_snap":
                    continue
                rel = [node for node in p["assignments"][0] if node[0] == 0x18]
                self.assertTrue(rel, (team, p["custom_name"]))
                self.assertEqual([int(node[1][0]) for node in rel], [1] * len(rel), (team, p["custom_name"]))
                n += 1
        self.assertGreaterEqual(n, 32)

    def test_engine_decoy_release_is_relative(self):
        ctx = oc.FORMATIONS["Gun Wildcat"].context()
        d = om.run_design(ctx, "Direct Snap Power")
        rel = [n for n in d.chains[ctx.qb.slot] if n[0] == 0x18]
        self.assertEqual(len(rel), 1)
        self.assertEqual(int(rel[0][1][0]), 1)


class Routes(unittest.TestCase):
    def test_no_settle_inside_then_out(self):
        bad = []
        for team, doc, _cat in shipped():
            for p in doc["plays"]:
                for slot, chain in enumerate(p["assignments"]):
                    if sanity.spot_out_nodes(chain):
                        bad.append((team, p["custom_name"], slot))
        self.assertEqual(bad, [])

    def test_engine_spot_out(self):
        kinds = [k for k, _d in oc.ROUTES["Spot Out"].segments(5)]
        self.assertEqual(kinds, [0, 7, 5])

    def test_pass_plays_run_three_routes(self):
        bad = []
        for team, doc, cat in shipped():
            home = {r["play"]: r["home"] for r in cat["plays"]}
            by_name = {f["custom_name"]: f for f in doc["formations"]}
            for p in doc["plays"]:
                if p["play_type"] not in ("pass", "pa_pass") or p["id"] not in home:
                    continue
                name = p["custom_name"]
                if "screen" in name.casefold() or (p.get("concept") or "") in MAX_PROTECT_CONCEPTS \
                        or "max" in name.casefold() or "protect" in name.casefold():
                    continue
                codes = by_name[home[p["id"]]]["position_codes"]
                routes = sum(1 for s, ch in enumerate(p["assignments"])
                             if codes[s] & 31 in (WR, TE, HB, FB) and runs_route(ch))
                if routes < 3:
                    bad.append((team, name, routes))
        self.assertEqual(bad, [])


class Menus(unittest.TestCase):
    def test_whole_pages(self):
        bad = [(team, fid, len(menu)) for team, doc, _cat in shipped() for fid, menu in doc["menus"].items()
               if len(menu) < sanity.PAGE or len(menu) % sanity.PAGE]
        self.assertEqual(bad, [])

    def test_check_mode_is_clean(self):
        self.assertEqual(sanity.main(["--check"]), 0)


if __name__ == "__main__":
    unittest.main()
