"""Focused tests for GUI-independent typed recipe generation."""

from __future__ import annotations

import hashlib
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from mod_editor.core.errors import OutputRefusedError
from mod_editor.__main__ import main as editor_main
from mod_editor.core import recipes
from mod_editor.core.recipes import (
    NFL_SCOREBUG_SOURCE_PIN,
    RecipeError,
    ScorebugRecipeEdit,
    canonical_recipe_json,
    create_apf_helmet_recipe,
    create_apf_jersey_recipe,
    create_apf_pants_recipe,
    create_apf_shoulder_recipe,
    create_nfl_scorebug_recipe,
)


def make_png(
    path: Path,
    dimensions: tuple[int, int],
    *,
    mode: str = "RGBA",
) -> Path:
    color = (11, 37, 83, 211) if mode == "RGBA" else (11, 37, 83)
    Image.new(mode, dimensions, color).save(path, format="PNG")
    return path


class RecipeGenerationTests(unittest.TestCase):
    def test_headless_cli_creates_all_recipe_types(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            jersey = make_png(root / "jersey.png", (1024, 1024))
            pants = root / "pants.png"
            Image.new("RGBA", (512, 512), (7, 17, 27, 255)).save(pants)
            helmet = root / "helmet.png"
            Image.new("RGBA", (256, 1024), (7, 17, 0, 255)).save(helmet)
            shoulder = make_png(root / "shoulder.png", (1024, 1024))
            score = make_png(root / "score.png", (64, 64))
            apf_output = root / "apf.json"
            pants_output = root / "pants.json"
            helmet_output = root / "helmet.json"
            shoulder_output = root / "shoulder.json"
            nfl_output = root / "nfl.json"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(
                    editor_main(
                        [
                            "--create-apf-shoulder-recipe",
                            str(shoulder_output),
                            "--asset-index",
                            "8",
                            "--shoulder-png",
                            str(shoulder),
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    editor_main(
                        [
                            "--create-apf-helmet-recipe",
                            str(helmet_output),
                            "--asset-index",
                            "16",
                            "--helmet-png",
                            str(helmet),
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    editor_main(
                        [
                            "--create-apf-pants-recipe",
                            str(pants_output),
                            "--asset-index",
                            "13",
                            "--pants-png",
                            str(pants),
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    editor_main(
                        [
                            "--create-apf-jersey-recipe",
                            str(apf_output),
                            "--asset-index",
                            "6",
                            "--jersey-png",
                            str(jersey),
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    editor_main(
                        [
                            "--create-nfl-scorebug-recipe",
                            str(nfl_output),
                            "--purpose",
                            "CLI scorebug test",
                            "--score-buga-png",
                            str(score),
                        ]
                    ),
                    0,
                )
            self.assertIn("MOD_EDITOR_APF_JERSEY_RECIPE_CREATED", stdout.getvalue())
            self.assertIn("MOD_EDITOR_APF_PANTS_RECIPE_CREATED", stdout.getvalue())
            self.assertIn("MOD_EDITOR_APF_HELMET_RECIPE_CREATED", stdout.getvalue())
            self.assertIn("MOD_EDITOR_APF_SHOULDER_RECIPE_CREATED", stdout.getvalue())
            self.assertIn("MOD_EDITOR_NFL_SCOREBUG_RECIPE_CREATED", stdout.getvalue())
            self.assertEqual(json.loads(apf_output.read_bytes())["asset_index"], 6)
            self.assertEqual(json.loads(pants_output.read_bytes())["asset_index"], 13)
            self.assertEqual(json.loads(helmet_output.read_bytes())["asset_index"], 16)
            self.assertEqual(json.loads(shoulder_output.read_bytes())["asset_index"], 8)
            self.assertEqual(
                json.loads(nfl_output.read_bytes())["edits"][0]["target"],
                "score_buga",
            )

    def test_apf_recipe_is_exact_canonical_and_contains_no_raw_target_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            png = make_png(root / "jersey.png", (1024, 1024))
            before = hashlib.sha256(png.read_bytes()).hexdigest()
            output = root / "jersey.recipe.json"

            result = create_apf_jersey_recipe(
                output=output, asset_index=23, png=png
            )

            self.assertEqual(result, output.resolve())
            payload = output.read_bytes()
            value = json.loads(payload)
            self.assertEqual(
                value,
                {
                    "asset_index": 23,
                    "png": "jersey.png",
                    "schema": "apf2k8_jersey_color_recipe/v1",
                },
            )
            self.assertEqual(payload, canonical_recipe_json(value))
            self.assertEqual(hashlib.sha256(png.read_bytes()).hexdigest(), before)
            serialized = payload.decode("utf-8")
            for forbidden in ("offset", "outer_table", "allocation", "game_data"):
                self.assertNotIn(forbidden, serialized)

    def test_apf_rejects_asset_bounds_dimensions_mode_invalid_png_and_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            valid = make_png(root / "valid.png", (1024, 1024))
            for value in (-1, 24, True):
                output = root / f"asset-{value}.json"
                with self.subTest(asset_index=value), self.assertRaises(RecipeError):
                    create_apf_jersey_recipe(
                        output=output, asset_index=value, png=valid
                    )
                self.assertFalse(os.path.lexists(output))

            wrong_size = make_png(root / "wrong-size.png", (512, 1024))
            wrong_mode = make_png(root / "wrong-mode.png", (1024, 1024), mode="RGB")
            invalid = root / "invalid.png"
            invalid.write_bytes(b"not a png")
            linked = root / "linked.png"
            linked.symlink_to(valid)
            for name, supplied in (
                ("size", wrong_size),
                ("mode", wrong_mode),
                ("invalid", invalid),
                ("symlink", linked),
            ):
                output = root / f"reject-{name}.json"
                with self.subTest(reason=name), self.assertRaises(RecipeError):
                    create_apf_jersey_recipe(
                        output=output, asset_index=6, png=supplied
                    )
                self.assertFalse(os.path.lexists(output))

    def test_apf_pants_recipe_is_canonical_opaque_and_has_only_named_selector(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            png = root / "pants.png"
            Image.new("RGBA", (512, 512), (9, 29, 49, 255)).save(png)
            output = root / "pants.recipe.json"

            result = create_apf_pants_recipe(
                output=output, asset_index=23, png=png
            )

            value = json.loads(output.read_bytes())
            self.assertEqual(result, output.resolve())
            self.assertEqual(value, {
                "asset_index": 23,
                "png": "pants.png",
                "schema": "apf2k8_pants_color_recipe/v1",
            })
            self.assertEqual(output.read_bytes(), canonical_recipe_json(value))
            self.assertNotIn("offset", output.read_text(encoding="utf-8"))

    def test_apf_pants_rejects_transparency_dimensions_mode_and_bounds(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            valid = root / "valid.png"
            transparent = root / "transparent.png"
            wrong_dimensions = root / "wrong-dimensions.png"
            wrong_mode = root / "wrong-mode.png"
            Image.new("RGBA", (512, 512), (1, 2, 3, 255)).save(valid)
            Image.new("RGBA", (512, 512), (1, 2, 3, 254)).save(transparent)
            Image.new("RGBA", (1024, 1024), (1, 2, 3, 255)).save(wrong_dimensions)
            Image.new("RGB", (512, 512), (1, 2, 3)).save(wrong_mode)
            cases = (
                ("transparent", 6, transparent),
                ("dimensions", 6, wrong_dimensions),
                ("mode", 6, wrong_mode),
                ("lower-bound", -1, valid),
                ("upper-bound", 24, valid),
                ("bool", True, valid),
            )
            for name, asset_index, png in cases:
                output = root / f"reject-pants-{name}.json"
                with self.subTest(name=name), self.assertRaises(RecipeError):
                    create_apf_pants_recipe(
                        output=output, asset_index=asset_index, png=png
                    )
                self.assertFalse(os.path.lexists(output))

    def test_apf_helmet_recipe_preserves_raw_channel_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            valid = root / "helmet.png"
            Image.new("RGBA", (256, 1024), (13, 231, 0, 255)).save(valid)
            output = root / "helmet.recipe.json"

            result = create_apf_helmet_recipe(output=output, asset_index=16, png=valid)

            value = json.loads(output.read_bytes())
            self.assertEqual(result, output.resolve())
            self.assertEqual(value, {
                "asset_index": 16,
                "png": "helmet.png",
                "schema": "apf2k8_helmet_color_recipe/v1",
            })
            self.assertEqual(output.read_bytes(), canonical_recipe_json(value))
            serialized = output.read_text(encoding="utf-8")
            for forbidden in ("offset", "paint", "diffuse", "normal", "semantics"):
                self.assertNotIn(forbidden, serialized)

    def test_apf_helmet_rejects_nonzero_blue_bad_alpha_dimensions_mode_and_bounds(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            valid = root / "valid.png"
            nonzero_blue = root / "blue.png"
            bad_alpha = root / "alpha.png"
            wrong_dimensions = root / "dimensions.png"
            wrong_mode = root / "mode.png"
            Image.new("RGBA", (256, 1024), (1, 2, 0, 255)).save(valid)
            Image.new("RGBA", (256, 1024), (1, 2, 1, 255)).save(nonzero_blue)
            Image.new("RGBA", (256, 1024), (1, 2, 0, 254)).save(bad_alpha)
            Image.new("RGBA", (1024, 256), (1, 2, 0, 255)).save(wrong_dimensions)
            Image.new("RGB", (256, 1024), (1, 2, 0)).save(wrong_mode)
            cases = (
                ("blue", 6, nonzero_blue),
                ("alpha", 6, bad_alpha),
                ("dimensions", 6, wrong_dimensions),
                ("mode", 6, wrong_mode),
                ("lower", -1, valid),
                ("upper", 24, valid),
                ("bool", True, valid),
            )
            for name, asset_index, png in cases:
                output = root / f"reject-helmet-{name}.json"
                with self.subTest(name=name), self.assertRaises(RecipeError):
                    create_apf_helmet_recipe(
                        output=output, asset_index=asset_index, png=png
                    )
                self.assertFalse(os.path.lexists(output))

    def test_apf_shoulder_recipe_is_canonical_and_rejects_bad_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            valid = make_png(root / "shoulder.png", (1024, 1024))
            output = root / "shoulder.recipe.json"
            result = create_apf_shoulder_recipe(
                output=output, asset_index=8, png=valid
            )
            value = json.loads(output.read_bytes())
            self.assertEqual(result, output.resolve())
            self.assertEqual(
                value,
                {
                    "asset_index": 8,
                    "png": "shoulder.png",
                    "schema": "apf2k8_shoulder_color_recipe/v1",
                },
            )
            self.assertEqual(output.read_bytes(), canonical_recipe_json(value))

            wrong = make_png(root / "wrong.png", (512, 512))
            linked = root / "linked.png"
            linked.symlink_to(valid)
            for name, index, png in (
                ("dimensions", 8, wrong),
                ("symlink", 8, linked),
                ("lower", -1, valid),
                ("upper", 24, valid),
                ("bool", True, valid),
            ):
                rejected = root / f"shoulder-reject-{name}.json"
                with self.subTest(name=name), self.assertRaises(RecipeError):
                    create_apf_shoulder_recipe(
                        output=rejected, asset_index=index, png=png
                    )
                self.assertFalse(os.path.lexists(rejected))

    def test_nfl_recipe_pins_pngs_sources_dimensions_and_canonical_target_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            score = make_png(root / "score.png", (64, 64))
            shield = make_png(root / "shield.png", (128, 64))
            font = make_png(root / "font.png", (128, 128))
            output = root / "scorebug.recipe.json"

            create_nfl_scorebug_recipe(
                output=output,
                purpose="Replace all three proved scorebug textures.",
                edits=[
                    ScorebugRecipeEdit("digital_font", font),
                    ScorebugRecipeEdit("score_buga", score),
                    ScorebugRecipeEdit("shield_espn", shield),
                ],
            )

            payload = output.read_bytes()
            value = json.loads(payload)
            self.assertEqual(payload, canonical_recipe_json(value))
            self.assertEqual(value["schema"], "nfl2k5_scorebug_mod_project/v1")
            self.assertEqual(value["source"], dict(NFL_SCOREBUG_SOURCE_PIN))
            self.assertEqual(
                [row["target"] for row in value["edits"]],
                ["score_buga", "shield_espn", "digital_font"],
            )
            paths = {
                "score_buga": score,
                "shield_espn": shield,
                "digital_font": font,
            }
            for record in value["edits"]:
                source = paths[record["target"]]
                data = source.read_bytes()
                self.assertEqual(record["png"], source.name)
                self.assertEqual(record["png_size"], len(data))
                self.assertEqual(
                    record["png_sha256"], hashlib.sha256(data).hexdigest()
                )
                self.assertEqual(
                    set(record), {"target", "png", "png_size", "png_sha256"}
                )
            self.assertEqual(
                value["source"],
                {
                    "canonical_index_sha256": "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d",
                    "canonical_index_size": 193710080,
                    "default_xbe_sha256": "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9",
                    "default_xbe_size": 11948032,
                    "scorebug_audit_sha256": "57bcbb1c0ff8e6c2376565365aba523e4c2fe8cdb66d3a7058daa84993c2ccd1",
                    "scorebug_audit_size": 46512,
                    "xiso_sha256": "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9",
                    "xiso_size": 6300499968,
                },
            )
            serialized = payload.decode("utf-8")
            for forbidden in ("offset", "outer_index", "span", "replacement_bytes"):
                self.assertNotIn(forbidden, serialized)

    def test_nfl_accepts_one_edit_and_rejects_count_duplicates_and_unknown_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            png = make_png(root / "score.png", (64, 64))
            output = root / "one.json"
            create_nfl_scorebug_recipe(
                output=output,
                purpose="One target",
                edits=[ScorebugRecipeEdit("score_buga", png)],
            )
            self.assertEqual(len(json.loads(output.read_bytes())["edits"]), 1)

            invalid_cases = (
                ("empty", []),
                (
                    "duplicate",
                    [
                        ScorebugRecipeEdit("score_buga", png),
                        ScorebugRecipeEdit("score_buga", png),
                    ],
                ),
                ("unknown", [ScorebugRecipeEdit("raw_offset", png)]),
                (
                    "four",
                    [
                        ScorebugRecipeEdit("score_buga", png),
                        ScorebugRecipeEdit("shield_espn", png),
                        ScorebugRecipeEdit("digital_font", png),
                        ScorebugRecipeEdit("score_buga", png),
                    ],
                ),
            )
            for name, edits in invalid_cases:
                destination = root / f"invalid-{name}.json"
                with self.subTest(name=name), self.assertRaises(RecipeError):
                    create_nfl_scorebug_recipe(
                        output=destination, purpose="Invalid", edits=edits
                    )
                self.assertFalse(os.path.lexists(destination))

            for purpose in ("", "x\0y", "x" * 4097):
                destination = root / f"purpose-{len(purpose)}.json"
                with self.subTest(purpose=repr(purpose)), self.assertRaises(RecipeError):
                    create_nfl_scorebug_recipe(
                        output=destination,
                        purpose=purpose,
                        edits=[ScorebugRecipeEdit("score_buga", png)],
                    )
                self.assertFalse(os.path.lexists(destination))

    def test_nfl_rejects_wrong_target_dimensions_invalid_png_and_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wrong = make_png(root / "wrong.png", (65, 64))
            wrong_mode = make_png(root / "wrong-mode.png", (64, 64), mode="RGB")
            invalid = root / "invalid.png"
            invalid.write_bytes(b"not a png")
            valid = make_png(root / "valid.png", (64, 64))
            linked = root / "linked.png"
            linked.symlink_to(valid)
            for name, supplied in (
                ("dimension", wrong),
                ("mode", wrong_mode),
                ("invalid", invalid),
                ("symlink", linked),
            ):
                output = root / f"reject-{name}.json"
                with self.subTest(reason=name), self.assertRaises(RecipeError):
                    create_nfl_scorebug_recipe(
                        output=output,
                        purpose="Rejected",
                        edits=[ScorebugRecipeEdit("score_buga", supplied)],
                    )
                self.assertFalse(os.path.lexists(output))

    def test_existing_and_broken_symlink_recipe_outputs_are_refused_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            apf_png = make_png(root / "jersey.png", (1024, 1024))
            pants_png = root / "pants.png"
            Image.new("RGBA", (512, 512), (5, 15, 25, 255)).save(pants_png)
            nfl_png = make_png(root / "score.png", (64, 64))
            existing = root / "existing.json"
            existing.write_bytes(b"sentinel")
            broken = root / "broken.json"
            broken.symlink_to(root / "missing.json")

            calls = (
                lambda path: create_apf_jersey_recipe(
                    output=path, asset_index=6, png=apf_png
                ),
                lambda path: create_apf_pants_recipe(
                    output=path, asset_index=13, png=pants_png
                ),
                lambda path: create_nfl_scorebug_recipe(
                    output=path,
                    purpose="Scorebug",
                    edits=[ScorebugRecipeEdit("score_buga", nfl_png)],
                ),
            )
            for call in calls:
                with self.subTest(workflow=call), self.assertRaises(OutputRefusedError):
                    call(existing)
                self.assertEqual(existing.read_bytes(), b"sentinel")
                with self.assertRaises(OutputRefusedError):
                    call(broken)
                self.assertTrue(broken.is_symlink())

            wrong_suffix = root / "recipe.txt"
            for call in calls:
                with self.subTest(workflow=call), self.assertRaises(OutputRefusedError):
                    call(wrong_suffix)
                self.assertFalse(os.path.lexists(wrong_suffix))

    def test_partial_recipe_outputs_are_cleaned_for_all_workflows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            apf_png = make_png(root / "jersey.png", (1024, 1024))
            pants_png = root / "pants.png"
            Image.new("RGBA", (512, 512), (5, 15, 25, 255)).save(pants_png)
            nfl_png = make_png(root / "score.png", (64, 64))

            def fail_after_prefix(descriptor: int, payload: bytes) -> None:
                os.write(descriptor, payload[:17])
                raise OSError("synthetic write failure")

            calls = (
                (
                    root / "partial-apf.json",
                    lambda output: create_apf_jersey_recipe(
                        output=output, asset_index=6, png=apf_png
                    ),
                ),
                (
                    root / "partial-pants.json",
                    lambda output: create_apf_pants_recipe(
                        output=output, asset_index=13, png=pants_png
                    ),
                ),
                (
                    root / "partial-nfl.json",
                    lambda output: create_nfl_scorebug_recipe(
                        output=output,
                        purpose="Scorebug",
                        edits=[ScorebugRecipeEdit("score_buga", nfl_png)],
                    ),
                ),
            )
            with patch.object(recipes, "_write_payload", side_effect=fail_after_prefix):
                for output, call in calls:
                    with self.subTest(output=output), self.assertRaises(RecipeError):
                        call(output)
                    self.assertFalse(os.path.lexists(output))


if __name__ == "__main__":
    unittest.main()
