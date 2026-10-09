"""Beta 77 u2a: 2026 kit corrections for ARI ATL BAL BUF CAR CHI CIN CLE: recipes, scope-limited authoring helpers,
the helmet shell recolour, the merged project and the repair."""
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
repair = _load("b77_u2a_repair_test", "tools/b77/u2a_repair.py")
DATA = ROOT / "data/nfl2k5_teams_2026"


def recipe(team: str) -> dict:
    return json.loads((DATA / f"{team}.json").read_text(encoding="utf-8"))


class Recipes(unittest.TestCase):
    def test_bills_wordmark_and_white_road_pants(self):
        d = recipe("BUF")
        for side in ("home", "away"):
            mark = d["kits"][side]["torso"]["chest_mark"]
            self.assertEqual(mark["width"], 23)
            self.assertEqual(mark["center"], [161, 102])
        self.assertEqual(d["kits"]["away"]["pants"]["base_colour"], "white")
        self.assertEqual([c for c, _ in d["kits"]["away"]["pants"]["stripe"]], ["jersey_royal", "red", "jersey_royal"])

    def test_panthers_home_black_pants_black_helmet_white_helmet_numbers(self):
        d = recipe("CAR")["kits"]
        self.assertEqual(d["home"]["pants"]["base_colour"], "black")
        self.assertEqual(d["home"]["helmet"]["shell"], "black")
        self.assertEqual(d["home"]["helmet_digits"]["fill"], "white")
        self.assertEqual(d["away"]["helmet"]["shell"], "silver")        # the road helmet stays silver
        for side in ("home", "away"):
            colours = [x["colour"] for x in d[side]["pants"]["decorations"]]
            self.assertIn("blue", colours)
            for x in d[side]["pants"]["decorations"]:                    # tapering stripes: wider at the waist
                (xa, _), (xb, _), (xc, y3), (xd, _) = [tuple(p) for p in x["polygon"]]
                self.assertGreater(xb - xa, xc - xd)

    def test_bengals_home_pants_socks_and_wordmark(self):
        d = recipe("CIN")["kits"]
        self.assertEqual(d["home"]["pants"]["base_colour"], "black")
        self.assertTrue(all(x["colour"] == "orange" for x in d["home"]["pants"]["decorations"]))
        self.assertEqual(d["home"]["socks"]["colour"], "orange")
        self.assertEqual(d["away"]["pants"]["base_colour"], "white")      # no white-jersey game photographed yet
        for side in ("home", "away"):
            mark = d[side]["torso"]["decorations"][0]
            self.assertEqual((mark["mark"], mark["width"], mark["offset"]), ("wm_bengals", 58, [0, 5.5]))

    def test_browns_home_sleeve_uses_the_u2a_mark_without_shift(self):
        d = recipe("CLE")
        self.assertIn("cle_h_sleeve_u2a", d["marks"])
        sleeve = d["kits"]["home"]["sleeve"]
        self.assertEqual(sleeve["decorations"][0]["mark"], "cle_h_sleeve_u2a")
        self.assertEqual(sleeve["art_shift_rows"], 0)
        self.assertEqual(d["kits"]["away"]["sleeve"]["decorations"][0]["mark"], "cle_a_sleeve")

    def test_ravens_cardinals_falcons_corrections(self):
        bal = recipe("BAL")["kits"]
        self.assertEqual(bal["home"]["socks"]["colour"], "jersey_purple")
        self.assertEqual(bal["away"]["pants"]["base_colour"], "black")
        ari = recipe("ARI")["kits"]["away"]["pants"]["stripe"]
        self.assertEqual(sum(n for _, n in ari), 30)

    def test_all_eight_recipes_parse_and_keep_selectors(self):
        sel = {"ARI": "00", "ATL": "01", "BAL": "02", "BUF": "03", "CAR": "04", "CHI": "05", "CIN": "06", "CLE": "30"}
        for team, code in sel.items():
            d = recipe(team)
            self.assertEqual(d["asset_code"], code)
            self.assertEqual(d["kits"]["home"]["selector"], f"{code}H0")
            self.assertEqual(d["kits"]["away"]["selector"], f"{code}A0")


