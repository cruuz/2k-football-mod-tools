"""Scorebar Studio document model: lossless round trips, presets, picture fitting, determinism."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
HAVE_PIL = importlib.util.find_spec("PIL") is not None
from mod_editor.core import nfl2k5_scorebug_author as a  # noqa: E402
from mod_editor.core import nfl2k5_scorebug_template as t  # noqa: E402

EXTRACTION = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)"
PACK = EXTRACTION / "vc_53450030/0"
LAYER_FILES = [f"{scale}x/{name}.png" for scale in (1, 2) for name in t.LAYERS]


def _bytes(folder: Path) -> dict:
    return {name: (folder / name).read_bytes() for name in LAYER_FILES}


@unittest.skipUnless(HAVE_PIL, "Pillow is required for scorebar authoring")
class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name).resolve()

    def test_reference_round_trip_is_byte_identical_and_compiles_the_same_atlas(self):
        document = a.Document.open_folder(t.DEFAULT_FOLDER)
        self.assertTrue(all(document.layers[name].image is not None for name in t.LAYERS))
        receipt = document.save_folder(self.work / "reference")
        self.assertEqual(_bytes(self.work / "reference"), _bytes(t.DEFAULT_FOLDER))
        self.assertEqual(t.compile_folder(self.work / "reference").image.tobytes(), t.compile_folder().image.tobytes())
        self.assertEqual(receipt["template"]["colours"], 16)
        self.assertEqual([row["sha256"] for row in receipt["template"]["layers"]],
                         [row["sha256"] for row in t.compile_folder().receipt["layers"]])
        self.assertTrue((self.work / "reference" / a.DOCUMENT_FILE).is_file())
        reopened = a.Document.open_folder(self.work / "reference")
        self.assertEqual(reopened, document)
        # A second save from the reopened document is still the reference, byte for byte.
        reopened.save_folder(self.work / "again")
        self.assertEqual(_bytes(self.work / "again"), _bytes(t.DEFAULT_FOLDER))

    def test_every_preset_exports_compiles_fits_and_reopens_equal(self):
        ids = [item.id for item in a.presets()]
        self.assertEqual(ids, ["reference_v10", "fable_espn", "plain_dark", "retail_like"])
        for item in a.presets():
            with self.subTest(preset=item.id):
                document = a.Document.from_preset(item)
                folder = self.work / item.id
                receipt = document.save_folder(folder)
                compiled = t.compile_folder(folder)
                self.assertEqual(compiled.image.tobytes(), document.atlas().tobytes())
                self.assertLessEqual(compiled.receipt["colours"], document.colour_limit)
                self.assertTrue(receipt["slot"]["fits"], receipt["slot"])
                self.assertEqual(receipt["warnings"], [])
                self.assertEqual(a.Document.open_folder(folder), document)
                layout = json.loads((folder / "layout.json").read_text())
                self.assertEqual(layout["schema"], t.SCHEMA)
                self.assertEqual(layout["layers"], t.compile_folder().receipt and json.loads((t.DEFAULT_FOLDER / "layout.json").read_text())["layers"])

    def test_retail_like_says_it_is_an_approximation_and_the_registry_needs_no_code_for_a_folder(self):
        retail = a.preset("retail_like")
        self.assertIn("approximation", retail.summary.lower())
        self.assertIn("no retail pixels", retail.summary.lower())
        a.Document.from_preset("plain_dark").save_folder(self.work / "mine")
        # A plain template folder, as another tool would leave it: no Studio document.
        (self.work / "mine" / a.DOCUMENT_FILE).unlink()
        registry = self.work / "presets.json"
        registry.write_text(json.dumps({"schema": a.PRESETS_SCHEMA, "presets": [
            {"id": "espn_exact", "title": "ESPN exact", "kind": "folder", "folder": str(self.work / "mine"),
             "summary": "Added by a JSON row only."}]}), encoding="utf-8")
        rows = a.presets(registry)
        self.assertEqual([row.id for row in rows], ["espn_exact"])
        document = a.Document.from_preset("espn_exact", registry)
        self.assertEqual(document.title, "ESPN exact")
        self.assertTrue(all(document.layers[name].image is not None for name in t.LAYERS))
        registry.write_text(json.dumps({"schema": a.PRESETS_SCHEMA, "presets": [{"id": "x", "title": "x", "kind": "magic"}]}))
        with self.assertRaisesRegex(a.AuthorError, "unknown kind"):
            a.presets(registry)

    def _picture(self, name: str, size: tuple[int, int]) -> Path:
        from PIL import Image
        image = Image.new("RGBA", size, (255, 0, 0, 255))
        for x in range(size[0] // 2, size[0]):
            for y in range(size[1]):
                image.putpixel((x, y), (0, 0, 255, 255))
        path = self.work / name
        (image.convert("RGB") if path.suffix == ".jpg" else image).save(path)
        return path

    def test_imported_pictures_are_fitted_in_on_screen_proportions_then_reduced_to_the_tile(self):
        tall = a.load_picture(self._picture("tall.png", (100, 300)))
        wide = a.load_picture(self._picture("wide.jpg", (300, 100)))
        # Contain pads: a tall picture leaves whole transparent columns in the 68x24 mark cell,
        # a wide one pads a single row that the tile reduction blends to part transparency.
        for source, fit, lowest_alpha in ((tall, "contain", 0), (tall, "cover", 255),
                                          (tall, "stretch", 255), (wide, "contain", 200), (wide, "cover", 255)):
            with self.subTest(fit=fit, size=a.decode_image(source.data).size):
                layer = a.Layer(image=a.ImageRef((source,), fit, None, False, "p"))
                for scale in (1, 2):
                    image = a.render_layer(layer, "left_mark", scale)
                    self.assertEqual(image.size, a.tile_size("left_mark", scale))
                    alphas = [p[3] for p in image.getdata()]
                    if lowest_alpha == 255:
                        self.assertEqual(min(alphas), 255)
                    elif lowest_alpha == 0:
                        self.assertEqual(min(alphas), 0)
                    else:
                        self.assertLess(min(alphas), lowest_alpha)
                    opaque = [p for p in image.getdata() if p[3] == 255]
                    self.assertTrue(any(p[0] > 200 and p[2] < 60 for p in opaque), "red half missing")
                    self.assertTrue(any(p[2] > 200 and p[0] < 60 for p in opaque), "blue half missing")
        cropped = a.Layer(image=a.ImageRef((tall,), "stretch", (0, 0, 50, 300), False, "crop"))
        image = a.render_layer(cropped, "down", 1)
        self.assertTrue(all(p[0] > 200 and p[2] < 60 for p in image.getdata()), "crop should keep only the red half")
        with self.assertRaisesRegex(a.AuthorError, "outside the picture"):
            a.render_layer(a.Layer(image=a.ImageRef((tall,), "cover", (0, 0, 500, 500), False, "bad")), "down", 1)
        document = a.Document.from_preset("plain_dark")
        document.layers["left_mark"] = a.Layer(image=a.ImageRef((wide,), "contain", None, True, "wide.jpg"), radius=3)
        receipt = document.save_folder(self.work / "picture")
        self.assertTrue((self.work / "picture" / "images" / "left_mark_any.jpg").is_file())
        self.assertEqual(a.Document.open_folder(self.work / "picture"), document)
        self.assertTrue(receipt["slot"]["fits"])

    def test_rendering_and_saving_are_deterministic(self):
        document = a.Document.from_preset("fable_espn")
        first = {name: a.encode_png(a.render_layer(document.layers[name], name, 2)) for name in t.LAYERS}
        second = {name: a.encode_png(a.render_layer(document.layers[name], name, 2)) for name in t.LAYERS}
        self.assertEqual(first, second)
        document.save_folder(self.work / "one")
        document.save_folder(self.work / "two")
        self.assertEqual(_bytes(self.work / "one"), _bytes(self.work / "two"))
        self.assertEqual((self.work / "one" / a.DOCUMENT_FILE).read_bytes(), (self.work / "two" / a.DOCUMENT_FILE).read_bytes())

    def test_colour_limit_reduces_blends_jointly_without_touching_exact_pictures(self):
        document = a.Document.open_folder(t.DEFAULT_FOLDER)
        for name in ("frame", "away_block", "home_block", "down", "clock_quarter"):
            document.layers[name] = a.Layer("#FFFFFFFF", a.Gradient(("#FF0000FF", "#00FF00FF", "#0000FFFF"), 37), 2)
        document.colour_limit = 256
        natural = document.save_folder(self.work / "wide")["template"]["colours"]
        self.assertGreater(natural, 20)
        self.assertLessEqual(natural, 256)
        document.colour_limit = 20
        receipt = document.save_folder(self.work / "limited")
        self.assertLessEqual(receipt["template"]["colours"], 20)
        self.assertEqual((self.work / "limited" / "1x" / "left_mark.png").read_bytes(), (t.DEFAULT_FOLDER / "1x" / "left_mark.png").read_bytes())
        self.assertEqual((self.work / "limited" / "2x" / "away_score.png").read_bytes(), (t.DEFAULT_FOLDER / "2x" / "away_score.png").read_bytes())
        self.assertEqual(a.Document.open_folder(self.work / "limited").colour_limit, 20)

    def test_warnings_name_dark_clock_strips_and_light_text_cells(self):
        document = a.Document.from_preset("plain_dark")
        document.layers["clock_quarter"] = a.Layer("#101010FF")
        document.layers["down"] = a.Layer("#FFFFFFFF")
        warnings = document.analysis()["warnings"]
        self.assertTrue(any("clock strip is dark" in w for w in warnings), warnings)
        self.assertTrue(any("banner is very light" in w for w in warnings), warnings)

    def test_bad_documents_and_folders_refuse_with_plain_messages(self):
        with self.assertRaisesRegex(a.AuthorError, "not a Scorebar Studio document"):
            a.Document.from_json({"schema": "other"})
        with self.assertRaisesRegex(a.AuthorError, "#RRGGBB"):
            a.Layer.from_json({"fill": "red"})
        with self.assertRaisesRegex(a.AuthorError, "two or three colours"):
            a.Layer.from_json({"gradient": {"stops": ["#000000"]}})
        with self.assertRaisesRegex(a.AuthorError, "Corner rounding"):
            a.Layer.from_json({"radius": 99})
        empty = self.work / "empty"
        empty.mkdir()
        with self.assertRaisesRegex(a.AuthorError, "not a supported scorebar template"):
            a.Document.open_folder(empty)
        with self.assertRaisesRegex(a.AuthorError, "not a folder"):
            a.Document.open_folder(self.work / "missing")
        broken = self.work / "broken"
        a.Document.from_preset("plain_dark").save_folder(broken)
        (broken / "1x" / "down.png").write_bytes(b"not a png")
        with self.assertRaisesRegex(a.AuthorError, "down.png is not a readable PNG"):
            a.Document.open_folder(broken)
        with self.assertRaisesRegex(a.AuthorError, "shipped reference kit"):
            a.Document.from_preset("plain_dark").save_folder(t.DEFAULT_FOLDER)
        with self.assertRaisesRegex(a.AuthorError, "not a readable picture"):
            a.load_picture(broken / "1x" / "down.png")
        saved = self.work / "moved"
        document = a.Document.from_preset("plain_dark")
        document.layers["left_mark"] = a.Layer(image=a.ImageRef((a.load_picture(self._picture("logo.png", (40, 20))),), "contain"))
        document.save_folder(saved)
        (saved / "images" / "left_mark_any.png").write_bytes(b"\x89PNG\r\n\x1a\nchanged")
        with self.assertRaisesRegex(a.AuthorError, "changed since this scorebar was saved"):
            a.Document.open_folder(saved)

    def _bar_extent(self, image, y: int = 395) -> tuple[int, int]:
        """The dark bar body's span on one row: the field is green and yard lines are white."""
        columns = [x for x in range(image.size[0]) if max(image.getpixel((x, y))[:3]) < 90]
        return min(columns), max(columns) + 1

    def test_preview_sizes_states_widescreen_contraction_and_team_colours(self):
        document = a.Document.from_preset("fable_espn")
        normal = a.preview(document)
        self.assertEqual(normal.size, a.HUD_SIZE)
        left, right = self._bar_extent(normal)
        self.assertAlmostEqual(left, t.RAILS[0], delta=3)
        self.assertAlmostEqual(right, t.RAILS[2], delta=3)
        wide = a.preview(document, widescreen=True)
        self.assertEqual(wide.size, a.WIDE_SIZE)
        left, right = self._bar_extent(wide)
        expected = [(320 + (x - 320) * 27 / 32) * a.WIDE_SIZE[0] / 640 for x in (t.RAILS[0], t.RAILS[2])]
        self.assertAlmostEqual(left, expected[0], delta=4)
        self.assertAlmostEqual(right, expected[1], delta=4)
        timeouts = a.preview(document, state_id="timeouts")
        self.assertNotEqual(timeouts.tobytes(), normal.tobytes())
        self.assertEqual(a.preview(document, state_id="first_and_ten").tobytes(), normal.tobytes())
        teams = a.preview(document, team_preview=("KC", "BUF"))
        self.assertNotEqual(teams.tobytes(), normal.tobytes())
        self.assertEqual(document.layers["away_block"], a.Document.from_preset("fable_espn").layers["away_block"],
                         "team colours must not change the document")
        with self.assertRaisesRegex(a.AuthorError, "32 teams"):
            a.preview(document, team_preview=("KC", "ZZZ"))
        self.assertEqual(len(a.teams()), 32)
        self.assertEqual([s.id for s in a.STATES], ["first_and_ten", "fourth_and_one", "timeouts", "two_minute"])

    def test_command_line_lists_exports_previews_and_validates(self):
        env = {**os.environ, "PYTHONPATH": str(ROOT)}
        listing = subprocess.run([sys.executable, "-m", "mod_editor.core.nfl2k5_scorebug_author", "presets"],
                                 cwd=ROOT, capture_output=True, text=True, timeout=60, env=env)
        self.assertEqual(listing.returncode, 0, listing.stderr)
        self.assertEqual([line.split("\t")[0] for line in listing.stdout.strip().splitlines()],
                         ["reference_v10", "fable_espn", "plain_dark", "retail_like"])
        folder = self.work / "cli"
        export = subprocess.run([sys.executable, "-m", "mod_editor.core.nfl2k5_scorebug_author", "export",
                                 "--preset", "plain_dark", "--folder", str(folder)],
                                cwd=ROOT, capture_output=True, text=True, timeout=120, env=env)
        self.assertEqual(export.returncode, 0, export.stderr)
        self.assertTrue(json.loads(export.stdout)["slot"]["fits"])
        check = subprocess.run([sys.executable, "-m", "mod_editor.core.nfl2k5_scorebug_author", "validate",
                                "--folder", str(folder)], cwd=ROOT, capture_output=True, text=True, timeout=60, env=env)
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertEqual(json.loads(check.stdout)["schema"], t.SCHEMA)
        shot = self.work / "shot.png"
        render = subprocess.run([sys.executable, "-m", "mod_editor.core.nfl2k5_scorebug_author", "preview",
                                 "--open", str(folder), "--out", str(shot), "--widescreen", "--state", "two_minute",
                                 "--teams", "NO", "MIA"], cwd=ROOT, capture_output=True, text=True, timeout=120, env=env)
        self.assertEqual(render.returncode, 0, render.stderr)
        self.assertTrue(shot.is_file())
        bad = subprocess.run([sys.executable, "-m", "mod_editor.core.nfl2k5_scorebug_author", "validate",
                              "--folder", str(self.work)], cwd=ROOT, capture_output=True, text=True, timeout=60, env=env)
        self.assertEqual(bad.returncode, 2)
        self.assertIn("Scorebar Studio:", bad.stderr)

    def test_product_path_imports_no_numpy_qt_or_emulator(self):
        source = (ROOT / "mod_editor/core/nfl2k5_scorebug_author.py").read_text(encoding="utf-8")
        for forbidden in ("import numpy", "import unicorn", "from unicorn", "PyQt5", "capstone"):
            self.assertNotIn(forbidden, source)
        for text in list(a.LAYER_TITLES.values()) + list(a.LAYER_NOTES.values()) + [s.title for s in a.STATES]:
            self.assertNotIn("—", text)


