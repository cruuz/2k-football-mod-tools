"""b778 pb7: No Huddle plays and quick game for weak offensive lines, checked on the shipped SOFTDRINK offense packs.

* the pack names its five No Huddle plays and the compiler writes them into the PLAY header table at 0x4C (failed on
  the base: the table kept retail formation indices with links 0, 1, 2, 2, 2, so TEN's No Huddle opened on Tush Push
  from Goal Line Sneak and Bubble Screen from Gun Wildcat);
* the five are an inside run, a quick-game pass, a sideline pass, a screen and a shot, from normal-down sets;
* every normal-down menu of TEN (a weak line) lists a quick-game play, most of them two or more (failed on the base:
  five TEN menus had none), and no book lists fewer quick-game plays or has more menus without one than this job left;
* the line grades and the weak-line rule are the documented ones.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_complete_offense as full  # noqa: E402
from mod_editor.core import nfl2k5_playbook_pack as packs  # noqa: E402
from pb.v2 import hurry_b778 as hurry  # noqa: E402
from pb.v2 import sanity_b778 as sanity  # noqa: E402

MANIFEST = ROOT / "pb" / "v2" / "manifest.json"
IMAGE = Path(os.environ.get("NFL2K5_RETAIL_IMAGE", "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))
XBE = Path(os.environ.get("NFL2K5_RETAIL_XBE",
                          "/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe"))
os.environ.setdefault("NFL2K5_SCORING_XBE", str(XBE))

# What this job left (pb/v2/hurry_b778.py --apply --xbe): {team: (quick-game records, normal-down menus without one)}.
# A later change may improve these, never make them worse.
LEFT = {
    "ARZ": (13, 4), "ATL": (11, 4), "BAL": (11, 1), "BUF": (14, 2), "CAR": (15, 0), "CHI": (12, 0), "CIN": (19, 1),
    "CLE": (14, 0), "DAL": (9, 4), "DEN": (17, 0), "DET": (17, 1), "GB": (13, 8), "HOU": (12, 4), "IND": (10, 2),
    "JAX": (15, 1), "KC": (15, 2), "MIA": (11, 6), "MIN": (15, 5), "NE": (17, 0), "NO": (13, 1), "NYG": (14, 3),
    "NYJ": (14, 4), "OAK": (8, 7), "PHI": (12, 0), "PIT": (15, 2), "SD": (13, 4), "SEA": (14, 2), "SF": (13, 3),
    "STL": (15, 1), "TB": (12, 3), "TEN": (20, 0), "WAS": (17, 1),
}
WEAK = {"CLE", "DET", "GB", "LAC", "LV", "MIA", "MIN", "NE", "NO", "NYG", "SEA", "TEN", "WAS"}


def shipped():
    for row in json.loads(MANIFEST.read_text(encoding="utf-8"))["teams"]:
        doc = json.loads((ROOT / row["pack"]).read_text(encoding="utf-8"))
        cat = json.loads((ROOT / "pb" / "v2" / "catalogs" / f"{row['team']}.json").read_text(encoding="utf-8"))
        yield row["team"], doc, cat


def team_doc(team):
    return next((doc, cat) for t, doc, cat in shipped() if t == team)


class PackField(unittest.TestCase):
    def setUp(self):
        self.doc, _cat = team_doc("TEN")

    def test_round_trip(self):
        pack = packs.pack_from_json(self.doc)
        self.assertEqual(len(pack.no_huddle), full.NO_HUDDLE_ENTRIES)
        self.assertEqual(packs.loads_pack(pack.dumps()).no_huddle, pack.no_huddle)
        self.assertEqual(json.loads(pack.dumps())["no_huddle"], self.doc["no_huddle"])

    def test_bad_entries_refuse(self):
        fid, pid = self.doc["no_huddle"][0]
        other = next(f for f, menu in self.doc["menus"].items() if pid not in menu)
        for bad in (self.doc["no_huddle"][:4], self.doc["no_huddle"] + [self.doc["no_huddle"][0]],
                    [[other, pid]] + self.doc["no_huddle"][1:], [[fid, pid]] * 5, [["f99", pid]] + self.doc["no_huddle"][1:],
                    [[fid]] + self.doc["no_huddle"][1:], "f00"):
            with self.subTest(no_huddle=bad):
                edited = copy.deepcopy(self.doc)
                edited["no_huddle"] = bad
                with self.assertRaises(packs.PlaybookPackError):
                    packs.pack_from_json(edited)

    def test_packs_without_the_field_still_load(self):
        edited = copy.deepcopy(self.doc)
        del edited["no_huddle"]
        pack = packs.pack_from_json(edited)
        self.assertEqual(pack.no_huddle, ())
        self.assertNotIn("no_huddle", json.loads(pack.dumps()))


class ShippedNoHuddle(unittest.TestCase):
    def test_every_book_names_five_plays_in_their_roles(self):
        bad = {}
        for team, doc, cat in shipped():
            rows = {r["play"]: r for r in cat["plays"]}
            frows = {f["formation"]: f for f in cat["formations"]}
            forms = {f["id"]: f for f in doc["formations"]}
            plays = {p["id"]: p for p in doc["plays"]}
            nh = doc.get("no_huddle")
            if not nh or len(nh) != 5:
                bad[team] = "missing"
                continue
            for role, (fid, pid) in zip(hurry.NH_ROLES, nh):
                form = forms[fid]
                tag = frows[form["custom_name"]]["tag"]
                if pid not in doc["menus"][fid] or tag not in hurry.NH_FORM_TAGS or form["custom_name"] == "Gun Wildcat" \
                        or hurry.role_score(role, plays[pid], rows.get(pid, {}), form) <= 0:
                    bad.setdefault(team, []).append((role, form["custom_name"], plays[pid]["custom_name"]))
        self.assertEqual(bad, {})

    def test_mostly_shotgun(self):
        # a hurry-up keeps its personnel: at least four of the five come from shotgun sets in every book
        for team, doc, cat in shipped():
            frows = {f["formation"]: f for f in cat["formations"]}
            forms = {f["id"]: f for f in doc["formations"]}
            gun = sum(1 for fid, _pid in doc["no_huddle"] if frows[forms[fid]["custom_name"]]["align"] == "gun")
            self.assertGreaterEqual(gun, 4, team)

    def test_ten_no_longer_opens_on_tush_push(self):
        doc, _cat = team_doc("TEN")
        names = {p["id"]: p["custom_name"] for p in doc["plays"]}
        self.assertNotIn("Tush Push", [names[pid] for _f, pid in doc["no_huddle"]])

    def test_pick_is_stable(self):
        for team, doc, cat in shipped():
            self.assertEqual(hurry.pick_no_huddle(doc, cat), doc["no_huddle"], team)


class ShippedQuickGame(unittest.TestCase):
    def test_ten_every_normal_down_menu_has_one(self):
        doc, cat = team_doc("TEN")
        quick = hurry.quick_ids(doc, cat)
        forms = {f["id"]: f["custom_name"] for f in doc["formations"]}
        short = {forms[fid]: sum(1 for q in doc["menus"][fid] if q in quick) for fid in hurry.floor_menus(doc, cat)}
        self.assertEqual({k: v for k, v in short.items() if v < 1}, {})
        self.assertGreaterEqual(sum(1 for v in short.values() if v >= hurry.QUICK_MIN_WEAK), 15)

    def test_no_book_got_worse(self):
        got = {}
        for team, doc, cat in shipped():
            quick = hurry.quick_ids(doc, cat)
            empty = sum(1 for fid in hurry.floor_menus(doc, cat) if not any(q in quick for q in doc["menus"][fid]))
            got[team] = (len(quick), empty)
        worse = {t: (got[t], LEFT[t]) for t in LEFT if got[t][0] < LEFT[t][0] or got[t][1] > LEFT[t][1]}
        self.assertEqual(worse, {})

    def test_converted_records_are_quick_game_and_lint_clean(self):
        for team, doc, cat in shipped():
            forms = {f["custom_name"]: f for f in doc["formations"]}
            plays = {p["id"]: p for p in doc["plays"]}
            for row in cat["plays"]:
                if row.get("added_by") != "b778 pb7":
                    continue
                p = plays[row["play"]]
                for fname in row["formations"]:
                    with self.subTest(team=team, play=p["custom_name"], formation=fname):
                        self.assertTrue(hurry.is_quick_game(p, forms[fname], row))
                        self.assertTrue(sanity.lint_clean(forms[fname], p))
                        self.assertFalse(sanity.reverses_in(forms[fname], p))

    def test_counts_and_pages(self):
        for team, doc, _cat in shipped():
            used = Counter(pid for menu in doc["menus"].values() for pid in menu)
            self.assertEqual({p["id"] for p in doc["plays"] if p.get("play_type") != "special"}, set(used), team)
            for fid, menu in doc["menus"].items():
                self.assertEqual(len(menu) % 3, 0, (team, fid))
                self.assertEqual(len(menu), len(set(menu)), (team, fid))

    def test_quick_game_classifier(self):
        doc, cat = team_doc("TEN")
        forms = {f["custom_name"]: f for f in doc["formations"]}
        rows = {r["play"]: r for r in cat["plays"]}
        named = {p["custom_name"]: p for p in doc["plays"]}
        home = lambda n: forms[rows[named[n]["id"]]["home"]]  # noqa: E731
        self.assertTrue(hurry.is_quick_game(named["X Double Slants"], home("X Double Slants"), rows[named["X Double Slants"]["id"]]))
        self.assertFalse(hurry.is_quick_game(named["Titans Mills"], home("Titans Mills"), rows[named["Titans Mills"]["id"]]))
        self.assertFalse(hurry.is_quick_game(named["Bubble Screen"], home("Bubble Screen"), rows[named["Bubble Screen"]["id"]]))


class LineGrades(unittest.TestCase):
    def test_grades_and_weak_rule(self):
        grades = hurry.ol_grades()
        self.assertEqual(len(grades["teams"]), 32)
        weak = {t for t, row in grades["teams"].items() if row["pass_block"] < hurry.WEAK_OL_PASS_BLOCK}
        self.assertEqual(weak, WEAK)
        for team in ("TEN", "OAK", "SD", "STL", "ARZ"):
            self.assertEqual(hurry.weak_line(team, grades), hurry.TEAM_ALIAS.get(team, team) in WEAK, team)
        self.assertNotIn("/home/", json.dumps(grades))


@unittest.skipUnless(IMAGE.is_file() and XBE.is_file(), "Retail image / executable unavailable")
class Compiled(unittest.TestCase):
    def test_header_table_holds_the_pack_plays(self):
        from nfl2k5_playbook_pack import _resource_from_image
        from mod_editor.core import nfl2k5_playbook_inspector as insp
        for team in ("TEN", "OAK"):
            doc, _cat = team_doc(team)
            pack = packs.pack_from_json(doc)
            raw = _resource_from_image(IMAGE, team)
            new = packs.apply_pack_to_resource(raw, pack, asset_id="book:" + team, xbe=XBE.read_bytes()).replacement
            book = insp.parse_playbook_resource(new)
            names = {p["id"]: p["custom_name"] for p in doc["plays"]}
            fnames = {f["id"]: f["custom_name"] for f in doc["formations"]}
            got = []
            for n in range(full.NO_HUDDLE_ENTRIES):
                fi, link = new[32 + 0x4C + 2 * n], new[33 + 0x4C + 2 * n]
                f = book.formations[fi]
                play = next(l.play_index for l in f.play_links if l.link_index == link)
                got.append((f.name, book.plays[play].name))
            self.assertEqual(got, [(fnames[f], names[p]) for f, p in doc["no_huddle"]], team)
            # the defense half of the table is untouched by the offense compile
            self.assertEqual(new[32 + 0x56:32 + 0x60], raw[32 + 0x56:32 + 0x60])


if __name__ == "__main__":
    unittest.main()
