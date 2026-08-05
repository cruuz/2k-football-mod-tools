"""Retail-free contract tests for the exact Stadium texture provider kind."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


TOOLS = Path(__file__).resolve().parents[2] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import nfl2k5_visual_mod_project as unified  # noqa: E402


class UnifiedStadiumTextureCompositionTests(unittest.TestCase):
    def _project(self, path: Path, png: Path, *, target: str | None = None) -> None:
        document = {
            "edits": [{
                "kind": unified.STADIUM_TEXTURE_KIND,
                "target": target or unified.STADIUM_TEXTURE_TARGET,
                "png": str(png),
            }],
            "purpose": "Synthetic cement01 unified-provider contract test.",
            "schema": unified.SCHEMA,
        }
        path.write_bytes(unified.canonical_json(document))

    def _same_scene_project(self, path: Path, first: Path, second: Path) -> None:
        document = {
            "edits": [
                {
                    "kind": unified.STADIUM_TEXTURE_KIND,
                    "target": "nfl2k5.stadium.o3280.c0005.scene2648.texture0002",
                    "png": str(first),
                },
                {
                    "kind": unified.STADIUM_TEXTURE_KIND,
                    "target": "nfl2k5.stadium.o3280.c0005.scene2648.texture0004",
                    "png": str(second),
                },
            ],
            "purpose": "Synthetic same-SCNE Stadium composition contract test.",
            "schema": unified.SCHEMA,
        }
        path.write_bytes(unified.canonical_json(document))

    def _geometry_project(
        self, path: Path, recipe: Path, texture: Path | None = None
    ) -> None:
        edits = [{
            "kind": unified.STADIUM_GEOMETRY_KIND,
            "target": unified.STADIUM_GEOMETRY_TARGET,
            "recipe": str(recipe),
        }]
        if texture is not None:
            edits.append({
                "kind": unified.STADIUM_TEXTURE_KIND,
                "target": unified.STADIUM_TEXTURE_TARGET,
                "png": str(texture),
            })
        path.write_bytes(unified.canonical_json({
            "edits": edits,
            "purpose": "Synthetic bounded Stadium geometry contract test.",
            "schema": unified.SCHEMA,
        }))

    @staticmethod
    def _built() -> tuple[bytes, list[tuple[str, bytes]], dict, str, dict]:
        target = {
            "selector": unified.STADIUM_TEXTURE_TARGET,
            "xiso_pack_path": "vc_53450030/9",
            "xiso_pack_sector": 35_531,
            "xiso_pack_size": 634_941_440,
            "xiso_pack_sha256": "a" * 64,
            "pack_offset": 0x07EA5A40,
            "xiso_absolute_span_offset": 35_531 * 2_048 + 0x07EA5A40,
            "span_sha256": "b" * 64,
        }
        return (
            b"synthetic fixed SCNE replacement",
            [("stadium-cement01-preview.png", b"derived preview")],
            {
                "schema": "nfl2k5_stadium_texture_unified_import/v1",
                "input_png": {"path": "staged.png"},
                "target": target,
            },
            unified.STADIUM_TEXTURE_TARGET,
            target,
        )

    def test_any_canonical_stadium_texture_target_is_schema_accepted(self) -> None:
        with tempfile.TemporaryDirectory(prefix="unified-stadium-test-") as temporary:
            root = Path(temporary)
            png = root / "cement01.png"
            png.write_bytes(b"user-authored PNG bytes")
            project_path = root / "project.json"
            self._project(project_path, png)
            project = unified.read_project(project_path)
            self.assertEqual(
                project.value["edits"][0]["target"],
                unified.STADIUM_TEXTURE_TARGET,
            )
            report = unified.validate_only(project_path)
            self.assertEqual(report["kind_counts"], {"stadium_texture": 1})

            self._project(
                project_path,
                png,
                target="nfl2k5.stadium.o3280.c0005.scene2648.texture0003",
            )
            project = unified.read_project(project_path)
            self.assertEqual(
                project.value["edits"][0]["target"],
                "nfl2k5.stadium.o3280.c0005.scene2648.texture0003",
            )

            self._project(project_path, png, target="stadium/free-form-name")
            with self.assertRaisesRegex(unified.ProjectError, "canonical Editable P8"):
                unified.read_project(project_path)

    def test_stadium_kind_dispatches_to_the_sealed_span_compiler(self) -> None:
        with tempfile.TemporaryDirectory(prefix="unified-stadium-test-") as temporary:
            root = Path(temporary)
            png = root / "cement01.png"
            png.write_bytes(b"user-authored PNG bytes")
            project_path = root / "project.json"
            self._project(project_path, png)
            project = unified.read_project(project_path)
            pins = unified.pin_project_inputs(project)
            work = root / "work"
            work.mkdir()
            owned_root = unified.ownership.track_existing(work, True)
            files = []
            try:
                with mock.patch.object(
                    unified.stadium_texture_adapter,
                    "build_unified_stadium_texture_import",
                    return_value=self._built(),
                ) as compiler:
                    built = unified.build_one_import(
                        0,
                        project.value["edits"][0],
                        project,
                        pins,
                        {},
                        root / "0",
                        root / "inventory.json",
                        owned_root,
                        files,
                        -1,
                    )
                self.assertEqual(built[3], unified.STADIUM_TEXTURE_TARGET)
                self.assertEqual(built[0], b"synthetic fixed SCNE replacement")
                self.assertEqual(compiler.call_count, 1)
                self.assertEqual(
                    compiler.call_args.args[2], unified.STADIUM_TEXTURE_TARGET
                )
                staged_png = compiler.call_args.args[3]
                self.assertTrue(staged_png.is_relative_to(work))
                self.assertEqual(staged_png.read_bytes(), png.read_bytes())
            finally:
                unified.ownership.cleanup_owned(files, [owned_root])

    def test_same_scene_targets_stage_once_and_use_one_composed_span(self) -> None:
        with tempfile.TemporaryDirectory(prefix="unified-stadium-test-") as temporary:
            root = Path(temporary)
            first = root / "cement01.png"
            second = root / "ibeam01.png"
            first.write_bytes(b"first user-authored PNG")
            second.write_bytes(b"second user-authored PNG")
            project_path = root / "project.json"
            self._same_scene_project(project_path, first, second)
            project = unified.read_project(project_path)
            pins = unified.pin_project_inputs(project)
            work = root / "work"
            work.mkdir()
            owned_root = unified.ownership.track_existing(work, True)
            files = []
            try:
                with mock.patch.object(
                    unified.stadium_texture_adapter,
                    "build_unified_stadium_texture_imports",
                    return_value=[self._built()],
                ) as compiler:
                    built = unified.build_stadium_scene_import(
                        0,
                        project.value["edits"],
                        project,
                        pins,
                        root / "0",
                        root / "inventory.json",
                        owned_root,
                        files,
                    )
                self.assertEqual(built[0], b"synthetic fixed SCNE replacement")
                self.assertEqual(compiler.call_count, 1)
                staged = compiler.call_args.args[2]
                self.assertEqual(
                    [selector for selector, _path in staged],
                    [
                        "nfl2k5.stadium.o3280.c0005.scene2648.texture0002",
                        "nfl2k5.stadium.o3280.c0005.scene2648.texture0004",
                    ],
                )
                self.assertEqual(staged[0][1].read_bytes(), first.read_bytes())
                self.assertEqual(staged[1][1].read_bytes(), second.read_bytes())
                self.assertNotEqual(staged[0][1], staged[1][1])
            finally:
                unified.ownership.cleanup_owned(files, [owned_root])

    def test_compression_cap_error_remains_human_readable_and_duplicate_fails(self) -> None:
        with tempfile.TemporaryDirectory(prefix="unified-stadium-test-") as temporary:
            root = Path(temporary)
            png = root / "cement01.png"
            png.write_bytes(b"user-authored PNG bytes")
            project_path = root / "project.json"
            self._project(project_path, png)
            project = unified.read_project(project_path)
            pins = unified.pin_project_inputs(project)
            work = root / "work"
            work.mkdir()
            owned_root = unified.ownership.track_existing(work, True)
            files = []
            error = unified.stadium_texture_adapter.StadiumTextureWriterError(
                unified.stadium_texture_adapter.FIXED_ALLOCATION_ERROR
            )
            try:
                with mock.patch.object(
                    unified.stadium_texture_adapter,
                    "build_unified_stadium_texture_import",
                    side_effect=error,
                ):
                    with self.assertRaisesRegex(
                        unified.ProjectError,
                        "Simplify large noisy or detail-heavy areas",
                    ):
                        unified.build_one_import(
                            0,
                            project.value["edits"][0],
                            project,
                            pins,
                            {},
                            root / "0",
                            root / "inventory.json",
                            owned_root,
                            files,
                            -1,
                        )
            finally:
                unified.ownership.cleanup_owned(files, [owned_root])

            duplicate = {
                "edits": project.value["edits"] * 2,
                "purpose": "Duplicate exact Stadium target must fail.",
                "schema": unified.SCHEMA,
            }
            project_path.write_bytes(unified.canonical_json(duplicate))
            with self.assertRaisesRegex(unified.ProjectError, "repeats"):
                unified.read_project(project_path)

    def test_geometry_recipe_schema_and_same_scene_texture_composition(self) -> None:
        with tempfile.TemporaryDirectory(prefix="unified-stadium-geometry-") as temporary:
            root = Path(temporary)
            recipe = root / "positions.json"
            recipe.write_bytes(b'{"private":"recipe"}\n')
            png = root / "surface.png"
            png.write_bytes(b"user-authored texture")
            project_path = root / "project.json"
            self._geometry_project(project_path, recipe, png)
            project = unified.read_project(project_path)
            self.assertEqual(
                [row["kind"] for row in project.value["edits"]],
                [unified.STADIUM_GEOMETRY_KIND, unified.STADIUM_TEXTURE_KIND],
            )
            self.assertEqual(
                unified.validate_only(project_path)["kind_counts"],
                {"stadium_geometry": 1, "stadium_texture": 1},
            )
            pins = unified.pin_project_inputs(project)
            work = root / "work"
            work.mkdir()
            owned_root = unified.ownership.track_existing(work, True)
            files = []
            try:
                with mock.patch.object(
                    unified.stadium_texture_adapter,
                    "build_unified_stadium_geometry_and_texture_import",
                    return_value=self._built(),
                ) as compiler:
                    built = unified.build_stadium_geometry_import(
                        0,
                        project.value["edits"][0],
                        [project.value["edits"][1]],
                        project,
                        pins,
                        root / "0",
                        root / "inventory.json",
                        owned_root,
                        files,
                    )
                self.assertEqual(built[0], b"synthetic fixed SCNE replacement")
                self.assertEqual(compiler.call_count, 1)
                staged_recipe = compiler.call_args.args[2]
                staged_textures = compiler.call_args.args[3]
                self.assertEqual(staged_recipe.read_bytes(), recipe.read_bytes())
                self.assertEqual(staged_textures[0][0], unified.STADIUM_TEXTURE_TARGET)
                self.assertEqual(staged_textures[0][1].read_bytes(), png.read_bytes())
            finally:
                unified.ownership.cleanup_owned(files, [owned_root])

            invalid = {
                "edits": [{
                    "kind": unified.STADIUM_GEOMETRY_KIND,
                    "target": "nfl2k5.stadium.arbitrary.geometry",
                    "recipe": str(recipe),
                }],
                "purpose": "Invalid geometry target must fail.",
                "schema": unified.SCHEMA,
            }
            project_path.write_bytes(unified.canonical_json(invalid))
            with self.assertRaisesRegex(unified.ProjectError, "bounded full-scene"):
                unified.read_project(project_path)


if __name__ == "__main__":
    unittest.main()
