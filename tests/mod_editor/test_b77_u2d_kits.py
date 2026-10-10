"""Beta 77 u2d: 2026 kit corrections for PHI PIT SEA SF TB TEN WAS: recipes, the shared u2a authoring helpers
(scope, merge, project job label) and the u2d repair (ownership, scope, idempotence, tamper refusal)."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


kits = _load("b77_u2a_kits_test", "tools/b77/u2a_kits.py")
repair = _load("b77_u2d_repair_test", "tools/b77/u2d_repair.py")
DATA = ROOT / "data/nfl2k5_teams_2026"


def recipe(team: str) -> dict:
    return json.loads((DATA / f"{team}.json").read_text(encoding="utf-8"))


class Recipes(unittest.TestCase):
    def test_selectors_and_codes_of_the_seven_teams(self):
        codes = {"PHI": "21", "PIT": "22", "SEA": "26", "SF": "25", "TB": "27", "TEN": "28", "WAS": "29"}
        for team, code in codes.items():
            d = recipe(team)
            self.assertEqual(d["asset_code"], code)
            self.assertEqual(d["kits"]["home"]["selector"], f"{code}H0")
            self.assertEqual(d["kits"]["away"]["selector"], f"{code}A0")

    def test_phi_is_unchanged_from_the_base_recipe(self):
        self.assertNotIn("u2d_b77", recipe("PHI"))

    def test_steelers_wider_pants_stripe_and_gold_road_collar(self):
        d = recipe("PIT")["kits"]
        for side in ("home", "away"):
            self.assertEqual(d[side]["pants"]["stripe"], [["black", 24]])
        self.assertEqual(d["away"]["torso"]["collar_trim"], [{"colour": "gold", "width": 8}])
        self.assertNotIn("collar_trim", d["home"]["torso"])

    def test_seahawks_road_is_all_white_with_white_socks(self):
        a = recipe("SEA")["kits"]["away"]
        self.assertEqual(a["pants"]["base_colour"], "white")
        self.assertEqual(a["socks"]["colour"], "white")
        self.assertEqual(recipe("SEA")["kits"]["home"]["pants"]["base_colour"], "pants_navy")   # home unchanged

    def test_49ers_wordmark_size_and_place(self):
        for side in ("home", "away"):
            mark = recipe("SF")["kits"][side]["torso"]["chest_mark"]
            self.assertEqual((mark["width"], mark["center"]), (30, [161, 100]))

    def test_buccaneers_thin_pants_seam_stripe(self):
        for side in ("home", "away"):
            stripe = recipe("TB")["kits"][side]["pants"]["stripe"]
            self.assertEqual(sum(n for _, n in stripe), 7)

    def test_titans_wordmarks_enlarged(self):
        d = recipe("TEN")["kits"]
        self.assertEqual(d["home"]["torso"]["decorations"][0]["width"], 55)
        self.assertEqual(d["away"]["torso"]["decorations"][0]["width"], 66)

    def test_commanders_road_collar_and_striped_white_socks_in_the_recipe(self):
        a = recipe("WAS")["kits"]["away"]
        self.assertEqual(a["torso"]["collar_trim"][0]["width"], 13)
        self.assertEqual(a["socks"]["colour"], "white")
        self.assertEqual([b["colour"] for b in a["socks"]["stripes"]], ["burgundy", "gold"])
        self.assertEqual(recipe("WAS")["kits"]["home"]["socks"]["colour"], "burgundy")


class Project(unittest.TestCase):
    def test_merge_projects_labels_the_job_and_teams(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            final = tmp / "final"
            (final / "AAA/cards/22A0").mkdir(parents=True)
            (final / "AAA/project.json").write_text(json.dumps({"edits": []}))
            (final / "AAA/author_receipt.json").write_text(json.dumps({"items": [{"selector": "22A0", "name": "pants"}]}))
            (final / "AAA/cards/22A0/team-select_unif_256.png").write_bytes(b"x")
            export = tmp / "export.json"
            export.write_text(json.dumps({"sets": [{"selector": "22A0"}]}))
            out = tmp / "p.json"
            kits.merge_projects(final, ["AAA"], out, export, "u2d")
            self.assertEqual(json.loads(out.read_text())["purpose"], "b77 u2d: 2026 kits of AAA")


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

    def test_manifest_owns_the_six_changed_teams_kits_and_the_two_card_packs(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "m.json"
            good = ["22H0.IFF", "22A0.IFF", "25H0.IFF", "26A0.IFF", "27H0.IFF", "28A0.IFF", "29A0.IFF"]
            for name in good + ["outer:3102", "outer:3105"]:
                path.write_text(json.dumps({"schema": repair.SCHEMA, "resources": {name: []}}))
                self.assertIn(name, repair.load_manifest(path)["resources"])
            for name in ("16H0.IFF", "21H0.IFF", "00H0.IFF", "30A0.IFF", "outer:3741", "22B0.IFF", "22H1.IFF"):
                path.write_text(json.dumps({"schema": repair.SCHEMA, "resources": {name: []}}))
                with self.assertRaises(ValueError):
                    repair.load_manifest(path)
            path.write_text(json.dumps({"schema": "b77/u2a/texture-repair/v1", "resources": {"22H0.IFF": []}}))
            with self.assertRaises(ValueError):
                repair.load_manifest(path)

    def test_loose_repair_is_scoped_idempotent_and_refuses_other_input(self):
        original = np.random.default_rng(5).integers(0, 256, 4096, dtype=np.uint8).tobytes()
        replacement = bytes(64)
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td).resolve()
            path = self.manifest(tmp, original, 1024, replacement, "28H0.IFF")
            manifest = repair.load_manifest(path)
            (tmp / "in").mkdir()
            (tmp / "in/28H0.IFF").write_bytes(original)
            receipt = repair.repair_resources(tmp / "in", tmp / "out", manifest, path.parent)
            data = (tmp / "out/28H0.IFF").read_bytes()
            self.assertEqual(data[:1024] + data[1088:], original[:1024] + original[1088:])
            self.assertEqual(data[1024:1088], replacement)
            self.assertTrue(receipt["resources"]["28H0.IFF"]["outside_scope_identical"])
            again = repair.repair_resources(tmp / "out", tmp / "again", manifest, path.parent)
            self.assertEqual((tmp / "again/28H0.IFF").read_bytes(), data)
            self.assertTrue(again["resources"]["28H0.IFF"]["spans"][0]["already_applied"])
            tampered = bytearray(original)
            tampered[1030] ^= 0xFF
            (tmp / "bad").mkdir()
            (tmp / "bad/28H0.IFF").write_bytes(bytes(tampered))
            with self.assertRaisesRegex(ValueError, "unexpected input span"):
                repair.repair_resources(tmp / "bad", tmp / "bad_out", manifest, path.parent)

    def test_loose_mode_does_not_take_card_resources(self):
        original = bytes(range(256)) * 4
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td).resolve()
            path = self.manifest(tmp, original, 16, b"\1" * 16, "outer:3105")
            (tmp / "in").mkdir()
            with self.assertRaisesRegex(ValueError, "kit packages only"):
                repair.repair_resources(tmp / "in", tmp / "out", repair.load_manifest(path), path.parent)


if __name__ == "__main__":
    unittest.main()