class Scope(unittest.TestCase):
    def test_changed_scope_follows_the_master_difference_and_grows(self):
        m = kits.MASTER
        old = np.zeros((8 * m, 8 * m, 4), np.float32)
        new = old.copy()
        new[2 * m:3 * m, 4 * m:5 * m, 0] = 0.5             # one native texel differs
        scope = kits._changed_scope(new, old, grow=0)
        self.assertEqual(int(scope.sum()), 1)
        self.assertTrue(scope[2, 4])
        self.assertEqual(int(kits._changed_scope(new, old, grow=1).sum()), 5)
        self.assertEqual(int(kits._changed_scope(old, old).sum()), 0)

    def test_merge_scope_keeps_every_texel_outside_the_scope(self):
        m = kits.MASTER
        base = np.random.default_rng(1).integers(0, 256, (4, 4, 4), dtype=np.uint8)
        new = np.full((4 * m, 4 * m, 4), 1.0, np.float32)
        scope = np.zeros((4, 4), bool)
        scope[1, 1] = True
        out = kits.merge_scope(new, base, scope)
        self.assertTrue((out[~scope] == base[~scope]).all())
        self.assertTrue((out[1, 1] == 255).all())

    def test_recipes_differ_only_for_the_part_that_changed(self):
        a = {"kits": {"home": {"torso": {"x": 1}, "pants": {"y": 1}, "socks": {"z": 1}, "sleeve": {"s": 1}}}}
        b = json.loads(json.dumps(a))
        b["kits"]["home"]["pants"]["y"] = 2
        self.assertTrue(kits.recipes_differ(b, a, "home", "pants"))
        for part in ("torso", "socks", "sleeve"):
            self.assertFalse(kits.recipes_differ(b, a, "home", part))