@unittest.skipUnless(HAVE_PIL and PACK.is_file(), "Pillow and the pinned USA pack 0 are required")
class SlotEstimateAgainstRetailTests(unittest.TestCase):
    def setUp(self):
        from mod_editor.core import nfl2k5_scorebug_ingame as r
        record = r.RESOURCES["score_buga"]
        with PACK.open("rb") as stream:
            stream.seek(record["pack_offset"])
            self.span = stream.read(record["span_size"])

    def test_estimate_agrees_with_the_exact_fixed_span_encoder(self):
        from PIL import Image
        import random
        for preset_id in ("reference_v10", "fable_espn", "plain_dark", "retail_like"):
            atlas = a.Document.from_preset(preset_id).atlas()
            estimate = a.slot_estimate(atlas)
            _span, receipt = t.encode_span(self.span, t.CompiledTemplate(atlas, {}))
            self.assertTrue(estimate["fits"])
            self.assertLessEqual(receipt["filled_bytes"], a.SLOT_BODY_BYTES)
        rng = random.Random(5)
        noisy = Image.new("RGBA", (64, 64))
        noisy.putdata([(v, v, v, 255) for v in (rng.randrange(32) * 8 for _ in range(4096))])
        self.assertFalse(a.slot_estimate(noisy)["fits"])
        with self.assertRaisesRegex(t.TemplateError, "too detailed"):
            t.encode_span(self.span, t.CompiledTemplate(noisy, {}))


if __name__ == "__main__":
    unittest.main()
