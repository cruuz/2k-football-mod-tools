"""Finding the stadium geometry you can actually edit.

Both editors could round-trip stadium models before this, and both hid which
model that was.  2K5 listed 477 scenes with one editable scene among them and
nothing marking it; APF required clicking the right surface out of 89 nodes to
reach any of its 77 authorized targets.  A modder asking "have stadium models
been working?" would open the wrong thing, watch Import stage nothing, and
answer their own question incorrectly.

These tests pin the discovery surfaces that replaced the hunt.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402


@dataclass(frozen=True)
class _Target:
    target_id: str
    vertex_count: int


@dataclass(frozen=True)
class _Scene:
    scene_id: str
    outer_index: int
    chunk_index: int
    mesh_count: int
    vertex_count: int
    geometry_targets: tuple[_Target, ...] = ()


class Nfl2k5StadiumSceneListTests(unittest.TestCase):
    """The 2K5 scene list marks, filters, and opens on editable geometry."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _window(self):
        from mod_editor.gui.studio_qt import StudioMainWindow

        window = StudioMainWindow()
        state = window._stadium_browser
        self.assertIsNotNone(state)
        assert state is not None

        # Opening a scene asks the facade for geometry and textures, which this
        # browse-only window has none of. Record the selection instead: what is
        # under test is which scene the list marks and offers.
        opened: list[str] = []

        def _record(current, _previous=None):
            if current is not None:
                identifier = str(current.data(32))  # Qt.UserRole
                state.selected_scene_id = identifier
                opened.append(identifier)

        window._select_stadium_scene = _record  # type: ignore[method-assign]
        state.scene_list.currentItemChanged.disconnect()
        state.scene_list.currentItemChanged.connect(_record)
        window.opened_scenes = opened  # type: ignore[attr-defined]
        state.scenes = (
            _Scene("scene.a", 3136, 6, 105, 17_669),
            _Scene("scene.b", 3200, 2, 40, 5_000),
            _Scene(
                "scene.editable",
                3280,
                5,
                76,
                16_742,
                tuple(_Target(f"t{index}", 100) for index in range(76)),
            ),
            _Scene("scene.d", 3400, 1, 12, 900),
        )
        state.scenes_loaded = True
        return window, state

    def test_the_editable_scene_is_marked_and_opened_first(self) -> None:
        window, state = self._window()
        try:
            window._populate_stadium_scenes()
            self.app.processEvents()
            self.assertEqual(state.scene_list.count(), 4)
            labels = [
                state.scene_list.item(row).text()
                for row in range(state.scene_list.count())
            ]
            marked = [label for label in labels if label.startswith("✎")]
            self.assertEqual(len(marked), 1)
            self.assertIn("76 editable meshes", marked[0])
            # Opening on row 0 would land on a scene Import cannot write.
            self.assertEqual(state.scene_list.currentRow(), 2)
            self.assertEqual(state.editable_only.text().strip()[-3:], "(1)")
        finally:
            window.deleteLater()
            self.app.processEvents()

    def test_a_view_only_scene_says_import_has_nothing_to_write(self) -> None:
        window, state = self._window()
        try:
            window._populate_stadium_scenes()
            self.app.processEvents()
            tip = state.scene_list.item(0).toolTip()
            self.assertIn("View and glTF export only", tip)
            editable_tip = state.scene_list.item(2).toolTip()
            self.assertIn("can be imported", editable_tip)
        finally:
            window.deleteLater()
            self.app.processEvents()

    def test_the_filter_narrows_to_editable_scenes_and_keeps_the_selection(self) -> None:
        window, state = self._window()
        try:
            window._populate_stadium_scenes()
            self.app.processEvents()
            state.editable_only.setChecked(True)
            self.app.processEvents()
            self.assertEqual(state.scene_list.count(), 1)
            self.assertEqual(state.count_label.text(), "1 / 4")
            self.assertTrue(state.scene_list.item(0).text().startswith("✎"))
            state.editable_only.setChecked(False)
            self.app.processEvents()
            self.assertEqual(state.scene_list.count(), 4)
            self.assertEqual(state.count_label.text(), "4")
        finally:
            window.deleteLater()
            self.app.processEvents()

    def test_no_scenes_is_still_an_honest_empty_state(self) -> None:
        window, state = self._window()
        try:
            state.scenes = ()
            window._populate_stadium_scenes()
            self.app.processEvents()
            self.assertEqual(state.scene_list.count(), 0)
            self.assertIn("No matching stadium scenes", state.scene_label.text())
            self.assertIsNone(state.selected_scene_id)
        finally:
            window.deleteLater()
            self.app.processEvents()


