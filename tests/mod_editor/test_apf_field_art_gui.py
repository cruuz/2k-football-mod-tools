"""Headless product tests for the bounded APF Field Art workspace."""

from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import tempfile
import unittest

from PIL import Image
from unittest import mock


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import sip  # noqa: E402
from PyQt5.QtGui import QImage  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.apf_studio import gui  # noqa: E402
from mod_editor.apf_studio.catalog import ApfCatalog  # noqa: E402
from mod_editor.apf_studio.field_art import (  # noqa: E402
    FieldArtKind,
)
from mod_editor.apf_studio.gui import (  # noqa: E402
    FIELD_ART_COVERED_TARGETS,
    FieldArtStudioPage,
)
from mod_editor.apf_studio.models import (  # noqa: E402
    ApfAsset,
    ApfCategory,
    ApfStatus,
)


def _write_png(path: Path, width: int, height: int) -> Path:
    """Write a real RGBA PNG so the panel's exact-size guard sees true pixels."""

    image = QImage(width, height, QImage.Format_RGBA8888)
    image.fill(0xFF203040)
    if not image.save(str(path), "PNG"):
        raise AssertionError(f"could not write test PNG at {path}")
    return path


def _asset(
    outer_index: int,
    inner_index: int,
    name: str,
    type_name: str,
    asset_class: str,
) -> ApfAsset:
    return ApfAsset(
        asset_id=f"apf:outer:{outer_index}:inner:{inner_index}",
        outer_index=outer_index,
        inner_index=inner_index,
        name=name,
        type_name=type_name,
        asset_class=asset_class,
        category=ApfCategory.FIELD_ART,
        status=ApfStatus.EXPORT_ONLY,
        decoded_size=1,
        outer_size=1,
        part_count=1,
    )


def _synthetic_catalog() -> ApfCatalog:
    assets: list[ApfAsset] = []
    for outer_index in range(118):
        assets.append(_asset(outer_index, 0, "endzone_l0", "TXTR", "texture"))
        if outer_index < 117:
            assets.append(
                _asset(outer_index, 1, "endzone_l1", "TXTR", "texture")
            )

    for ordinal, outer_index in enumerate(range(200, 204)):
        assets.extend(
            (
                _asset(outer_index, 0, "field", "SCNE", "scene_model_package"),
                _asset(outer_index, 1, "field_radiance", "TXTR", "texture"),
            )
        )
        if ordinal < 3:
            assets.append(_asset(outer_index, 2, "divots", "TXTR", "texture"))

    for inner_index, name in enumerate(
        (
            "divot_GrassRain",
            "divot_GrassSnow",
            "divot_GrassDry",
            "pc_field_goal",
            "Field_Pass_text",
            "Stride_number_field",
        )
    ):
        assets.append(_asset(300, inner_index, name, "TXTR", "texture"))
    for inner_index, name in enumerate(("divotb1", "field_pass01", "divota1"), 6):
        assets.append(
            _asset(300, inner_index, name, "SCNE", "scene_model_package")
        )
    assets.append(_asset(301, 0, "tc2_footballField", "SCNE", "scene_model_package"))
    assets.extend(
        (
            _asset(
                302,
                0,
                "there_is_a_penalty_onthe_field",
                "CurveAnim",
                "animation_curve",
            ),
            _asset(
                302,
                1,
                "penalty_onthe_field",
                "CurveAnim",
                "animation_curve",
            ),
        )
    )
    if len(assets) != 258:
        raise AssertionError("Synthetic Field Art inventory changed")
    return ApfCatalog(
        source_sha256="f" * 64,
        outer_count=1543,
        iff_count=1473,
        non_iff_count=70,
        inner_count=10_394,
        assets=tuple(assets),
        uniform_assets=(),
        capabilities=(),
        audio_selection_manifest=Path("synthetic-inner-selection.json"),
    )


class _Source:
    """Only the read-only 0A path the writer dispatch needs."""

    def __init__(self, index_0a: str = "/nonexistent/APF/0A") -> None:
        self.index_0a = index_0a


