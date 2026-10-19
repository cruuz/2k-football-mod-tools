"""b776-fs1: retail face scans for the Anniversary moments and the classic teams (Noah 10/18: "Eli's actual face scan").

Retail-free: the pair table against the shipped face catalog, the roster-side data, the person matching.
Retail-backed (skips without the user's retail game): every pair's relocated spans build and fit, the digest of all 202
spans, and the 35 retail-moment rosters' head decisions on the real resources. Offline evidence only.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tests"), str(ROOT / "tests/mod_editor")]
from mod_editor.core import nfl2k5_classic_teams as ct  # noqa: E402
from mod_editor.core import nfl2k5_espn25_more_moments as mm  # noqa: E402
from mod_editor.core import nfl2k5_espn25_rosters as er  # noqa: E402
from mod_editor.core import nfl2k5_moment_scans as ms  # noqa: E402
from mod_editor.core import nfl2k5_roster_appearance_transfer as at  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from test_nfl2k5_espn25_rosters import RETAIL  # noqa: E402

PLAN_DIGEST = "44e5a0c941d3a9dd593bba091ce1f7de76b1b5f6a610309dad6cd734a241db56"   # sha256 over every (selector, bytes)


def retail_available():
    return (RETAIL / "vc_53450030/0").is_file()


class DataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scans = ms.load()
        cls.catalog = at._catalog()

    def test_the_table_is_complete_and_eli_has_a_new_id(self):
        self.assertEqual(len(self.scans), 39)
        by = {s["name"]: s for s in self.scans}
        self.assertEqual(by["Eli Manning"]["retail"], 6504)
        self.assertNotEqual(by["Eli Manning"]["slot"], 6504)
        self.assertEqual(ms.slots()[6504], by["Eli Manning"]["slot"])
        self.assertEqual(ms.NOPHOTO_BASE, mm.NOPHOTO_BASE)

    def test_every_pair_is_valid_against_the_shipped_face_catalog(self):
        for s in self.scans:
            with self.subTest(name=s["name"]):
                for face in (s["retail"], s["slot"]):
                    for family in ("f", "h", "n", "s", "portrait"):
                        self.assertIn(ms.selector(face, family), self.catalog)
                src = {f: self.catalog[ms.selector(s["retail"], f)] for f in ("f", "h", "n", "s")}
                dst = {f: self.catalog[ms.selector(s["slot"], f)] for f in ("f", "h", "n", "s")}
                # the renamed LZ stream must fit the target's fixed stored allocation
                for family in ("h", "n"):
                    self.assertLessEqual(src[family]["lz"]["consumed_bytes"], dst[family]["stored_size"])
                    self.assertEqual(src[family]["layout_signature_sha256"], dst[family]["layout_signature_sha256"])
                self.assertEqual(src["f"]["span_size"], dst["f"]["span_size"])
                same = src["s"]["span_size"] == dst["s"]["span_size"]
                self.assertEqual(s["shape"] == "copied", same)
                # a generic fallback id is never a source or a target
                self.assertFalse({s["retail"], s["slot"]} & set(range(9001, 9508)))

    def test_validation_refuses_a_shared_or_unsorted_table(self):
        good = json.loads(ms.DATA.read_text(encoding="utf-8"))
        for mutate in (lambda d: d["scans"].append(dict(d["scans"][0])),
                       lambda d: d["scans"][1].update(slot=d["scans"][0]["slot"]),
                       lambda d: d["scans"][1].update(slot=d["scans"][2]["retail"]),
                       lambda d: d["scans"].reverse(),
                       lambda d: d["scans"][0].update(shape="grown"),
                       lambda d: d.update(schema="other")):
            doc = json.loads(json.dumps(good))
            mutate(doc)
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "scans.json"
                path.write_text(json.dumps(doc), encoding="utf-8")
                with self.assertRaises(ms.MomentScansError):
                    ms.load(path)

    def test_name_patch_changes_only_the_name(self):
        raw = bytes(64) + "f6504".encode("utf-16-le") + bytes(100)
        out = ms._patch_name(raw, "f6504", "f2708")
        self.assertEqual(out[:64] + out[74:], raw[:64] + raw[74:])
        self.assertEqual(out[64:74].decode("utf-16-le"), "f2708")
        with self.assertRaises(ms.MomentScansError):
            ms._patch_name(raw, "f0001", "f2708")

    def test_a_main_roster_that_uses_a_target_id_is_refused(self):
        slot = self.scans[0]["slot"]
        ms.check_roster({1, 2, 3})
        with self.assertRaises(ms.MomentScansError):
            ms.check_roster({1, slot})

    def test_people_find_matches_spellings_and_refuses_namesakes(self):
        import datetime
        people = mm.People()

        def add(first, last, year, month, day, value):
            people.setdefault((first.casefold(), last.casefold(), year % 100), value)
            people.by_last.setdefault((last.casefold(), year % 100, month, day), []).append((first, last, value))
            people.by_first.setdefault((first.casefold(), year % 100, month, day), []).append((last, first, value))
        add("Greg", "Rousseau", 2000, 4, 5, (9001, 3303))
        add("Joey", "Porter", 2000, 7, 26, (9002, 7071))
        add("Mike", "Doss", 1981, 3, 24, (9003, 5071))
        d = datetime.date
        self.assertEqual(people.find("Gregory", "Rousseau", d(2000, 4, 5)), (9001, 3303))          # Gregory / Greg
        self.assertEqual(people.find("Joey", "Porter Jr.", d(2000, 7, 26)), (9002, 7071))          # Porter / Porter Jr.
        self.assertEqual(people.find("Greg", "Rousseau", d(2000, 4, 5)), (9001, 3303))             # strict key
        self.assertIsNone(people.find("Mike", "Adams", d(1981, 3, 24)))                            # same first name and birthday
        self.assertIsNone(people.find("Gregory", "Rousseau", d(2000, 4, 6)))                       # another birthday

    def test_the_retail_moment_looks_are_consistent(self):
        manifest, sheets = er.dataset()
        looks = er.appearance()
        self.assertEqual(len(looks), 35)
        slots = ms.slots()
        modes = {}
        for target in manifest["resources"]:
            for row, look in zip(sheets[target["outer"]], looks[target["filename"]]):
                modes[look["mode"]] = modes.get(look["mode"], 0) + 1
                if look["mode"] == "relocate":
                    self.assertIn(look["retail"]["photo"], slots)
                if look["mode"] == "retail":
                    self.assertNotIn(look["retail"]["photo"], slots.values())
        self.assertEqual(modes, {"keep": 1758, "retail": 55, "generic": 38, "relocate": 4})

    def test_added_moment_and_classic_looks_name_only_resolvable_scans(self):
        slots = ms.slots()
        for data in (mm.Data.load(), ct.Data.load()):
            for key, looks in data.appearance.items():
                for look in looks:
                    retail = look.get("retail")
                    if retail:
                        self.assertNotIn(retail["photo"], slots.values(), f"{key} {look['name']}")


class BuildWiringTests(unittest.TestCase):
    def test_the_scans_run_after_every_roster_writer_and_are_preflighted(self):
        source = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        classic = source.index('receipt["result"]["classic_teams"] = classic.image_status(target, retail)')
        step = source.index('scans_receipt = scans.apply_to_image(target, scans_source)')
        self.assertGreater(step, classic)
        self.assertLess(step, source.index("loaded_weather_plan is not None", classic))
        self.assertIn('if receipt["result"]["moment_scans"] != "applied":', source)
        self.assertIn("planned = scans_module.plan(source, source, photos=frozenset())", source)
        for option in ("plan.espn25_rosters", "plan.espn25_more_moments", "plan.classic_teams and plan.historic_teams_quick_game"):
            self.assertIn(option, source[step - 900:step])


@unittest.skipUnless(retail_available(), "user-owned USA disc folder absent")
class RetailTests(unittest.TestCase):
    def test_every_pair_builds_fits_and_is_pinned(self):
        writes = ms.plan(RETAIL, RETAIL, photos=frozenset())          # force every pair, as the preflight does
        self.assertEqual(len(writes), 39 * 4 + 23 * 2)
        digest = hashlib.sha256()
        for selector, _offset, expected, current in writes:
            digest.update(selector.encode() + expected)
            self.assertEqual(len(expected), len(current))
            self.assertNotEqual(expected, current)
        self.assertEqual(digest.hexdigest(), PLAN_DIGEST)
        # on a stock retail roster the retired players still hold their ids: only pairs whose target id nobody holds
        # are active (one: id 0544), the others are skipped because their retail heads are intact
        active = ms.plan(RETAIL, RETAIL)
        self.assertEqual({sel.split(":")[0] if not sel.startswith("portrait") else sel[9:] for sel, *_ in active}, {"0544"})
        self.assertEqual(ms.image_status(RETAIL, RETAIL), "retail")

    def test_the_retail_moment_rosters_follow_their_looks_and_nothing_else_moves(self):
        manifest, sheets = er.dataset()
        looks, slots = er.appearance(), ms.slots()
        with rr._outer_image()(RETAIL) as archive:
            retail = {t["outer"]: archive.read_entry(t["outer"]) for t in manifest["resources"]}
        out, receipt = er.apply(retail)
        self.assertEqual(er.status(out), "applied")
        head_fields = ("photo_id", "skin_low", "skin_high", "face", "dreads")
        seen = set()
        for t in manifest["resources"]:
            before = rr.RosterDocument(retail[t["outer"]][32:])
            after = rr.RosterDocument(out[t["outer"]][32:])
            for a, b, look in zip(before.players, after.players, looks[t["filename"]]):
                seen.add(look["mode"])
                va, vb = a.record.values, b.record.values
                mode = look["mode"]
                moved = {k for k in va if va[k] != vb[k]} - {"first_name_pointer", "last_name_pointer", "jersey", "college_pointer", "hand"}
                if mode == "keep":
                    self.assertEqual(moved, set(), look["name"])
                    continue
                self.assertLessEqual(moved, set(head_fields), look["name"])
                if mode == "generic":
                    self.assertEqual(vb["photo_id"], ms.NOPHOTO_BASE + b.index)
                else:
                    r = look["retail"]
                    self.assertEqual(vb["photo_id"], slots[r["photo"]] if mode == "relocate" else r["photo"])
                    self.assertEqual((b.record.skin, vb["face"], vb["dreads"]), (r["skin"], r["face"], r["dreads"]))
                self.assertEqual(a.record.ratings(), b.record.ratings())
        self.assertEqual(seen, {"keep", "retail", "relocate", "generic"})


if __name__ == "__main__":
    unittest.main()
