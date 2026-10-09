"""Beta 77 u2b: 2026 kit corrections for DAL DEN DET GB HOU IND JAX KC: the recipes and the repair of the four changed
teams (DAL DEN DET HOU). The authoring helpers are u2a's (tools/b77/u2a_kits.py, tested in test_b77_u2a_kits)."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


repair = _load("b77_u2b_repair_test", "tools/b77/u2b_repair.py")
DATA = ROOT / "data/nfl2k5_teams_2026"


def recipe(team: str) -> dict:
    return json.loads((DATA / f"{team}.json").read_text(encoding="utf-8"))


def mark(kit: dict, name: str) -> dict:
    return next(x for x in kit["torso"]["decorations"] if x.get("mark") == name)


class Recipes(unittest.TestCase):
    def test_all_eight_recipes_keep_their_selectors(self):
        sel = {"DAL": ("07", "07A0", "07H0"), "DEN": ("08", "08H0", "08A0"), "DET": ("09", "09H0", "09A0"),
               "GB": ("10", "10H0", "10A0"), "HOU": ("37", "37H0", "37A0"), "IND": ("11", "11H0", "11A0"),
               "JAX": ("12", "12H0", "12A0"), "KC": ("13", "13H0", "13A0")}
        for team, (code, home, away) in sel.items():
            d = recipe(team)
            self.assertEqual(d["asset_code"], code)
            self.assertEqual(d["kits"]["home"]["selector"], home)
            self.assertEqual(d["kits"]["away"]["selector"], away)

    def test_cowboys_road_wordmark_smaller_and_lower_and_home_pants_silver_blue(self):
        d = recipe("DAL")["kits"]
        m = mark(d["away"], "cowboys_wordmark")
        self.assertEqual((m["width"], m["center"]), (28, [162, 102.2]))
        self.assertEqual(d["home"]["pants"]["base_colour"], "seafoam_blue")
        self.assertEqual(recipe("DAL")["albedo"]["seafoam_blue"], "#9DB9C1")

    def test_broncos_wordmark_and_navy_road_pants(self):
        d = recipe("DEN")["kits"]
        for side in ("home", "away"):
            m = mark(d[side], "chest_wordmark")
            self.assertEqual((m["width"], m["center"][1]), (35, 104.8))
        pants = d["away"]["pants"]
        self.assertEqual(pants["base_colour"], "navy")
        colours = {x["colour"] for x in pants["decorations"]}
        self.assertEqual(colours, {"navy", "white", "orange"})
        self.assertEqual(d["home"]["pants"]["base_colour"], "white")      # the home look is unchanged

    def test_lions_road_wordmark_and_home_sleeve_stripes_join(self):
        d = recipe("DET")["kits"]
        m = mark(d["away"], "detroit")
        self.assertEqual((m["width"], m["center"]), (51, [161, 101.1]))
        colours = [x["colour"] for x in d["home"]["sleeve"]["decorations"]]
        self.assertEqual(colours.count("silver"), 8)                    # four silver bands and the four lines that now meet them

    def test_texans_wordmarks(self):
        d = recipe("HOU")["kits"]
        self.assertEqual((mark(d["home"], "word_texans")["width"], mark(d["home"], "word_texans")["center"][1]), (48, 99.8))
        self.assertEqual((mark(d["away"], "word_houston")["width"], mark(d["away"], "word_houston")["center"][1]), (55, 103.0))

    def test_changed_teams_carry_their_notes_and_unchanged_teams_do_not(self):
        for team in ("DAL", "DEN", "DET", "HOU"):
            self.assertIn("u2b_b77", recipe(team))
            self.assertIn("changes", recipe(team)["u2b_b77"])
        for team in ("GB", "IND", "JAX", "KC"):
            self.assertNotIn("u2b_b77", recipe(team))


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

    def test_manifest_owns_the_four_teams_kits_and_the_card_resource(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "m.json"
            for name in ["07H0.IFF", "07A0.IFF", "08H0.IFF", "08A0.IFF", "09H0.IFF", "09A0.IFF", "37H0.IFF", "37A0.IFF",
                         "outer:3102"]:
                path.write_text(json.dumps({"schema": repair.SCHEMA, "resources": {name: []}}))
                self.assertIn(name, repair.load_manifest(path)["resources"])
            for name in ("16H0.IFF", "10H0.IFF", "11A0.IFF", "12H0.IFF", "13A0.IFF", "00H0.IFF", "07H1.IFF", "outer:3741"):
                path.write_text(json.dumps({"schema": repair.SCHEMA, "resources": {name: []}}))
                with self.assertRaises(ValueError):
                    repair.load_manifest(path)
            path.write_text(json.dumps({"schema": "b77/u2a/texture-repair/v1", "resources": {"07H0.IFF": []}}))
            with self.assertRaises(ValueError):
                repair.load_manifest(path)

    def test_loose_repair_is_scoped_idempotent_and_refuses_other_input(self):
        import numpy as np
        original = np.random.default_rng(7).integers(0, 256, 4096, dtype=np.uint8).tobytes()
        replacement = bytes(64)
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            path = self.manifest(tmp, original, 1024, replacement, "08A0.IFF")
            manifest = repair.load_manifest(path)
            (tmp / "in").mkdir()
            (tmp / "in/08A0.IFF").write_bytes(original)
            receipt = repair.repair_resources(tmp / "in", tmp / "out", manifest, path.parent)
            data = (tmp / "out/08A0.IFF").read_bytes()
            self.assertEqual(data[:1024] + data[1088:], original[:1024] + original[1088:])
            self.assertEqual(data[1024:1088], replacement)
            self.assertTrue(receipt["resources"]["08A0.IFF"]["outside_scope_identical"])
            again = repair.repair_resources(tmp / "out", tmp / "again", manifest, path.parent)
            self.assertEqual((tmp / "again/08A0.IFF").read_bytes(), data)
            self.assertTrue(again["resources"]["08A0.IFF"]["spans"][0]["already_applied"])
            tampered = bytearray(original)
            tampered[1030] ^= 0xFF
            (tmp / "bad").mkdir()
            (tmp / "bad/08A0.IFF").write_bytes(bytes(tampered))
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


if __name__ == "__main__":
    unittest.main()
