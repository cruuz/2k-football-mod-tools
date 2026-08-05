"""Headless product tests for Logos → Wordmarks (all typed slots 0..205)."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageDraw  # noqa: E402
from PyQt5 import sip  # noqa: E402
from PyQt5.QtWidgets import QApplication, QTabWidget  # noqa: E402

from mod_editor.apf_studio.gui import ApfTextLogoPanel, LogosStudioPage  # noqa: E402
from mod_editor.apf_studio.models import ApfStatus, Modification, UniformAsset  # noqa: E402


class _Session:
    def __init__(self) -> None:
        self.rows: dict[str, Modification] = {}

    def modification(self, asset_id: str) -> Modification | None:
        return self.rows.get(asset_id)


class _Facade:
    def __init__(self, *, ready: bool = True) -> None:
        self.source_ready = ready
        self.source = (
            SimpleNamespace(source_sha256="d" * 64, index_0a=Path("/game/0A"))
            if ready
            else None
        )
        self.session = _Session()
        self.modified_asset_ids: frozenset[str] = frozenset()
        self.assets = tuple(
            UniformAsset(
                family="textlogo",
                asset_index=index,
                asset_id=f"apf:uniform:textlogo:{index:02d}",
                title=f"Wordmark {index:03d}",
                width=512,
                height=128,
                png_contract="Synthetic exact wordmark contract.",
                status=ApfStatus.EDITABLE,
                outer_index=500 + index,
                inner_index=0,
                affected_teams=(("Americans",) if index == 8 else ()),
            )
            for index in range(206)
        )
        self.replace_calls: list[tuple[str, Path]] = []
        self.revert_calls: list[str] = []

    def uniform_assets(self, family: str | None = None):
        return self.assets if family in (None, "textlogo") else ()

    def require_session(self) -> _Session:
        return self.session

    def preview_uniform(self, asset_id: str, _progress: object) -> Path:
        return Path(f"/private/{asset_id}.png")

    def replace_uniform(
        self, asset_id: str, path: Path, _progress: object
    ) -> Modification:
        self.replace_calls.append((asset_id, path))
        payload = path.read_bytes()
        modification = Modification(
            asset_id=asset_id,
            kind="uniform",
            replacement_path=path,
            replacement_sha256=__import__("hashlib").sha256(payload).hexdigest(),
            metadata={"family": "textlogo"},
        )
        self.session.rows[asset_id] = modification
        self.modified_asset_ids = frozenset(self.session.rows)
        return modification

    def revert(self, asset_id: str, _progress: object) -> bool:
        self.revert_calls.append(asset_id)
        removed = self.session.rows.pop(asset_id, None) is not None
        self.modified_asset_ids = frozenset(self.session.rows)
        return removed

    def capability_cards(self, *_args: object):
        return ()

    def browse_assets(self, **_kwargs: object):
        return ()


class _RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, object, bool]] = []

    def __call__(
        self,
        label: str,
        operation: object,
        on_success: object = None,
        blocking: bool = True,
    ) -> bool:
        self.calls.append((label, operation, on_success, blocking))
        return True

    def last(self) -> tuple[str, object, object, bool]:
        return self.calls[-1]


class ApfTextLogoGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.application.quit()
        sip.delete(cls.application)
        cls.application = None

    def test_all_206_typed_slots_are_exposed_and_crest_is_explicitly_separate(self) -> None:
        facade = _Facade()
        runner = _RecordingRunner()
        panel = ApfTextLogoPanel(facade, runner)  # type: ignore[arg-type]
        try:
            self.assertEqual(panel.slot.minimum(), 0)
            self.assertEqual(panel.slot.maximum(), 205)
            self.assertEqual(len(panel._assets), 206)
            self.assertEqual(panel.fit_mode.itemData(0), "contain")
            self.assertEqual(panel.fit_mode.itemData(1), "cover")
            self.assertIn("not the square", panel.identity.text().casefold())
            panel.slot.setValue(8)
            self.application.processEvents()
            self.assertIn("uniform_textlogo_08.iff", panel.owners.text())
            self.assertIn("Americans", panel.owners.text())
            panel.slot.setValue(205)
            self.application.processEvents()
            self.assertIn("uniform_textlogo_205.iff", panel.owners.text())
        finally:
            panel.deleteLater()
            self.application.processEvents()

    def test_import_prepares_opaque_native_png_and_stages_normal_project_edit(self) -> None:
        facade = _Facade()
        runner = _RecordingRunner()
        panel = ApfTextLogoPanel(facade, runner)  # type: ignore[arg-type]
        try:
            panel.slot.setValue(205)
            panel.fit_mode.setCurrentIndex(1)
            with tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "logo.png"
                image = Image.new("RGBA", (200, 400), (0, 0, 0, 0))
                ImageDraw.Draw(image).ellipse(
                    (20, 20, 180, 380), fill=(20, 200, 90, 160)
                )
                image.save(source)
                panel._stage_path(source)
                # Step one prepares the exact fitted pixels for preview.
                label, operation, complete, blocking = runner.last()
                self.assertEqual(label, "Preparing wordmark 205 preview")
                self.assertTrue(blocking)
                prepared = operation(lambda *_args: None)  # type: ignore[operator]
                with mock.patch(
                    "mod_editor.apf_studio.gui.confirm_prepared_slot_image",
                    return_value=True,
                ) as preview:
                    complete(prepared)  # type: ignore[operator]
                preview.assert_called_once()
                self.assertEqual(
                    Path(preview.call_args.args[1]),
                    Path(getattr(prepared, "output_path")),
                )
                # Step two stages the previewed pixels unchanged.
                label, operation, complete, blocking = runner.last()
                self.assertEqual(label, "Importing wordmark 205")
                self.assertTrue(blocking)
                result = operation(lambda *_args: None)  # type: ignore[operator]
                with mock.patch(
                    "mod_editor.apf_studio.gui.QMessageBox.information"
                ):
                    complete(result)  # type: ignore[operator]
            self.assertEqual(facade.replace_calls[0][0], "apf:uniform:textlogo:205")
            replacement = facade.replace_calls[0][1]
            self.assertEqual(replacement, Path(getattr(prepared, "output_path")))
            with Image.open(replacement) as staged:
                staged.load()
                self.assertEqual(staged.size, (512, 128))
                self.assertEqual(staged.mode, "RGBA")
                self.assertEqual(staged.getchannel("A").getextrema(), (255, 255))
            self.assertIn("Modified", panel.status.text())

            panel._revert()
            _label, revert_operation, revert_complete, _blocking = runner.last()
            self.assertTrue(revert_operation(lambda *_args: None))  # type: ignore[operator]
            revert_complete(True)  # type: ignore[operator]
            self.assertEqual(facade.revert_calls, ["apf:uniform:textlogo:205"])
            self.assertNotIn("Modified", panel.status.text())
        finally:
            panel.deleteLater()
            self.application.processEvents()

    def test_declining_the_preview_stages_nothing(self) -> None:
        facade = _Facade()
        runner = _RecordingRunner()
        panel = ApfTextLogoPanel(facade, runner)  # type: ignore[arg-type]
        try:
            panel.slot.setValue(7)
            with tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "logo.png"
                Image.new("RGBA", (300, 100), (10, 200, 40, 255)).save(source)
                panel._stage_path(source)
                _label, operation, complete, _blocking = runner.last()
                prepared = operation(lambda *_args: None)  # type: ignore[operator]
                prepared_path = Path(getattr(prepared, "output_path"))
                self.assertTrue(prepared_path.is_file())
                with mock.patch(
                    "mod_editor.apf_studio.gui.confirm_prepared_slot_image",
                    return_value=False,
                ):
                    complete(prepared)  # type: ignore[operator]
                # Declined: nothing staged and the private preview is removed.
                self.assertEqual(facade.replace_calls, [])
                self.assertFalse(prepared_path.exists())
        finally:
            panel.deleteLater()
            self.application.processEvents()

    def _prepared_preview(self, panel, runner, facade, source: Path,
                          fit_index: int) -> Path:
        panel.slot.setValue(205)
        panel.fit_mode.setCurrentIndex(fit_index)
        panel._stage_path(source)
        _label, operation, complete, _blocking = runner.last()
        prepared = operation(lambda *_args: None)  # type: ignore[operator]
        with mock.patch(
            "mod_editor.apf_studio.gui.confirm_prepared_slot_image",
            return_value=True,
        ) as preview:
            complete(prepared)  # type: ignore[operator]
        self.assertEqual(preview.call_count, 1)
        return Path(preview.call_args.args[1])

    def test_preview_thumbnail_matches_the_selected_fit_mode(self) -> None:
        """The previewed pixels must be exactly what the fit mode promises."""
        with tempfile.TemporaryDirectory() as directory:
            # A tall, fully opaque magenta source.  Contain must pad the sides
            # (flattened to black); cover must center-crop with no padding.
            source = Path(directory) / "tall.png"
            Image.new("RGBA", (100, 400), (255, 0, 255, 255)).save(source)

            facade = _Facade()
            runner = _RecordingRunner()
            panel = ApfTextLogoPanel(facade, runner)  # type: ignore[arg-type]
            try:
                contain_preview = self._prepared_preview(
                    panel, runner, facade, source, fit_index=0
                )
                with Image.open(contain_preview) as shown:
                    self.assertEqual(shown.size, (512, 128))
                    self.assertEqual(shown.getchannel("A").getextrema(),
                                     (255, 255))
                    corner = shown.getpixel((0, 0))
                    center = shown.getpixel((256, 64))
                # Side padding was flattened onto the opaque-black background.
                self.assertEqual(corner, (0, 0, 0, 255))
                self.assertEqual(center, (255, 0, 255, 255))

                facade2 = _Facade()
                runner2 = _RecordingRunner()
                panel2 = ApfTextLogoPanel(facade2, runner2)  # type: ignore[arg-type]
                cover_preview = self._prepared_preview(
                    panel2, runner2, facade2, source, fit_index=1
                )
                with Image.open(cover_preview) as shown:
                    self.assertEqual(shown.size, (512, 128))
                    corner = shown.getpixel((0, 0))
                    center = shown.getpixel((256, 64))
                    edge = shown.getpixel((511, 127))
                # Cover fills every pixel with the cropped art -- no padding.
                self.assertEqual(corner, (255, 0, 255, 255))
                self.assertEqual(center, (255, 0, 255, 255))
                self.assertEqual(edge, (255, 0, 255, 255))
                panel2.deleteLater()
                self.application.processEvents()
            finally:
                panel.deleteLater()
                self.application.processEvents()

    def test_logos_workspace_has_distinct_team_logo_wordmark_and_inventory_tabs(self) -> None:
        facade = _Facade(ready=False)
        page = LogosStudioPage(facade, _RecordingRunner())  # type: ignore[arg-type]
        try:
            tab_widget = page.findChild(QTabWidget, "workspaceTabs")
            self.assertIsNotNone(tab_widget)
            self.assertEqual(tab_widget.count(), 3)  # type: ignore[union-attr]
            self.assertEqual(tab_widget.tabText(0), "Team Logo")  # type: ignore[union-attr]
            self.assertEqual(tab_widget.tabText(1), "Wordmarks (206)")  # type: ignore[union-attr]
            self.assertEqual(tab_widget.tabText(2), "All Logo && Team Art")  # type: ignore[union-attr]
            team_tip = tab_widget.tabToolTip(0).casefold()  # type: ignore[union-attr]
            wordmark_tip = tab_widget.tabToolTip(1).casefold()  # type: ignore[union-attr]
            self.assertIn("selector slot 5", team_tip)
            self.assertIn("frontend/team select cache", team_tip)
            self.assertIn("separate selector slot 6", wordmark_tip)
            self.assertIn("never resizes a crest", wordmark_tip)
        finally:
            page.deleteLater()
            self.application.processEvents()


if __name__ == "__main__":
    unittest.main()