class ApfEditableMeshPickerTests(unittest.TestCase):
    """APF lists its authorized POSITION targets instead of hiding them."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _page(self):
        from mod_editor.apf_studio.gui import StadiumStudioPage

        class _Facade:
            source_ready = False
            source = None
            modified_asset_ids = frozenset()

            def capability_cards(self, _category=None):
                return ()

            def stadium_scenes(self, _search=""):
                return ()

            def stadium_package_assets(self, _scene):
                return ()

        page = StadiumStudioPage(
            _Facade(),  # type: ignore[arg-type]
            lambda *_a, **_k: None,  # type: ignore[arg-type]
        )
        # Past the load and open-a-scene walls, so what the buttons report is
        # about the mesh selection and nothing else.
        page.facade.source_ready = True  # type: ignore[attr-defined]
        page._preview = object()  # type: ignore[assignment]
        return page

    def test_every_authorized_target_of_the_scene_is_offered(self) -> None:
        from mod_editor.apf_studio import stadium_model_import
        from mod_editor.apf_studio.stadium import ApfStadiumScene

        page = self._page()
        try:
            targets = stadium_model_import.targets()
            self.assertEqual(len(targets), 77)
            outer, inner = targets[0].outer_index, targets[0].inner_index
            scene = ApfStadiumScene(
                asset_id=f"apf:outer:{outer}:inner:{inner}",
                outer_index=outer,
                inner_index=inner,
                decoded_size=1,
                package_asset_count=1,
            )
            page._populate_mesh_targets(scene)
            # One prompt row plus every authorized mesh.
            self.assertEqual(page.mesh_target.count(), len(targets) + 1)
            self.assertTrue(page.mesh_target.isEnabled())
            self.assertIn("77 editable meshes", page.mesh_target.itemText(0))
            offered = {
                page.mesh_target.itemData(index).target_id
                for index in range(1, page.mesh_target.count())
            }
            self.assertEqual(offered, {target.target_id for target in targets})
            # Nothing is selected until the modder chooses, and choosing one
            # is what unlocks Export/Import.
            self.assertIsNone(page._selected_model_target)
            self.assertTrue(
                str(page.export_model_button.property("disableReason") or "")
            )
            page.mesh_target.setCurrentIndex(1)
            self.app.processEvents()
            self.assertEqual(
                page._selected_model_target.target_id, targets[0].target_id
            )
            self.assertEqual(
                str(page.export_model_button.property("disableReason") or ""), ""
            )
            self.assertEqual(
                str(page.import_model_button.property("disableReason") or ""), ""
            )
        finally:
            page.deleteLater()
            self.app.processEvents()

    def test_a_scene_with_no_authorized_target_says_so(self) -> None:
        from mod_editor.apf_studio.stadium import ApfStadiumScene

        page = self._page()
        try:
            scene = ApfStadiumScene(
                asset_id="apf:outer:9999:inner:0",
                outer_index=9999,
                inner_index=0,
                decoded_size=1,
                package_asset_count=1,
            )
            page._populate_mesh_targets(scene)
            self.assertFalse(page.mesh_target.isEnabled())
            self.assertIn("No editable meshes", page.mesh_target.itemText(0))
            block = str(page.export_model_button.property("disableReason") or "")
            self.assertIn("no catalog-authorized POSITION target", block)
            # Never silent-gray: the control stays clickable and explains.
            self.assertTrue(page.export_model_button.isEnabled())
            self.assertTrue(page.import_model_button.isEnabled())
        finally:
            page.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
