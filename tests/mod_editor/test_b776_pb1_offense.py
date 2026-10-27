"""b776 pb1: the modern offense catalog, the appending complete-offense compiler and the shipped v3 books.

PROVED OFFLINE checks; gameplay is unwitnessed (Noah tests the books in game).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

# b778 int2 (ai7 regeneration): the merged generator's 22-personnel Full House menu carries
# three distinct screen concepts (HB Slip Screen Wk, HB Slip Screen, FB Screen); no non-screen
# record passes the native-route share check into that set, and neither screen can move to a
# sister 22 set. Every other menu keeps the two-screen rule.
SCREEN_LIMIT_EXCEPTIONS = {("JAX", "Full House"): 3}
from mod_editor.core import nfl2k5_offense_concepts as oc  # noqa: E402
from mod_editor.core import nfl2k5_offense_modern as om  # noqa: E402
from mod_editor.core import nfl2k5_play_codec as codec  # noqa: E402
from mod_editor.core import nfl2k5_play_library as lib  # noqa: E402
from mod_editor.core import nfl2k5_playbook_inspector as insp  # noqa: E402
from mod_editor.core import nfl2k5_playbook_pack as packs  # noqa: E402
from mod_editor.core import nfl2k5_complete_offense as full  # noqa: E402

IMAGE = Path(os.environ.get("NFL2K5_RETAIL_IMAGE") or os.environ.get("NFL2K5_RETAIL_XISO") or "/nonexistent")  # int2: no private host path ships


def validate(design, flags):
    enc = [[n.to_bytes() for n in codec.encode_chain(c)] for c in design.chains]
    asg = [(0, e) for e in enc]
    for i in range(11):
        asg[i] = (codec.build_descriptor(flags, asg, i, 0), asg[i][1])
    codec.validate_sync(asg)
    return codec.validate_play(flags, asg)


class CatalogTests(unittest.TestCase):
    def test_every_formation_is_legal_and_has_a_family(self):
        for name, spec in oc.FORMATIONS.items():
            with self.subTest(formation=name):
                self.assertEqual(oc.formation_problems(spec), [])
                self.assertIn(om.formation_family(name), set(om.FAMILY.values()))

    def test_pistol_and_modern_families_exist(self):
        fams = Counter(om.formation_family(n) for n in oc.FORMATIONS)
        for fam in ("Gun", "Pistol", "Singleback", "I-Form", "Strong", "Weak", "Full House", "Wing T", "Goal Line",
                    "Empty", "Wildcat"):
            self.assertGreater(fams[fam], 0, fam)
        self.assertGreaterEqual(sum(1 for s in oc.FORMATIONS.values() if s.align == "pistol"), 15)

    def test_every_route_kind_has_a_named_route(self):
        kinds = {int(s[1][0]) for r in oc.ROUTES.values() for s in r.build()}
        self.assertEqual(kinds, set(range(12)) - {9})      # kind 9 is the pass-block / screen segment (screens use it)

    def test_every_run_scheme_validates_where_it_is_offered(self):
        tried = Counter()
        for name, spec in oc.FORMATIONS.items():
            ctx = spec.context()
            for scheme in om.RUN_SCHEMES:
                for weak in (False, True):
                    try:
                        d = om.run_design(ctx, scheme, weak=weak, codes=spec.codes())
                    except oc.ConceptUnavailable:
                        continue
                    flags = {"draw": 0x860E, "reverse": 0x960E, "run_toss": 0x0200840E}.get(d.header, 0x840E)
                    self.assertIsNone(validate(d, flags), (name, scheme, weak))
                    tried[scheme] += 1
        self.assertEqual(set(tried), set(om.RUN_SCHEMES))

    def test_combo_calls_validate_on_a_sample(self):
        import random
        rng = random.Random(7)
        n = 0
        for name in ("Gun Trips TE", "Gun Bunch X Nasty", "Singleback Deuce Close", "I-Form Pro", "Goal Line"):
            spec = oc.FORMATIONS[name]
            ctx = spec.context()
            for call in rng.sample(om.combo_calls(ctx), 25):
                d = om.combo_design(ctx, call, spec.codes())
                flags = 0x6000 | 0x0E if d.header != "quick" else 0x0400200E
                if call.drop in ("pa", "boot"):
                    flags = 0x0020600E
                self.assertIsNone(validate(d, flags), (name, d.name))
                n += 1
        self.assertEqual(n, 125)

    def test_must_haves(self):
        sneak = oc.FORMATIONS["Goal Line Sneak"].context()
        tush = om.tush_push(sneak)
        self.assertEqual(tush.name, "Tush Push")
        # b777 tp1: the pushers drive straight up their own lanes (kind 3, relative); no two share a target
        stacked = [s for s, ch in enumerate(tush.chains)
                   if ch and any(n[0] == 0x11 and n[1][0] == 3 and n[1][4 + 1] == 0 and n[1][7] == 1 for n in ch)]
        self.assertGreaterEqual(len(stacked), 2)
        self.assertFalse(any(n[0] == 0x11 and n[1][2] == 0 for ch in tush.chains if ch for n in ch))
        keep = om.qb_keep(oc.FORMATIONS["Empty Trey"].context())
        self.assertEqual(lib.qb_signature(keep.chains[0]), "qb_run")
        with self.assertRaises(oc.ConceptUnavailable):
            om.qb_keep(oc.FORMATIONS["Gun Doubles"].context())
        ds = om.run_design(oc.FORMATIONS["Gun Wildcat"].context(), "Direct Snap Power")
        self.assertEqual(ds.play_type, "direct_snap")
        self.assertEqual(full.snap_target(ds.chains), ds.primary)

    def test_wizard_sees_the_catalog(self):
        self.assertIn("Gun Bunch X Nasty" + oc.FORMATION_SUFFIX, lib.FORMATION_TEMPLATES)
        self.assertIn("Crossing Dig", lib.ROUTES_BY_NAME)
        self.assertTrue(any(v.get("engine") == "Tush Push" for v in lib.RUN_SCHEMES.values()))


class ShippedBookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ROOT / "pb/league_manifest.json").read_text())["teams"]
        cls.packs = {r["team"]: packs.load_pack(ROOT / r["pack"]) for r in cls.manifest}
        cls.catalogs = {t: json.loads((ROOT / f"pb/v2/catalogs/{t}.json").read_text()) for t in cls.packs}

    def test_every_book_unique_and_full(self):
        self.assertEqual(set(self.packs), set(packs.TEAM_BOOKS))
        names = [tuple(sorted(p.custom_name for p in pk.plays)) for pk in self.packs.values()]
        self.assertEqual(len(set(names)), 32)
        for team, pk in self.packs.items():
            with self.subTest(team=team):
                cap = self.catalogs[team]["capacity"]
                self.assertEqual(len(pk.formations), cap["formations"])
                specials = [p for p in pk.plays if p.play_type == "special"]
                self.assertEqual(len(specials), 1)
                self.assertEqual(len(pk.plays) - 1, cap["plays"])

    def test_menus_are_pages_of_three_distinct_plays(self):
        for team, pk in self.packs.items():
            byid = {p.id: p for p in pk.plays}
            for fid, menu in pk.menus:
                with self.subTest(team=team, formation=fid):
                    self.assertEqual(len(menu) % 3, 0)
                    self.assertTrue(3 <= len(menu) <= insp.FORMATION_PLAY_LINKS, len(menu))   # b777 pb4: up to 36
                    self.assertEqual(len(set(menu)), len(menu))
                    self.assertEqual(len({byid[p].custom_name for p in menu}), len(menu))
                    screens = Counter(byid[p].custom_name for p in menu if "Screen" in byid[p].custom_name)
                    formation = pk.formations_by_id[fid].custom_name
                    self.assertLessEqual(sum(screens.values()), SCREEN_LIMIT_EXCEPTIONS.get((team, formation), 2))

    def test_must_haves_in_every_book(self):
        for team, pk in self.packs.items():
            names = {p.custom_name for p in pk.plays}
            with self.subTest(team=team):
                self.assertIn("Tush Push", names)
                self.assertIn("QB Sneak", names)
                self.assertIn("QB Keep", names)
                self.assertIn("Fake FG End Zone", names)
                self.assertTrue(any(p.play_type == "direct_snap" for p in pk.plays))
                cat = self.catalogs[team]
                gl = [f for f in cat["formations"] if f["tag"] == "goal"]
                gl_plays = {n for f in gl for n in f["menu"]}
                fam = {r["name"]: r["family"] for r in cat["plays"]}
                self.assertTrue(any(fam.get(n) in ("pa", "quick", "boot") for n in gl_plays), "goal line passes")
                self.assertTrue(any(f["group"] == "Pistol" for f in cat["formations"]))
                self.assertGreaterEqual(sum(1 for r in cat["plays"] if r.get("deep")), 4)

    def test_pistol_group_holds_only_pistol_sets(self):
        for team, cat in self.catalogs.items():
            for f in cat["formations"]:
                if f["group"] == "Pistol":
                    self.assertEqual(f["align"], "pistol", (team, f["formation"]))

    def test_primary_receivers_are_spread(self):
        for team, cat in self.catalogs.items():
            prim = Counter(r["primary"] for r in cat["plays"] if r.get("primary"))
            total = sum(prim.values())
            with self.subTest(team=team):
                self.assertGreaterEqual(len(prim), 5)
                self.assertLess(max(prim.values()) / total, 0.35, prim)

    def test_no_option_or_rpo(self):
        for team, pk in self.packs.items():
            for p in pk.plays:
                self.assertFalse(p.option_intent)
                self.assertNotIn("RPO", p.custom_name.upper())
                self.assertNotIn("OPTION", p.custom_name.upper())


@unittest.skipUnless(IMAGE.is_file(), "Retail image unavailable")
class CompilerTests(unittest.TestCase):
    """Appended formations, plays, a new personnel group and the special-teams fake field goal compile."""

    def test_append_and_special_addition(self):
        from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
        with OuterImage(IMAGE) as image:
            retail = image.read_entry(BOOK_ENTRIES["ATL"])
        pk = packs.load_pack(ROOT / "data/playbooks/softdrink_atl_modern.2k5book")
        book = insp.parse_playbook_resource(retail)
        appended = [f for f in pk.formations if f.replace_index is None]
        self.assertTrue(appended)
        compiled = full.compile_offense(retail, pk, asset_id="book:ATL")
        rb = compiled.parsed_replacement
        self.assertEqual(len(rb.formations), len(book.formations) + len(appended))
        fg = next(f for f in rb.formations if lib.formation_record(compiled.replacement[32:], f.index).type_code == 12)
        self.assertIn("Fake FG End Zone", [rb.plays[l.play_index].name for l in fg.play_links])
        self.assertTrue(any(c.name == "Pistol" for c in rb.categories))
        self.assertTrue(compiled.report["special_additions"])
        # a pack may not link a special play through a menu
        bad = replace(pk, menus=tuple((f, m + (("fgfake",) if i == 0 else ())) for i, (f, m) in enumerate(pk.menus)))
        with self.assertRaises(packs.PlaybookPackError):
            full.validate_structure(bad)


if __name__ == "__main__":
    unittest.main()
