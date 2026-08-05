"""Headless Qt contract tests for the honest APF Stadium Studio page."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import sip  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.apf_studio.catalog import ApfCatalog  # noqa: E402
from mod_editor.apf_studio.facade import ApfStudioFacade  # noqa: E402
from mod_editor.apf_studio.gui import StadiumStudioPage  # noqa: E402
from mod_editor.apf_studio.models import (  # noqa: E402
    ApfAsset,
    ApfCategory,
    ApfStatus,
)
from mod_editor.apf_studio.stadium import stadium_package_assets, stadium_scenes  # noqa: E402
from mod_editor.gui.stadium_viewer import (  # noqa: E402
    GltfWireframeModel,
    SurfaceIdentity,
    WireTriangle,
)


def _asset(
    outer: int,
    inner: int,
    name: str,
    type_name: str,
    category: ApfCategory,
) -> ApfAsset:
    return ApfAsset(
        asset_id=f"apf:outer:{outer}:inner:{inner}",
        outer_index=outer,
        inner_index=inner,
        name=name,
        type_name=type_name,
        asset_class="synthetic_fixture",
        category=category,
        status=ApfStatus.EXPORT_ONLY,
        decoded_size=2_048,
        outer_size=16_384,
        part_count=2,
    )


class _Facade:
    def __init__(self, catalog: ApfCatalog):
        self.catalog = catalog
        self.source = SimpleNamespace(source_sha256=catalog.source_sha256)
        self.source_ready = True

    def require_catalog(self) -> ApfCatalog:
        return self.catalog

    def browse_assets(self, **kwargs: object) -> tuple[ApfAsset, ...]:
        category = kwargs.get("category")
        return tuple(
            item
            for item in self.catalog.assets
            if category is None or item.category is category
        )

    def capability_cards(self, _category: ApfCategory) -> tuple[object, ...]:
        return ()

    def stadium_scenes(self, search: str = "") -> tuple[object, ...]:
        return stadium_scenes(self.catalog, search)

    def stadium_package_assets(self, scene: object) -> tuple[ApfAsset, ...]:
        return stadium_package_assets(self.catalog, scene)  # type: ignore[arg-type]


class ApfStadiumStudioGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.application.quit()
        sip.delete(cls.application)
        cls.application = None

    def test_page_inventory_exports_and_bounded_geometry_import_boundary(self) -> None:
        texture = _asset(14, 1, "stadium_wall", "TXTR", ApfCategory.STADIUMS)
        helper = _asset(14, 2, "stadium_helper", "SPCI", ApfCategory.ALL_ASSETS)
        scene = _asset(14, 8, "stadium", "SCNE", ApfCategory.STADIUMS)
        catalog = ApfCatalog(
            source_sha256="a" * 64,
            outer_count=1,
            iff_count=1,
            non_iff_count=0,
            inner_count=3,
            assets=(texture, helper, scene),
            uniform_assets=(),
            capabilities=(),
            audio_selection_manifest=Path("/nonexistent/audio-selection.json"),
        )
        tasks: list[str] = []

        def run_task(
            title: str,
            _operation: object,
            _complete: object,
            _busy: bool,
        ) -> None:
            tasks.append(title)

        page = StadiumStudioPage(_Facade(catalog), run_task)  # type: ignore[arg-type]
        try:
            page.set_context()
            self.application.processEvents()
            self.assertEqual(page.scene_count.text(), "1 / 1")
            self.assertEqual(page.scene_list.count(), 1)
            self.assertEqual(page.package_list.count(), 3)
            self.assertEqual(page.package_count.text(), "3 records")
            self.assertTrue(page.export_scene_button.isEnabled())
            self.assertTrue(page.export_package_button.isEnabled())
            self.assertFalse(page.replace_package_button.isEnabled())
            self.assertEqual(page.replace_package_button.text(), "Replace (locked)")
            self.assertFalse(page.revert_package_button.isEnabled())
            self.assertNotIn("Coming Soon", page.replace_package_button.toolTip())
            self.assertIn("POSITION-only", page.replace_package_button.toolTip())
            self.assertFalse(page.export_model_button.isEnabled())
            self.assertFalse(page.import_model_button.isEnabled())
            self.assertIn("ownership", page.surface_boundary.text())
            self.assertIn("89 exact scene surfaces", page.material_findings_note.text())
            self.assertIn("84 material records", page.material_findings_note.text())
            self.assertIn("78 embedded textures", page.material_findings_note.text())
            self.assertIn("20 shader families", page.material_findings_note.text())
            self.assertIn("Replace, Revert", page.material_findings_note.text())
            self.assertIn("Xbox 360 hardware", page.material_findings_note.toolTip())
            self.assertIn("additional stadium scene", page.material_findings_note.toolTip())
            self.assertEqual(
                tasks,
                [
                    "Preparing stadium package texture",
                    "Opening APF Stadium Studio",
                ],
            )

            page._model = GltfWireframeModel(
                triangles=(
                    WireTriangle((0, 0, 0), (1, 0, 0), (0, 1, 0), 0, 0),
                ),
                center=(0.5, 0.5, 0.0),
                radius=0.5,
                source_triangle_count=1,
                mesh_count=1,
                surfaces=(
                    SurfaceIdentity(
                        mesh_index=0,
                        primitive_index=0,
                        mesh_name="Upper deck",
                        gltf_node_indices=(0,),
                        node_names=("Upper deck",),
                        apf_scene_node_indices=(13,),
                        apf_source_mesh_index=3,
                        material_index=None,
                    ),
                ),
            )
            page._preview = SimpleNamespace(gltf_path=Path("/private/scene.gltf"))
            page._surface_selected(0, 0)
            self.assertIn("APF scene node 13", page.surface_identity.text())
            self.assertIn("source mesh 3", page.surface_identity.text())
            self.assertIn("outer14.inner8.node13", page.surface_boundary.text())
            self.assertIn("UVs, normals, materials", page.surface_boundary.text())
            self.assertTrue(page.export_model_button.isEnabled())
            self.assertTrue(page.import_model_button.isEnabled())
            self.assertFalse(page.replace_package_button.isEnabled())
            self.assertFalse(page.revert_package_button.isEnabled())
        finally:
            page.close()
            sip.delete(page)

    def test_facade_stadium_texture_stage_revert_owns_private_snapshot(self) -> None:
        facade = ApfStudioFacade()
        facade.source = SimpleNamespace(game_root=Path("/private/game"))
        with tempfile.TemporaryDirectory(prefix="apf-stadium-facade-") as directory:
            source = Path(directory) / "source.png"
            source.write_bytes(b"user-png")

            def stage(
                game_root: Path,
                texture_index: int,
                source_png: Path,
                destination: Path,
            ) -> tuple[Path, tuple[int, int]]:
                self.assertEqual(game_root, Path("/private/game"))
                self.assertEqual(texture_index, 55)
                self.assertEqual(source_png, source)
                destination.write_bytes(b"private-native-png")
                return destination, (17, 13)

            with mock.patch(
                "mod_editor.apf_studio.facade.stadium_texture.stage_replacement_png",
                side_effect=stage,
            ):
                staged = facade.stage_stadium_texture(55, source)
            self.assertNotEqual(staged, source)
            self.assertEqual(staged.read_bytes(), b"private-native-png")
            self.assertTrue(facade.revert_stadium_texture(55))
            self.assertFalse(staged.exists())
            self.assertEqual(source.read_bytes(), b"user-png")
        facade.close()


if __name__ == "__main__":
    unittest.main()