class HelmetShell(unittest.TestCase):
    def helmet(self):
        im = np.zeros((256, 256, 4), np.uint8)
        im[..., 3] = 255
        im[:, :] = (178, 180, 187, 255)                            # the silver shell
        im[100:110, 20:60] = (0, 133, 207, 255)                     # a Panther-blue stripe
        im[104:106, 30:32] = (200, 200, 205, 255)                   # a 4 px grey speck inside the blue (a tooth): too small to be shell
        im[:, 190:] = (250, 250, 250, 255)                          # the label strip on the right of the atlas
        return im

    def test_shell_darkens_while_stripe_speck_and_labels_keep_their_texels(self):
        im = self.helmet()
        out, keep = kits.recolour_helmet_shell(im, np.array([178, 180, 187]) / 255.0, np.array([17, 17, 24]) / 255.0)
        self.assertTrue((out[200, 100, :3] < 40).all())
        self.assertTrue((out[105, 40] == im[105, 40]).all())       # stripe unchanged
        self.assertTrue((out[104, 30] == im[104, 30]).all())       # speck unchanged
        self.assertTrue((out[:, 190:] == im[:, 190:]).all())        # label strip unchanged
        self.assertFalse(keep[:, 190:].any())
        self.assertTrue((out[..., 3] == im[..., 3]).all())

    def test_no_light_fringe_next_to_the_stripe(self):
        im = self.helmet()
        out, keep = kits.recolour_helmet_shell(im, np.array([178, 180, 187]) / 255.0, np.array([17, 17, 24]) / 255.0)
        ring = out[99, 40, :3].astype(int)
        self.assertLess(int(ring.max()), 100)


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

    def test_manifest_owns_the_eight_teams_kits_and_the_two_card_packs(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "m.json"
            good = ["00H0.IFF", "00A0.IFF", "01H0.IFF", "02A0.IFF", "03H0.IFF", "04A0.IFF", "05H0.IFF", "06A0.IFF",
                    "30H0.IFF"]
            for name in good + ["outer:3102", "outer:3105"]:
                path.write_text(json.dumps({"schema": repair.SCHEMA, "resources": {name: []}}))
                self.assertIn(name, repair.load_manifest(path)["resources"])
            for name in ("16H0.IFF", "07H0.IFF", "31A0.IFF", "outer:3741", "00B0.IFF", "00H1.IFF"):
                path.write_text(json.dumps({"schema": repair.SCHEMA, "resources": {name: []}}))
                with self.assertRaises(ValueError):
                    repair.load_manifest(path)
            path.write_text(json.dumps({"schema": "b77/u1/texture-repair/v1", "resources": {"00H0.IFF": []}}))
            with self.assertRaises(ValueError):
                repair.load_manifest(path)

    def test_loose_repair_is_scoped_idempotent_and_refuses_other_input(self):
        original = np.random.default_rng(5).integers(0, 256, 4096, dtype=np.uint8).tobytes()
        replacement = bytes(64)
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            path = self.manifest(tmp, original, 1024, replacement, "04H0.IFF")
            manifest = repair.load_manifest(path)
            (tmp / "in").mkdir()
            (tmp / "in/04H0.IFF").write_bytes(original)
            receipt = repair.repair_resources(tmp / "in", tmp / "out", manifest, path.parent)
            data = (tmp / "out/04H0.IFF").read_bytes()
            self.assertEqual(data[:1024] + data[1088:], original[:1024] + original[1088:])
            self.assertEqual(data[1024:1088], replacement)
            self.assertTrue(receipt["resources"]["04H0.IFF"]["outside_scope_identical"])
            again = repair.repair_resources(tmp / "out", tmp / "again", manifest, path.parent)
            self.assertEqual((tmp / "again/04H0.IFF").read_bytes(), data)
            self.assertTrue(again["resources"]["04H0.IFF"]["spans"][0]["already_applied"])
            tampered = bytearray(original)
            tampered[1030] ^= 0xFF
            (tmp / "bad").mkdir()
            (tmp / "bad/04H0.IFF").write_bytes(bytes(tampered))
            with self.assertRaisesRegex(ValueError, "unexpected input span"):
                repair.repair_resources(tmp / "bad", tmp / "bad_out", manifest, path.parent)

    def test_loose_mode_does_not_take_card_resources(self):
        original = bytes(range(256)) * 4
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            path = self.manifest(tmp, original, 16, b"\1" * 16, "outer:3105")
            (tmp / "in").mkdir()
            with self.assertRaisesRegex(ValueError, "kit packages only"):
                repair.repair_resources(tmp / "in", tmp / "out", repair.load_manifest(path), path.parent)


class Project(unittest.TestCase):
    def test_merge_adds_cards_only_for_kits_with_changed_art(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            final = tmp / "final"
            (final / "AAA").mkdir(parents=True)
            (final / "AAA/project.json").write_text(json.dumps({"edits": [{"kind": "pants", "asset_code": "03",
                                                                          "side": "A", "variant": 0}]}))
            (final / "AAA/author_receipt.json").write_text(json.dumps({"items": [{"selector": "03A0", "name": "pants"}]}))
            for fam in ("unif_256", "helm_256", "helm_128"):
                (final / f"AAA/cards/03A0/team-select_{fam}.png").parent.mkdir(parents=True, exist_ok=True)
                (final / f"AAA/cards/03A0/team-select_{fam}.png").write_bytes(b"x")
            export = tmp / "export.json"
            export.write_text(json.dumps({"sets": [{"selector": "03H0"}, {"selector": "03A0"}]}))
            out = tmp / "p.json"
            info = kits.merge_projects(final, ["AAA"], out, export)
            self.assertEqual(info["kits_changed"], ["03A0"])
            doc = json.loads(out.read_text())
            cards = [e for e in doc["edits"] if e["kind"] == "team_select"]
            self.assertEqual([(e["family"], e["resolution"]) for e in cards], [("unif", 256)])   # no helmet edit: no helm cards
            self.assertTrue(all(e["side"] == "away" and e["asset_code"] == "03" for e in cards))
            (final / "AAA/author_receipt.json").write_text(json.dumps({"items": [
                {"selector": "03A0", "name": "helmet_helmet02"}]}))
            doc = json.loads((kits.merge_projects(final, ["AAA"], out, export) and out).read_text())
            self.assertEqual(len([e for e in doc["edits"] if e["kind"] == "team_select"]), 3)
            (final / "AAA/author_receipt.json").write_text(json.dumps({"items": [{"selector": "03A0", "name": "pants"}]}))
            (final / "AAA/author_receipt.json").write_text(json.dumps({"items": [{"selector": "99H0", "name": "x"}]}))
            with self.assertRaises(ValueError):
                kits.merge_projects(final, ["AAA"], out, export)


if __name__ == "__main__":
    unittest.main()