class _Facade:
    def __init__(self, catalog: ApfCatalog, *, ready: bool = True):
        self.catalog = catalog
        self.source_ready = ready
        self.source = _Source() if ready else None
        self.modified_asset_ids: frozenset[str] = frozenset()

    def require_catalog(self) -> ApfCatalog:
        return self.catalog

    def browse_assets(self, **kwargs: object) -> tuple[ApfAsset, ...]:
        return self.catalog.browse(**kwargs)  # type: ignore[arg-type]

    @staticmethod
    def capability_cards(_category: ApfCategory) -> tuple[object, ...]:
        return ()


def _do_not_run_tasks(*_args: object, **_kwargs: object) -> None:
    return None


class _RecordingRunner:
    """Capture the operations the page would run instead of threading them."""

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

    def operation_for(self, prefix: str) -> object:
        for label, operation, _on_success, _blocking in reversed(self.calls):
            if label.startswith(prefix):
                return operation
        raise AssertionError(f"no task was started with label prefix {prefix!r}")


class _CompletedProcess:
    def __init__(self, returncode: int, stderr: str = "", stdout: str = "") -> None:
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = stdout


class ApfFieldArtGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.application.quit()
        sip.delete(cls.application)
        cls.application = None

    def _page(
        self,
        catalog: ApfCatalog | None = None,
        *,
        ready: bool = True,
        runner: object | None = None,
    ) -> FieldArtStudioPage:
        page = FieldArtStudioPage(
            _Facade(catalog or _synthetic_catalog(), ready=ready),  # type: ignore[arg-type]
            runner or _do_not_run_tasks,  # type: ignore[arg-type]
        )
        page.set_context()
        self.application.processEvents()
        return page

    def test_semantic_map_and_exact_catalog_browser_ship_together(self) -> None:
        page = self._page()
        try:
            self.assertEqual(page.group_table.rowCount(), 7)
            self.assertEqual(page.group_filter.count(), 8)
            self.assertEqual(
                page.summary_label.text(),
                "258 resources  •  7 families  •  125 packages",
            )
            self.assertEqual(
                tuple(
                    page.group_table.item(row, 1).text()
                    for row in range(page.group_table.rowCount())
                ),
                ("235", "4", "4", "6", "3", "4", "2"),
            )
            self.assertIn("co-location only", page.package_note.text())
            self.assertIn("Exact asset IDs", page.package_note.text())
            self.assertEqual(len(page.browser._matches), 258)
            self.assertEqual(page.browser.result_count.text(), "258 assets")
            self.assertIn("ID: apf:outer:", page.browser.detail_metadata.text())
        finally:
            page.deleteLater()
            self.application.processEvents()

    def test_family_filter_uses_reviewed_asset_ids_not_name_guessing(self) -> None:
        page = self._page()
        try:
            index = page.group_filter.findData(FieldArtKind.FIELD_SCENE.value)
            self.assertGreater(index, 0)
            page.group_filter.setCurrentIndex(index)
            self.application.processEvents()

            self.assertEqual(len(page.browser._matches), 4)
            self.assertEqual(
                {asset.name for asset in page.browser._matches}, {"field"}
            )
            self.assertEqual(
                {asset.type_name for asset in page.browser._matches}, {"SCNE"}
            )
            self.assertEqual(page.browser.result_count.text(), "4 assets")
            self.assertIn("4 records across 4 archive packages", page.group_note.text())
        finally:
            page.deleteLater()
            self.application.processEvents()

    def _assert_replace_locked_explainable(self, page) -> None:
        """Lock is honest: buttons stay clickable, but disableReason blocks write."""

        self.assertFalse(page.browser.replace_button.isHidden())
        self.assertFalse(page.browser.revert_button.isHidden())
        # Never silent-gray: enabled + tooltip + disableReason teach the wall.
        self.assertTrue(page.browser.replace_button.isEnabled())
        self.assertTrue(page.browser.revert_button.isEnabled())
        self.assertEqual(page.browser.replace_button.text(), "Replace locked")
        self.assertEqual(page.browser.revert_button.text(), "Revert locked")
        tip = page.browser.replace_button.toolTip()
        reason = str(page.browser.replace_button.property("disableReason") or "")
        self.assertTrue(tip.strip(), "locked replace must explain itself")
        self.assertTrue(reason.strip(), "disableReason required for click-to-explain")

    def test_replace_and_revert_are_visible_but_explicitly_locked(self) -> None:
        page = self._page()
        try:
            self._assert_replace_locked_explainable(page)
            self.assertIn("runtime field material", page.browser.detail_notes.text())
            self.assertIn(
                "browse and export-only", page.browser.replace_button.toolTip()
            )
            self.assertIn("no bounded writer", page.browser.replace_button.toolTip())
        finally:
            page.deleteLater()
            self.application.processEvents()

    def test_deferred_families_stay_locked_in_the_inventory(self) -> None:
        page = self._page()
        try:
            for kind in (
                FieldArtKind.FIELD_RADIANCE,
                FieldArtKind.DIVOT_WEATHER_TEXTURE,
                FieldArtKind.PRACTICE_SCENE,
                FieldArtKind.PENALTY_ANIMATION,
            ):
                index = page.group_filter.findData(kind.value)
                self.assertGreater(index, 0)
                page.group_filter.setCurrentIndex(index)
                self.application.processEvents()
                self._assert_replace_locked_explainable(page)
        finally:
            page.deleteLater()
            self.application.processEvents()

    def test_semantic_contract_drift_fails_closed_but_raw_rows_stay_visible(self) -> None:
        catalog = _synthetic_catalog()
        drifted = replace(catalog, assets=catalog.assets[:-1])
        page = self._page(drifted)
        try:
            self.assertIsNone(page.inventory)
            self.assertEqual(page.group_table.rowCount(), 0)
            self.assertIn("Semantic map needs review", page.summary_label.text())
            self.assertEqual(len(page.browser._matches), 257)
            self._assert_replace_locked_explainable(page)
        finally:
            page.deleteLater()
            self.application.processEvents()

    def test_unloaded_state_preserves_the_action_lock(self) -> None:
        page = self._page(ready=False)
        try:
            summary = page.summary_label.text()
            self.assertIn("Load", summary)
            self.assertIn("Field Art", summary)
            # Teachable empty state may include next-step stock-NFL inventory copy.
            self.assertTrue(
                summary.startswith("Load a game to map Field Art")
                or summary.startswith("Load your APF game to map Field Art"),
                msg=summary,
            )
            self.assertEqual(page.browser.table.rowCount(), 0)
            self._assert_replace_locked_explainable(page)
        finally:
            page.deleteLater()
            self.application.processEvents()

    def test_editor_offers_exactly_the_offline_proved_slots(self) -> None:
        page = self._page()
        try:
            offered = tuple(
                target.name for target in FIELD_ART_COVERED_TARGETS
            )
            self.assertEqual(
                offered,
                (
                    "endzone_l0",
                    "endzone_l1",
                    "pc_field_goal",
                    "Field_Pass_text",
                    "Stride_number_field",
                    "divots",
                ),
            )
            self.assertEqual(page.editor.slot.count(), len(offered))
            # The deferred codecs and the non-texture rows are never offered.
            for deferred in (
                "field_radiance",
                "divot_GrassRain",
                "divot_GrassSnow",
                "divot_GrassDry",
                "divotb1",
                "tc2_footballField",
                "penalty_onthe_field",
            ):
                self.assertNotIn(deferred, offered)
            # Each offered slot is pinned to one exact archive identity.
            self.assertEqual(
                tuple(target.key for target in FIELD_ART_COVERED_TARGETS),
                ((6, 0), (6, 1), (659, 18), (659, 23), (659, 252), (53, 0)),
            )
        finally:
            page.deleteLater()
            self.application.processEvents()

    def test_editor_replace_is_unlocked_but_build_waits_for_a_staged_png(self) -> None:
        page = self._page()
        try:
            self.assertTrue(page.editor.replace_button.isEnabled())
            self.assertTrue(page.editor.export_button.isEnabled())
            self.assertEqual(page.editor.replace_button.text(), "Replace PNG…")
            # Never silent-gray: Build/Revert stay clickable until staged.
            self.assertTrue(page.editor.build_button.isEnabled())
            self.assertTrue(page.editor.revert_button.isEnabled())
            self.assertTrue(
                str(page.editor.build_button.property("disableReason") or "").strip()
            )
            self.assertTrue(
                str(page.editor.revert_button.property("disableReason") or "").strip()
            )
            self.assertIn("not proved without a Xenia capture", page.editor.description.text())
        finally:
            page.deleteLater()
            self.application.processEvents()

    def test_editor_is_read_only_safe_until_a_game_is_loaded(self) -> None:
        page = self._page(ready=False)
        try:
            # Never silent-gray when unloaded: enabled + disableReason teaches Load.
            self.assertTrue(page.editor.replace_button.isEnabled())
            self.assertTrue(page.editor.export_button.isEnabled())
            self.assertTrue(page.editor.build_button.isEnabled())
            self.assertTrue(page.editor.revert_button.isEnabled())
            for button in (
                page.editor.replace_button,
                page.editor.export_button,
                page.editor.build_button,
            ):
                reason = str(button.property("disableReason") or "")
                self.assertIn("Load", reason)
            self.assertEqual(page.editor.status.text(), "○ Not loaded")
        finally:
            page.deleteLater()
            self.application.processEvents()

    def test_editor_stages_an_exact_size_png_and_revert_clears_it(self) -> None:
        page = self._page()
        try:
            target_index = next(
                index
                for index, target in enumerate(FIELD_ART_COVERED_TARGETS)
                if target.name == "divots"
            )
            page.editor.slot.setCurrentIndex(target_index)
            self.application.processEvents()
            target = page.editor.current_target()
            self.assertEqual((target.width, target.height), (64, 64))

            with tempfile.TemporaryDirectory() as directory:
                staged = Path(directory) / "divots.png"
                _write_png(staged, target.width, target.height)
                page.editor._stage_path(staged)
                self.application.processEvents()

                self.assertEqual(page.editor.staged_path(target), staged)
                self.assertTrue(page.editor.build_button.isEnabled())
                self.assertTrue(page.editor.revert_button.isEnabled())
                self.assertEqual(page.editor.status.text(), "● Staged")

                page.editor._revert()
                self.application.processEvents()
                self.assertIsNone(page.editor.staged_path(target))
                self.assertTrue(page.editor.build_button.isEnabled())
                self.assertTrue(page.editor.revert_button.isEnabled())
                self.assertTrue(
                    str(page.editor.build_button.property("disableReason") or "").strip()
                )
                self.assertTrue(
                    str(page.editor.revert_button.property("disableReason") or "").strip()
                )
        finally:
            page.deleteLater()
            self.application.processEvents()

    def test_editor_build_dispatches_the_proved_writer_for_the_selected_slot(
        self,
    ) -> None:
        runner = _RecordingRunner()
        page = self._page(runner=runner)
        try:
            target_index = next(
                index
                for index, target in enumerate(FIELD_ART_COVERED_TARGETS)
                if target.name == "pc_field_goal"
            )
            page.editor.slot.setCurrentIndex(target_index)
            self.application.processEvents()
            target = page.editor.current_target()

            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                staged = _write_png(root / "edit.png", target.width, target.height)
                page.editor._stage_path(staged)
                out_volume = root / "out" / "0A"

                with mock.patch.object(
                    gui.QFileDialog,
                    "getSaveFileName",
                    return_value=(str(out_volume), ""),
                ), mock.patch.object(
                    gui.QMessageBox, "question", return_value=gui.QMessageBox.Yes
                ):
                    page.editor._build_copied_volume()

                operation = runner.operation_for("Building copied 0A")
                with mock.patch("subprocess.run") as run:
                    run.return_value = _CompletedProcess(0)
                    operation(lambda *_args: None)

                run.assert_called_once()
                argv = run.call_args.args[0]
                self.assertTrue(argv[1].endswith("apf_field_art_patch.py"))
                self.assertEqual(argv[argv.index("--entry-index") + 1], "659")
                self.assertEqual(argv[argv.index("--file-index") + 1], "18")
                self.assertEqual(argv[argv.index("--png") + 1], str(staged))
                self.assertEqual(
                    argv[argv.index("--output-volume") + 1], str(out_volume)
                )
                # The panel hands the writer ``str(Path(source.index_0a))``, so
                # the argv carries the host OS's own spelling of that same
                # volume ("/nonexistent/APF/0A" on POSIX,
                # "\nonexistent\APF\0A" on Windows).  Compare against the same
                # construction rather than the POSIX literal: still pins the
                # exact read-only source the writer is pointed at, portably.
                self.assertEqual(
                    argv[argv.index("--index") + 1],
                    str(Path(page.facade.source.index_0a)),
                )
                self.assertIn("--manifest", argv)
        finally:
            page.deleteLater()
            self.application.processEvents()

    def test_editor_build_fails_closed_when_the_writer_refuses(self) -> None:
        runner = _RecordingRunner()
        page = self._page(runner=runner)
        try:
            target = page.editor.current_target()
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                staged = _write_png(root / "edit.png", target.width, target.height)
                page.editor._stage_path(staged)

                with mock.patch.object(
                    gui.QFileDialog,
                    "getSaveFileName",
                    return_value=(str(root / "out" / "0A"), ""),
                ), mock.patch.object(
                    gui.QMessageBox, "question", return_value=gui.QMessageBox.Yes
                ):
                    page.editor._build_copied_volume()

                operation = runner.operation_for("Building copied 0A")
                with mock.patch("subprocess.run") as run:
                    run.return_value = _CompletedProcess(
                        1, stderr="error: base hash is not the pinned retail data"
                    )
                    with self.assertRaises(RuntimeError) as raised:
                        operation(lambda *_args: None)
                self.assertIn("pinned retail data", str(raised.exception))
        finally:
            page.deleteLater()
            self.application.processEvents()

    def test_editor_offers_to_resize_a_png_that_is_not_the_base_size(self) -> None:
        """A wrong size is an offer now, not a dead end.

        The writer still demands the exact base size and always will. Refusing
        the user's file instead of fitting it was the app's choice, and it
        stopped people before they started -- so the prompt is the behaviour
        under test, along with declining it leaving nothing staged.
        """
        page = self._page()
        try:
            target_index = next(
                index
                for index, target in enumerate(FIELD_ART_COVERED_TARGETS)
                if target.name == "divots"
            )
            page.editor.slot.setCurrentIndex(target_index)
            self.application.processEvents()
            target = page.editor.current_target()

            with tempfile.TemporaryDirectory() as directory:
                wrong = Path(directory) / "wrong.png"
                _write_png(wrong, target.width // 2, target.height)

                # Declining leaves the slot exactly as it was.
                with mock.patch.object(
                    gui.QMessageBox, "question",
                    return_value=gui.QMessageBox.Cancel,
                ) as asked:
                    page.editor._stage_path(wrong)
                self.application.processEvents()
                asked.assert_called_once()
                self.assertIn("Resize this image?", asked.call_args.args[1])
                self.assertIsNone(page.editor.staged_path(target))
                self.assertTrue(page.editor.build_button.isEnabled())
                self.assertTrue(
                    str(page.editor.build_button.property("disableReason") or "").strip()
                )

                # Accepting stages a copy at exactly the base size.
                with mock.patch.object(
                    gui.QMessageBox, "question",
                    return_value=gui.QMessageBox.Yes,
                ), mock.patch.object(
                    gui.QMessageBox, "information", return_value=None
                ):
                    page.editor._stage_path(wrong)
                self.application.processEvents()
                staged = page.editor.staged_path(target)
                self.assertIsNotNone(staged)
                with Image.open(staged) as fitted:
                    self.assertEqual(
                        fitted.size, (target.width, target.height)
                    )
        finally:
            page.deleteLater()
            self.application.processEvents()


if __name__ == "__main__":
    unittest.main()
