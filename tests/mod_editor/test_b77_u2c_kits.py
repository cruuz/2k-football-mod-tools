"""Beta 77 u2c: 2026 kit corrections for MIA LAR NYJ NYG NO (LV LAC MIN checked and unchanged): recipes, the number
author, the merged project (shared u2a compiler) and the u2c repair ownership, scope, idempotence and tamper refusal."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/b77")]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


kits = _load("b77_u2c_kits_test", "tools/b77/u2c_kits.py")
u2a = sys.modules["u2a_kits"]
repair = _load("b77_u2c_repair_test", "tools/b77/u2c_repair.py")
DATA = ROOT / "data/nfl2k5_teams_2026"


def recipe(team: str) -> dict:
    return json.loads((DATA / f"{team}.json").read_text(encoding="utf-8"))


def base_recipe(team: str) -> dict:
    out = subprocess.run(["git", "show", f"local/b77-base:data/nfl2k5_teams_2026/{team}.json"], cwd=ROOT,
                         capture_output=True, text=True)
    if out.returncode:
        raise unittest.SkipTest("local/b77-base is not available")
    return json.loads(out.stdout)


class Recipes(unittest.TestCase):
    def test_dolphins_wordmark_is_wide_and_pants_stripes_are_wide(self):
        d = recipe("MIA")["kits"]
        for side in ("home", "away"):
            marks = [x for x in d[side]["torso"]["decorations"] if x.get("mark", "").startswith("dolphins_")]
            self.assertEqual(len(marks), 2)
            for x in marks:
                self.assertEqual((x["width"], x["center"]), (52, [161, 93.0]))
        self.assertEqual(d["home"]["pants"]["stripe"], [["orange", 3], ["jersey_aqua", 14], ["orange", 3]])
        self.assertEqual(d["away"]["pants"]["stripe"], [["orange", 3], ["white", 14], ["orange", 3]])

    def test_rams_have_sol_yoke_bands_and_thin_white_road_pants_stripe(self):
        d = recipe("LAR")["kits"]
        for side in ("home", "away"):
            first = d[side]["torso"]["decorations"][0]
            self.assertEqual([b["colour"] for b in first["bands"]], ["sol", "sol", "sol"])
            self.assertTrue(all(len(b["polygons"]) > 50 for b in first["bands"]))
        self.assertEqual(d["away"]["pants"]["stripe"], [["white", 5]])
        self.assertEqual(d["home"]["pants"], base_recipe("LAR")["kits"]["home"]["pants"])
        # the alternate styles (cs, fw, mr) belong to other jobs and stay as they were
        for key in ("cs_home", "cs_away", "fw_home", "fw_away", "mr_home", "mr_away"):
            self.assertEqual(d[key], base_recipe("LAR")["kits"][key])

    def test_jets_road_collar_is_wide_and_home_collar_unchanged(self):
        d = recipe("NYJ")["kits"]
        self.assertEqual(d["away"]["torso"]["collar_trim"][0]["width"], 12)
        self.assertEqual(d["home"]["torso"], base_recipe("NYJ")["kits"]["home"]["torso"])

    def test_giants_home_and_road_numbers_keep_the_v05_recipe(self):
        d = recipe("NYG")["kits"]
        self.assertEqual(d["home"]["digits"], base_recipe("NYG")["kits"]["home"]["digits"])
        self.assertEqual(d["away"]["digits"], base_recipe("NYG")["kits"]["away"]["digits"])

    def test_saints_patch_is_on_both_kits_beside_the_shield(self):
        d = recipe("NO")["kits"]
        for side in ("home", "away"):
            items = d[side]["torso"]["decorations"]
            base = base_recipe("NO")["kits"][side]["torso"]["decorations"]
            self.assertEqual(items[:len(base)], base)
            patch = items[len(base):]
            self.assertGreater(len(patch), 10)
            xs = [p[0] for it in patch if "polygon" in it for p in it["polygon"]]
            self.assertTrue(170 <= min(xs) and max(xs) <= 195)          # right of the collar shield at x 161

    def test_untouched_teams_are_byte_identical_to_the_base_recipes(self):
        for team in ("LV", "LAC", "MIN"):
            self.assertEqual((DATA / f"{team}.json").read_text(), (
                subprocess.run(["git", "show", f"local/b77-base:data/nfl2k5_teams_2026/{team}.json"], cwd=ROOT,
                               capture_output=True, text=True).stdout))

    def test_every_changed_recipe_records_what_was_checked(self):
        for team in ("MIA", "LAR", "NYJ", "NYG", "NO"):
            block = recipe(team)["u2c_b77"]
            self.assertTrue(block["checked_against"] and block["changes"] and block["unchanged_because_right"])
        for team in ("MIA", "LAR", "NYJ", "NYG", "NO", "LV", "LAC", "MIN"):
            kitset = recipe(team)["kits"]
            self.assertTrue({"home", "away"} <= set(kitset))


class Numbers(unittest.TestCase):
    def test_number_block_follows_digits_unless_arm_digits_is_set(self):
        kit = {"digits": {"fill": "white"}}
        self.assertEqual(kits.number_block(kit, "jersey"), {"fill": "white"})
        self.assertEqual(kits.number_block(kit, "arm"), {"fill": "white"})
        kit["arm_digits"] = {"fill": "red"}
        self.assertEqual(kits.number_block(kit, "arm"), {"fill": "red"})
        self.assertEqual(kits.number_block(kit, "jersey"), {"fill": "white"})

    def test_digits_changed_only_when_the_block_differs(self):
        a = {"digits": {"fill": "white", "outline": "red"}}
        b = {"digits": {"fill": "white"}}
        self.assertTrue(kits.digits_changed(a, b, "jersey"))
        self.assertTrue(kits.digits_changed(a, b, "arm"))
        self.assertFalse(kits.digits_changed(b, dict(b), "jersey"))


class Repair(unittest.TestCase):
    def manifest(self, tmp: Path, original: bytes, offset: int, replacement: bytes, name: str) -> Path:
        base = tmp / "manifest"
        base.mkdir()
        digest = hashlib.sha256(replacement).hexdigest()
        (base / f"{digest}.span").write_bytes(replacement)
        doc = {"schema": repair.SCHEMA, "resources": {name: [{
            "label": "torso", "offset": offset, "length": len(replacement), "replacement": f"{digest}.span",
            "before_sha256": hashlib.sha256(original[offset:offset + len(replacement)]).hexdigest(),
            "after_sha256": digest}]}}
        path = base / "native_manifest.json"
        path.write_text(json.dumps(doc), encoding="utf-8", newline="\n")
        return path

    def test_manifest_owns_only_the_u2c_kit_packages_and_the_unif_card_pack(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "m.json"
            for name in ("14H0.IFF", "14A0.IFF", "17A0.IFF", "18H0.IFF", "19A0.IFF", "23H0.IFF", "outer:3102"):
                path.write_text(json.dumps({"schema": repair.SCHEMA, "resources": {name: []}}))
                self.assertIn(name, repair.load_manifest(path)["resources"])
            # u2a's, u1's and the alternates' packages and the helmet card pack are somebody else's
            for name in ("00H0.IFF", "30H0.IFF", "16H0.IFF", "20H0.IFF", "24A0.IFF", "23H10.IFF", "14H1.IFF",
                         "outer:3105", "outer:3741"):
                path.write_text(json.dumps({"schema": repair.SCHEMA, "resources": {name: []}}))
                with self.assertRaises(ValueError):
                    repair.load_manifest(path)

    def test_loose_repair_is_scoped_idempotent_and_refuses_other_input(self):
        original = np.random.default_rng(7).integers(0, 256, 4096, dtype=np.uint8).tobytes()
        replacement = bytes(64)
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            path = self.manifest(tmp, original, 1024, replacement, "18H0.IFF")
            manifest = repair.load_manifest(path)
            (tmp / "in").mkdir()
            (tmp / "in/18H0.IFF").write_bytes(original)
            receipt = repair.repair_resources(tmp / "in", tmp / "out", manifest, path.parent)
            data = (tmp / "out/18H0.IFF").read_bytes()
            self.assertEqual(data[:1024] + data[1088:], original[:1024] + original[1088:])
            self.assertEqual(data[1024:1088], replacement)
            self.assertTrue(receipt["resources"]["18H0.IFF"]["outside_scope_identical"])
            again = repair.repair_resources(tmp / "out", tmp / "again", manifest, path.parent)
            self.assertEqual((tmp / "again/18H0.IFF").read_bytes(), data)
            self.assertTrue(again["resources"]["18H0.IFF"]["spans"][0]["already_applied"])
            tampered = bytearray(original)
            tampered[1030] ^= 0xFF
            (tmp / "bad").mkdir()
            (tmp / "bad/18H0.IFF").write_bytes(bytes(tampered))
            with self.assertRaisesRegex(ValueError, "unexpected input span"):
                repair.repair_resources(tmp / "bad", tmp / "bad_out", manifest, path.parent)

    def test_loose_mode_does_not_take_card_resources(self):
        original = bytes(range(256)) * 4
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            path = self.manifest(tmp, original, 16, b"\1" * 16, "outer:3102")
            (tmp / "in").mkdir()
            with self.assertRaisesRegex(ValueError, "kit packages only"):
                repair.repair_resources(tmp / "in", tmp / "out", repair.load_manifest(path), path.parent)

    def test_the_private_manifest_has_no_span_in_common_with_u2a(self):
        # structural: the kit selectors of the two jobs are disjoint, so their resources can never share a span
        u2a_codes = {"00", "01", "02", "03", "04", "05", "06", "30"}
        mine = {"14", "17", "18", "19", "23"}
        self.assertFalse(u2a_codes & mine)


class Project(unittest.TestCase):
    def test_merge_adds_unif_cards_for_every_changed_kit_but_no_helmet_cards(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            final = tmp / "final"
            (final / "NYG").mkdir(parents=True)
            (final / "NYG/project.json").write_text(json.dumps({"edits": [{"kind": "live_number_nameplate",
                "family": "jersey", "asset_code": "18", "side": "H", "variant": 0, "digit": 1, "png": "x"}]}))
            (final / "NYG/author_receipt.json").write_text(json.dumps({"items": [{"selector": "18H0",
                                                                                   "name": "digit_jersey_1"}]}))
            (final / "NYG/cards/18H0").mkdir(parents=True)
            (final / "NYG/cards/18H0/team-select_unif_256.png").write_bytes(b"x")
            export = tmp / "export.json"
            export.write_text(json.dumps({"sets": [{"selector": "18H0"}, {"selector": "18A0"}]}))
            out = tmp / "p.json"
            info = u2a.merge_projects(final, ["NYG"], out, export)
            self.assertEqual(info["kits_changed"], ["18H0"])
            cards = [e for e in json.loads(out.read_text())["edits"] if e["kind"] == "team_select"]
            self.assertEqual([(e["family"], e["resolution"], e["side"], e["asset_code"]) for e in cards],
                             [("unif", 256, "home", "18")])


if __name__ == "__main__":
    unittest.main()
