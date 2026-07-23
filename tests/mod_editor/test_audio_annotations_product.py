"""Headless product contracts for 2K5 Audio cue labels and notes."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import zipfile


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtGui import QTextDocument  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.core.errors import ValidationError  # noqa: E402
from mod_editor.core.nfl2k5_audio_catalog import (  # noqa: E402
    Nfl2k5AudioService,
    PLAYABLE_AUDIO_SCOPE_ID,
)
from mod_editor.gui.audio_panel_qt import AudioPanel  # noqa: E402
from mod_editor.studio.audio_annotations import AudioCueAnnotation  # noqa: E402
from mod_editor.studio.facade import Nfl2k5StudioFacade  # noqa: E402
from mod_editor.studio.session import StudioSession  # noqa: E402
from tests.mod_editor.test_nfl2k5_audio_catalog import AudioFixture  # noqa: E402


@dataclass(frozen=True)
class _SyntheticUniformAsset:
    asset_id: str = "nfl2k5.uniform.synthetic"
    label: str = "Synthetic uniform"


class _SyntheticUniformCatalog:
    def get_asset(self, _asset_id: str) -> _SyntheticUniformAsset:
        return _SyntheticUniformAsset()


class _NoopVisualIO:
    def __init__(self, _cache: object) -> None:
        pass


class AudioAnnotationProductTests(unittest.TestCase):
    """Exercise the user-visible contracts through real session/facade objects."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="2k5-audio-annotation-product-"
        )
        self.root = Path(self.temporary.name)
        source_root = self.root / "source"
        source_root.mkdir()
        self.fixture = AudioFixture(source_root)
        self.catalog = self.fixture.catalog()
        self.service = Nfl2k5AudioService(self.fixture.cache, self.catalog)
        with patch(
            "mod_editor.studio.session.Nfl2k5ProductVisualIO", _NoopVisualIO
        ):
            self.session = StudioSession(
                self.fixture.cache,
                _SyntheticUniformCatalog(),
                root=self.root / "sessions",
                session_id="product",
            )
        self.session.attach_audio_service(self.service)
        self.facade = Nfl2k5StudioFacade(
            uniform_catalog=_SyntheticUniformCatalog(),  # type: ignore[arg-type]
            visual_catalog=_SyntheticUniformCatalog(),  # type: ignore[arg-type]
        )
        self.facade._cache = self.fixture.cache
        self.facade._session = self.session
        self.facade._audio_catalog = self.catalog
        self.facade._audio_service = self.service
        self.facade._audio_origin_preparation = SimpleNamespace(
            is_ready=lambda _cache: True
        )
        self.progress: list[tuple[str, int, int]] = []

    def tearDown(self) -> None:
        self.application.processEvents()
        self.temporary.cleanup()

    def _progress(self, stage: str, completed: int, total: int) -> None:
        self.progress.append((stage, completed, total))

    @staticmethod
    def _asset_ids(page: object) -> tuple[str, ...]:
        return tuple(asset.asset_id for asset in page.assets)  # type: ignore[attr-defined]

    @staticmethod
    def _table_row_for(panel: AudioPanel, asset_id: str) -> int:
        for row in range(panel.table.rowCount()):
            item = panel.table.item(row, 0)
            if item is not None and item.data(Qt.UserRole) == asset_id:
                return row
        raise AssertionError(f"Audio table does not contain {asset_id}")

    def test_facade_searches_title_note_and_mixed_terms_without_labeling_aliases(
        self,
    ) -> None:
        first, related_alias = self.catalog.assets
        self.assertEqual(first.name, related_alias.name)
        self.assertEqual(first.alias_status, related_alias.alias_status)

        result = self.facade.set_audio_annotation(
            first.asset_id,
            "Overtime victory horn",
            "Verified while returning from the pause menu.",
            self._progress,
        )
        self.assertTrue(result.changed)
        self.assertEqual(
            self.facade.audio_annotation(first.asset_id),
            AudioCueAnnotation(
                first.asset_id,
                "Overtime victory horn",
                "Verified while returning from the pause menu.",
            ),
        )
        self.assertIsNone(self.facade.audio_annotation(related_alias.asset_id))

        common = {
            "status": None,
            "offset": 0,
            "limit": 50,
            "scope": "standalone",
        }
        self.assertEqual(
            self._asset_ids(self.facade.browse_audio(search="victory", **common)),
            (first.asset_id,),
        )
        self.assertEqual(
            self._asset_ids(self.facade.browse_audio(search="pause", **common)),
            (first.asset_id,),
        )
        self.assertEqual(
            self._asset_ids(
                self.facade.browse_audio(search="menu-back verified", **common)
            ),
            (first.asset_id,),
        )
        self.assertEqual(
            self._asset_ids(
                self.facade.browse_audio(
                    search="", labeled_only=True, **common
                )
            ),
            (first.asset_id,),
        )
        self.assertEqual(
            self.facade.browse_audio(
                search="victory missing-term", **common
            ).total,
            0,
        )

    def test_matching_and_shortlist_exports_carry_custom_discovery_metadata(
        self,
    ) -> None:
        asset = self.catalog.assets[0]
        self.facade.set_audio_annotation(
            asset.asset_id,
            "Custom Victory Cue",
            "Confirmed during a fourth-quarter comeback.",
            self._progress,
        )
        outputs = (
            self.facade.export_audio_bundle(
                search="victory",
                status=None,
                scope="standalone",
                family=None,
                labeled_only=True,
                destination=self.root / "matching.zip",
                output_format="wav",
                bundle_name="Labeled discoveries",
                progress=self._progress,
            ),
            self.facade.export_audio_selection(
                (asset.asset_id,),
                self.root / "shortlist.zip",
                bundle_name="My cue shortlist",
                progress=self._progress,
            ),
        )
        for output in outputs:
            with self.subTest(output=output.name), zipfile.ZipFile(output) as archive:
                manifest = json.loads(archive.read("manifest.json"))
                record = manifest["records"][0]
                self.assertEqual(record["stable_id"], asset.asset_id)
                self.assertEqual(record["display_name"], "Custom Victory Cue")
                self.assertEqual(
                    record["metadata"]["custom_title"], "Custom Victory Cue"
                )
                self.assertEqual(
                    record["metadata"]["annotation_note"],
                    "Confirmed during a fourth-quarter comeback.",
                )
                self.assertEqual(
                    record["metadata"]["game_catalog_name"], asset.name
                )
                playlist = archive.read("playlist.m3u8").decode("utf-8")
                self.assertIn("Custom Victory Cue", playlist)

    def test_audio_panel_labels_only_playable_rows_and_commits_after_worker_success(
        self,
    ) -> None:
        first = self.catalog.assets[0]
        captured_tasks: list[object] = []
        changed_signals: list[str] = []
        with patch("mod_editor.gui.audio_panel_qt.QMessageBox.warning"):
            panel = AudioPanel(self.facade, page_size=4)
            panel.audio_annotation_changed.connect(changed_signals.append)
            try:
                self.application.processEvents()
                self.assertEqual(panel.scope_filter.currentData(), PLAYABLE_AUDIO_SCOPE_ID)
                self.assertFalse(panel.labeled_only_filter.isHidden())
                self.assertTrue(panel.annotation_title_edit.isEnabled())
                self.assertTrue(panel.annotation_note_edit.isEnabled())

                panel.scope_filter.setCurrentIndex(
                    panel.scope_filter.findData("streaming")
                )
                self.application.processEvents()
                self.assertEqual(panel.selected_asset_id, self.catalog.streaming_banks[0].asset_id)
                self.assertFalse(panel.annotation_title_edit.isEnabled())
                self.assertFalse(panel.annotation_note_edit.isEnabled())
                self.assertFalse(panel.save_annotation_button.isEnabled())
                self.assertFalse(panel.clear_annotation_button.isEnabled())
                self.assertFalse(panel.labeled_only_filter.isEnabled())

                panel.scope_filter.setCurrentIndex(
                    panel.scope_filter.findData("standalone")
                )
                self.application.processEvents()
                self.assertEqual(panel.selected_asset_id, first.asset_id)
                self.assertTrue(panel.annotation_title_edit.isEnabled())
                self.assertTrue(panel.labeled_only_filter.isEnabled())

                panel._pool = SimpleNamespace(  # type: ignore[assignment]
                    start=lambda task: captured_tasks.append(task)
                )
                panel.annotation_title_edit.setText("Sideline victory horn")
                panel.annotation_note_edit.setPlainText("Confirmed after overtime.")
                self.assertTrue(panel.save_annotation_button.isEnabled())
                panel.save_annotation_button.click()

                self.assertTrue(panel.operation_in_progress)
                self.assertEqual(len(captured_tasks), 1)
                self.assertEqual(changed_signals, [])
                self.assertIsNone(self.session.audio_annotation(first.asset_id))

                captured_tasks.pop(0).run()  # type: ignore[attr-defined]
                self.application.processEvents()
                self.assertFalse(panel.operation_in_progress)
                self.assertEqual(changed_signals, [first.asset_id])
                self.assertEqual(
                    self.session.audio_annotation(first.asset_id),
                    AudioCueAnnotation(
                        first.asset_id,
                        "Sideline victory horn",
                        "Confirmed after overtime.",
                    ),
                )
                self.assertNotIn(first.asset_id, panel._annotation_drafts)

                row = self._table_row_for(panel, first.asset_id)
                title_item = panel.table.item(row, 0)
                self.assertEqual(title_item.text(), "✎ Sideline victory horn")
                self.assertIn(
                    f"Game/catalog label: {first.name}", title_item.toolTip()
                )
                self.assertIn(first.asset_id, title_item.toolTip())
                self.assertIn(
                    f"Game/catalog label: {first.name}", panel.metadata_label.text()
                )
                self.assertIn(first.asset_id, panel.metadata_label.text())

                panel.labeled_only_filter.setChecked(True)
                self.application.processEvents()
                self.assertEqual(panel.page.total, 1)
                self.assertEqual(panel.selected_asset_id, first.asset_id)
                self.assertTrue(panel.clear_annotation_button.isEnabled())
                panel.clear_annotation_button.click()

                self.assertTrue(panel.operation_in_progress)
                self.assertEqual(len(captured_tasks), 1)
                self.assertEqual(changed_signals, [first.asset_id])
                self.assertIsNotNone(self.session.audio_annotation(first.asset_id))

                captured_tasks.pop(0).run()  # type: ignore[attr-defined]
                self.application.processEvents()
                self.assertFalse(panel.operation_in_progress)
                self.assertEqual(changed_signals, [first.asset_id, first.asset_id])
                self.assertIsNone(self.session.audio_annotation(first.asset_id))
                self.assertEqual(panel.page.total, 0)
                self.assertEqual(panel.table.rowCount(), 0)
            finally:
                panel.deleteLater()
                self.application.processEvents()

    def test_untrusted_markup_is_literal_and_unsaved_drafts_survive_browsing(
        self,
    ) -> None:
        first = self.catalog.assets[0]
        hostile_title = '<img src="file:///tmp/annotation-probe"> <b>literal</b>'
        hostile_note = '<b>not bold</b> & "not markup"'
        self.facade.set_audio_annotation(
            first.asset_id, hostile_title, hostile_note, self._progress
        )
        with patch("mod_editor.gui.audio_panel_qt.QMessageBox.warning"):
            panel = AudioPanel(self.facade, page_size=2)
            try:
                self.application.processEvents()
                self.assertEqual(panel.selected_asset_id, first.asset_id)
                self.assertEqual(panel.asset_title.textFormat(), Qt.PlainText)
                self.assertEqual(panel.asset_title.text(), hostile_title)
                title_item = panel.table.item(0, 0)
                tooltip = title_item.toolTip()
                self.assertIn("&lt;img", tooltip)
                self.assertIn("&lt;b&gt;not bold&lt;/b&gt;", tooltip)
                self.assertNotIn("<img", tooltip)
                self.assertNotIn("<b>not bold</b>", tooltip)
                tooltip_document = QTextDocument()
                tooltip_document.setHtml(tooltip)
                self.assertIn(hostile_title, tooltip_document.toPlainText())
                self.assertIn(hostile_note, tooltip_document.toPlainText())

                draft_title = "Unsaved sideline discovery"
                draft_note = "Keep this note while I compare nearby cues."
                panel.annotation_title_edit.setText(draft_title)
                panel.annotation_note_edit.setPlainText(draft_note)
                self.assertIn(first.asset_id, panel._annotation_drafts)
                self.assertIn("Unsaved draft retained", panel.annotation_help.text())

                panel.table.selectRow(1)
                self.application.processEvents()
                self.assertNotEqual(panel.selected_asset_id, first.asset_id)
                panel.table.selectRow(0)
                self.application.processEvents()
                self.assertEqual(panel.selected_asset_id, first.asset_id)
                self.assertEqual(panel.annotation_title_edit.text(), draft_title)
                self.assertEqual(
                    panel.annotation_note_edit.toPlainText(), draft_note
                )

                panel._next_page()
                self.application.processEvents()
                self.assertNotEqual(panel.selected_asset_id, first.asset_id)
                panel._previous_page()
                self.application.processEvents()
                self.assertEqual(panel.selected_asset_id, first.asset_id)
                self.assertEqual(panel.annotation_title_edit.text(), draft_title)
                self.assertEqual(
                    panel.annotation_note_edit.toPlainText(), draft_note
                )

                panel.scope_filter.setCurrentIndex(
                    panel.scope_filter.findData("streaming")
                )
                self.application.processEvents()
                panel.scope_filter.setCurrentIndex(
                    panel.scope_filter.findData("standalone")
                )
                self.application.processEvents()
                self.assertEqual(panel.selected_asset_id, first.asset_id)
                self.assertEqual(panel.annotation_title_edit.text(), draft_title)
                self.assertEqual(
                    panel.annotation_note_edit.toPlainText(), draft_note
                )
                self.assertEqual(
                    self.session.audio_annotation(first.asset_id),
                    AudioCueAnnotation(first.asset_id, hostile_title, hostile_note),
                )
            finally:
                panel.deleteLater()
                self.application.processEvents()

    def test_annotation_only_project_is_saveable_metadata_but_not_a_build_edit(
        self,
    ) -> None:
        asset = self.catalog.streaming_ranges[0]
        self.facade.set_audio_annotation(
            asset.asset_id,
            "Kickoff crowd bed",
            "Keep this logical range separate from its physical-slot neighbors.",
            self._progress,
        )

        self.assertEqual(self.facade.project_metadata_count, 1)
        self.assertEqual(self.facade.modified_count, 0)
        self.assertEqual(tuple(self.facade.modified_asset_ids), ())
        self.assertEqual(self.session.modified_count, 0)
        self.assertEqual(self.session.modified_asset_ids, frozenset())
        with self.assertRaisesRegex(ValidationError, "Replace at least one asset"):
            self.session.canonical_document()

        destination = self.root / "cue-labels-only.2k5mod"
        saved = self.facade.save_project(destination, self._progress)
        self.assertEqual(saved.output, destination.resolve())
        with zipfile.ZipFile(destination) as archive:
            members = sorted(archive.namelist())
            self.assertEqual(
                members,
                ["audio-annotations.json", "project.json"],
            )
            manifest = json.loads(archive.read("project.json"))
            annotations = json.loads(archive.read("audio-annotations.json"))
        self.assertEqual(manifest["audio_annotations"]["count"], 1)
        self.assertEqual(annotations["annotations"][0]["cue_id"], asset.asset_id)
        self.assertNotIn("audio_edits", manifest)
        self.assertNotIn("edits/", " ".join(members))


if __name__ == "__main__":
    unittest.main()
