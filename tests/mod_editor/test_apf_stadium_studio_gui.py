"""Headless Qt contract tests for the honest APF Stadium Studio page."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import sip  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.apf_studio.catalog import ApfCatalog  # noqa: E402
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

    def test_page_inventory_exports_and_unresolved_writer_boundary(self) -> None:
        texture = _asset(52, 1, "stadium_wall", "TXTR", ApfCategory.STADIUMS)
        helper = _asset(52, 2, "stadium_helper", "SPCI", ApfCategory.ALL_ASSETS)
        scene = _asset(52, 4, "stadium", "SCNE", ApfCategory.STADIUMS)
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
            self.assertIn("Coming Soon", page.replace_package_button.toolTip())
            self.assertIn("ownership", page.surface_boundary.text())
            self.assertIn("116 scene meshes", page.material_findings_note.text())
            self.assertIn("328 draws", page.material_findings_note.text())
            self.assertIn("113 material records", page.material_findings_note.text())
            self.assertIn("13 shader families", page.material_findings_note.text())
            self.assertIn("737 known named texture", page.material_findings_note.text())
            self.assertIn(
                "material-array base", page.material_findings_note.toolTip()
            )
            self.assertIn(
                "texture-object pointer", page.material_findings_note.toolTip()
            )
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
                        apf_scene_node_indices=(27,),
                        apf_source_mesh_index=3,
                        material_index=None,
                    ),
                ),
            )
            page._surface_selected(0, 0)
            self.assertIn("APF scene node 27", page.surface_identity.text())
            self.assertIn("source mesh 3", page.surface_identity.text())
            self.assertIn("not decoded", page.surface_boundary.text())
            self.assertFalse(page.replace_package_button.isEnabled())
            self.assertFalse(page.revert_package_button.isEnabled())
        finally:
            page.close()
            sip.delete(page)


if __name__ == "__main__":
    unittest.main()
