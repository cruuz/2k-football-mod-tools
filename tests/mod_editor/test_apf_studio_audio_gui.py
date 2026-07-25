from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402
from PyQt5 import sip  # noqa: E402

from mod_editor.apf_studio.gui import (  # noqa: E402
    InspectorCategoryPage,
    InspectorBrowser,
    _audio_player_command,
)
from mod_editor.apf_studio.inspectors import (  # noqa: E402
    ExportIdentity,
    PagedModel,
    _row,
)
from mod_editor.apf_studio.models import (  # noqa: E402
    ApfCategory,
    ExternalAudioBankIdentity,
    ExternalAudioBankOwner,
)


class ApfAudioGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.application.quit()
        sip.delete(cls.application)
        cls.application = None

    @staticmethod
    def _playable_row(
        index: int,
        *,
        source_id: str = "audo:standalone",
        source_label: str = "Standalone AUDO",
    ) -> object:
        identity = ExportIdentity("audo", 5, index, None, f"sound-{index:03d}")
        return _row(
            f"audo:{index}",
            "audo",
            f"sound_{index:03d}",
            "AUDIO",
            {
                "outer_table_index": 5,
                "inner_file_index": index,
                "audio_source_id": source_id,
                "audio_source_label": source_label,
                "role_id": "ui_menu_sfx",
                "role_label": "UI & Menu SFX",
                "audio_format": "XMA1",
                "sample_rate": 22_050,
                "derived_channel_count": 1,
                "duration_seconds": 1.0,
            },
            export_identity=identity,
        )

    @staticmethod
    def _pack_row(index: int, *, role_id: str = "ui_menu_sfx") -> object:
        """One product-shaped AUDO row suitable for replacement-pack actions."""

        identity = ExportIdentity("audo", 5, index, None, f"sound-{index:03d}")
        return _row(
            f"apf:audio:audo:5:{index}",
            "audo",
            f"sound_{index:03d}",
            "AUDIO",
            {
                "outer_table_index": 5,
                "inner_file_index": index,
                "audio_source_id": "audo:standalone",
                "audio_source_label": "Standalone AUDO",
                "role_id": role_id,
                "role_label": (
                    "UI & Menu SFX" if role_id == "ui_menu_sfx" else "Other Audio"
                ),
                "audio_format": "XMA1",
                "sample_rate": 22_050,
                "derived_channel_count": 1,
                "duration_seconds": 1.0,
                "declared_sample_count": 21_604,
                "encoded_size": 0x1800,
                "packet_count": 3,
            },
            export_identity=identity,
        )

    @staticmethod
    def _soundtrack_rows() -> tuple[object, ...]:
        rows: list[object] = []
        # Deliberately reverse and interleave the physical model order.  The
        # album contract is source substream order, never incidental catalog
        # insertion order.
        for index in reversed(range(15)):
            duration = 120.0 + index
            rows.append(
                _row(
                    f"apf:audio:ausb:9:3:substream:{index}",
                    "ausb_substream",
                    f"Soundtrack Track {index + 1:02d} · Mono companion",
                    "XMA packets",
                    {
                        "outer_table_index": 9,
                        "inner_file_index": 3,
                        "substream_index": index,
                        "bank_name": "jukebox22",
                        "audio_source_id": "ausb:9:3",
                        "audio_source_label": "jukebox22 · O9/I3",
                        "role_id": "soundtrack_music",
                        "role_label": "Soundtrack & Music",
                        "sample_rate": 22_050,
                        "derived_channel_count": 1,
                        "duration_seconds_candidate": duration,
                        "logical_track_number": index + 1,
                        "paired_bank_name": "jukeboxmusic",
                        "track_title_status": "Unknown; artist and title are not guessed.",
                    },
                    export_identity=ExportIdentity(
                        "ausb_substream", 9, 3, index, f"jukebox22-{index:05d}"
                    ),
                )
            )
            rows.append(
                _row(
                    f"apf:audio:ausb:8:2:substream:{index}",
                    "ausb_substream",
                    f"Soundtrack Track {index + 1:02d} · Full stereo",
                    "XMA packets",
                    {
                        "outer_table_index": 8,
                        "inner_file_index": 2,
                        "substream_index": index,
                        "bank_name": "jukeboxmusic",
                        "audio_source_id": "ausb:8:2",
                        "audio_source_label": "jukeboxmusic · O8/I2",
                        "role_id": "soundtrack_music",
                        "role_label": "Soundtrack & Music",
                        "sample_rate": 48_000,
                        "derived_channel_count": 2,
                        "duration_seconds_candidate": duration,
                        "logical_track_number": index + 1,
                        "paired_bank_name": "jukebox22",
                        "track_title_status": "Unknown; artist and title are not guessed.",
                    },
                    export_identity=ExportIdentity(
                        "ausb_substream", 8, 2, index, f"jukeboxmusic-{index:05d}"
                    ),
                )
            )
        return tuple(rows)

    def test_audio_browser_exposes_product_controls_without_a_display(self) -> None:
        audo_identity = ExportIdentity("audo", 5, 1, None, "menu-back")
        bank_identities = tuple(
            ExportIdentity("ausb_substream", 8, 2, index, f"jukebox-{index}")
            for index in range(2)
        )
        common_bank = {
            "outer_table_index": 8,
            "inner_file_index": 2,
            "bank_name": "jukeboxmusic",
            "audio_source_id": "ausb:8:2",
            "audio_source_label": "jukeboxmusic · O8/I2",
            "role_id": "soundtrack_music",
            "role_label": "Soundtrack & Music",
            "audio_format": "XMA1",
            "sample_rate": 48_000,
            "derived_channel_count": 2,
        }
        model = PagedModel(
            (
                _row(
                    "audo:1",
                    "audo",
                    "menu_back",
                    "AUDIO",
                    {
                        "outer_table_index": 5,
                        "inner_file_index": 1,
                        "audio_source_id": "audo:standalone",
                        "audio_source_label": "Standalone AUDO",
                        "role_id": "ui_menu_sfx",
                        "role_label": "UI & Menu SFX",
                        "audio_format": "XMA1",
                        "sample_rate": 22_050,
                        "derived_channel_count": 1,
                        "duration_seconds": 1.0,
                    },
                    export_identity=audo_identity,
                ),
                _row(
                    "bank:2",
                    "ausb_bank",
                    "jukeboxmusic",
                    "2 substreams",
                    {
                        **common_bank,
                        "name": "jukeboxmusic",
                        "substream_count": 2,
                    },
                ),
                *(
                    _row(
                        f"bank:2:{index}",
                        "ausb_substream",
                        f"Soundtrack Track {index + 1:02d} · Full stereo",
                        "XMA packets",
                        {
                            **common_bank,
                            "substream_index": index,
                            "duration_seconds_candidate": 100.0 + index,
                        },
                        export_identity=identity,
                    )
                    for index, identity in enumerate(bank_identities)
                ),
            )
        )
        browser = InspectorBrowser(
            "Complete audio",
            object(),  # type: ignore[arg-type]
            lambda *_args, **_kwargs: None,
            audio_mode=True,
        )
        try:
            browser.set_model(model, "fixture")
            self.assertEqual(browser.table.columnCount(), 6)
            self.assertEqual(browser.table.horizontalHeaderItem(0).text(), "Sound")
            self.assertEqual(browser.role_filter.count(), 3)
            self.assertEqual(browser.source_filter.count(), 3)
            self.assertEqual(
                browser.source_filter.itemData(1), "audo:standalone"
            )
            self.assertEqual(browser.source_filter.itemData(2), "ausb:8:2")
            self.assertIn("O8/I2", browser.source_filter.itemText(2))
            self.assertTrue(browser.replace_audio_button.isEnabled())
            self.assertEqual(browser.replace_audio_button.text(), "Replace with XMA1…")
            self.assertEqual(browser.replace_audio_button.objectName(), "primaryButton")
            self.assertIn("XMA1", browser.replace_audio_button.toolTip())
            self.assertIn("22,050 Hz", browser.replace_audio_button.toolTip())
            self.assertFalse(browser.revert_audio_button.isEnabled())
            self.assertIn("PCM authoring bridge", browser.audio_replace_note.text())
            self.assertTrue(browser.play_audio_button.isEnabled())
            self.assertTrue(browser.export_matching_button.isEnabled())
            self.assertIn("(3)", browser.export_matching_button.text())
            self.assertTrue(browser.shortlist_toggle_button.isEnabled())
            self.assertEqual(browser.shortlist_count.text(), "Selected 0 / 256")
            self.assertFalse(browser.export_shortlist_button.isEnabled())
            self.assertTrue(browser.shortlist_matching_button.isEnabled())
            self.assertEqual(
                browser.shortlist_matching_button.text(),
                "Add all matching (3)",
            )
            self.assertEqual(
                browser.shortlist_matching_button.accessibleName(),
                "Add all 3 matching playable sounds to the audio shortlist",
            )
            self.assertFalse(browser.soundtrack_album_button.isEnabled())
            detail_layout = browser.export_matching_button.parentWidget().layout()
            self.assertGreaterEqual(
                detail_layout.indexOf(browser.export_matching_button), 0
            )
            self.assertGreaterEqual(
                detail_layout.indexOf(browser.shortlist_matching_button), 0
            )
            browser.table.selectRow(1)
            self.application.processEvents()
            self.assertFalse(browser.replace_audio_button.isEnabled())
            self.assertTrue(browser.export_bank_button.isVisibleTo(browser))
            self.assertEqual(len(browser._selected_bank_identities()), 2)
            browser.kind_filter.setCurrentIndex(
                browser.kind_filter.findData("ausb_bank")
            )
            browser.refresh()
            self.assertFalse(browser.export_matching_button.isEnabled())
            self.assertIn("No playable", browser.export_matching_button.toolTip())
            self.assertFalse(browser.shortlist_matching_button.isEnabled())
            browser.kind_filter.setCurrentIndex(
                browser.kind_filter.findData("ausb_substream")
            )
            browser.refresh()
            self.assertTrue(browser.export_matching_button.isEnabled())
            self.assertIn("(2)", browser.export_matching_button.text())
            browser.kind_filter.setCurrentIndex(0)
            browser.source_filter.setCurrentIndex(
                browser.source_filter.findData("ausb:8:2")
            )
            browser.refresh()
            self.assertEqual(browser.table.rowCount(), 3)
            self.assertIn("(2)", browser.export_matching_button.text())
            browser.source_filter.setCurrentIndex(
                browser.source_filter.findData("audo:standalone")
            )
            browser.refresh()
            self.assertEqual(browser.table.rowCount(), 1)
            self.assertIn("(1)", browser.export_matching_button.text())
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_external_bank_is_named_raw_export_only_and_never_playable(self) -> None:
        owner = ExternalAudioBankOwner(
            descriptor_outer_index=1310,
            descriptor_inner_index=143,
            bank_name="lines",
            substream_count=31_826,
            sample_rate=22_050,
            channel_count=1,
        )
        identity = ExternalAudioBankIdentity(
            external_filename="lines.bin",
            outer_table_index=579,
            name_id=0x12345678,
            encoded_size=814_096_384,
            owners=(owner,),
        )
        external = _row(
            "apf:audio:external:579",
            "external_bank",
            "lines.bin",
            "814,096,384 raw XMA1 bytes · 1 AUSB descriptor owner",
            {
                "outer_table_index": 579,
                "external_filename": "lines.bin",
                "encoded_size": identity.encoded_size,
                "raw_asset_id": identity.raw_asset_id,
                "linked_audio_source_ids": (owner.audio_source_id,),
                "linked_role_ids": ("commentary_speech",),
                "linked_role_labels": ("Commentary & Speech",),
                "audio_format": "Raw external XMA1 packet bank",
            },
            external_bank_identity=identity,
        )
        playable = _row(
            "apf:audio:ausb:1310:143:substream:0",
            "ausb_substream",
            "lines · 00000",
            "XMA packets",
            {
                "outer_table_index": 1310,
                "inner_file_index": 143,
                "substream_index": 0,
                "audio_source_id": owner.audio_source_id,
                "audio_source_label": "lines · O1310/I143",
                "role_id": "commentary_speech",
                "role_label": "Commentary & Speech",
                "sample_rate": 22_050,
                "derived_channel_count": 1,
                "duration_seconds_candidate": 1.0,
            },
            export_identity=ExportIdentity(
                "ausb_substream", 1310, 143, 0, "lines-00000"
            ),
        )
        calls: list[tuple[ExternalAudioBankIdentity, Path]] = []
        queued: dict[str, object] = {}

        def export_external_audio_bank(
            selected: ExternalAudioBankIdentity,
            destination: Path,
            _progress: object,
        ) -> Path:
            calls.append((selected, destination))
            return destination

        def run_task(
            title: str, operation: object, complete: object, blocking: bool
        ) -> None:
            queued.update(
                title=title,
                operation=operation,
                complete=complete,
                blocking=blocking,
            )

        browser = InspectorBrowser(
            "Complete audio",
            SimpleNamespace(
                export_external_audio_bank=export_external_audio_bank
            ),
            run_task,
            audio_mode=True,
        )
        modified_events: list[str] = []
        browser.modifiedChanged.connect(lambda: modified_events.append("modified"))
        try:
            browser.set_model(PagedModel((external, playable)), "fixture")
            self.assertEqual(browser._selected_row(), external)
            self.assertTrue(
                browser.export_external_bank_button.isVisibleTo(browser)
            )
            self.assertTrue(browser.export_external_bank_button.isEnabled())
            self.assertFalse(browser.play_audio_button.isEnabled())
            self.assertTrue(browser.play_audio_button.isHidden())
            self.assertTrue(browser.export_audio_button.isHidden())
            self.assertTrue(browser.export_bank_button.isHidden())
            self.assertFalse(browser.shortlist_toggle_button.isEnabled())
            self.assertEqual(
                browser.shortlist_toggle_button.text(),
                "Choose a sound to shortlist",
            )
            self.assertFalse(browser.replace_audio_button.isEnabled())
            self.assertIn("not playable", browser.table.item(0, 5).text())
            self.assertEqual(browser.table.item(0, 4).text(), "O579")

            browser.source_filter.setCurrentIndex(
                browser.source_filter.findData(owner.audio_source_id)
            )
            browser.refresh()
            self.assertEqual(browser.table.rowCount(), 2)
            browser.role_filter.setCurrentIndex(
                browser.role_filter.findData("commentary_speech")
            )
            browser.refresh()
            self.assertEqual(browser.table.rowCount(), 2)
            browser.kind_filter.setCurrentIndex(
                browser.kind_filter.findData("external_bank")
            )
            browser.refresh()
            self.assertEqual(browser.table.rowCount(), 1)

            with tempfile.TemporaryDirectory() as directory:
                destination = Path(directory) / "lines.bin"
                with patch(
                    "mod_editor.apf_studio.gui.QFileDialog.getSaveFileName",
                    return_value=(
                        str(destination),
                        "Original external XMA1 bank (*.bin)",
                    ),
                ):
                    browser._export_external_audio_bank()
                self.assertEqual(
                    queued["title"],
                    "Exporting original APF external audio bank",
                )
                operation = queued["operation"]
                self.assertEqual(
                    operation(lambda *_args: None),  # type: ignore[operator]
                    destination,
                )
            self.assertEqual(calls, [(identity, destination)])
            self.assertEqual(modified_events, [])
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_standalone_audo_replace_and_revert_are_exactly_scoped(self) -> None:
        row = self._playable_row(19)
        row = _row(
            "apf:audio:audo:5:19",
            row.kind,
            row.title,
            row.subtitle,
            {
                **row.fields,
                "encoded_size": 10_240,
                "declared_sample_count": 21_604,
            },
            export_identity=row.export_identity,
        )
        replacement = Path("/tmp/user-authored.xma")
        queued: dict[str, object] = {}
        calls: list[tuple[ExportIdentity, Path]] = []
        facade = SimpleNamespace(modified_asset_ids=frozenset())

        def replace(
            identity: ExportIdentity, path: Path, _progress: object
        ) -> object:
            calls.append((identity, path))
            facade.modified_asset_ids = frozenset((row.row_id,))
            return object()

        facade.replace_audo_exact_slot = replace
        facade.revert = lambda asset_id, _progress: (
            setattr(facade, "modified_asset_ids", frozenset()) or asset_id == row.row_id
        )

        def run_task(
            title: str, operation: object, complete: object, blocking: bool
        ) -> None:
            queued.update(
                title=title,
                operation=operation,
                complete=complete,
                blocking=blocking,
            )

        browser = InspectorBrowser(
            "Complete audio",
            facade,
            run_task,
            audio_mode=True,
        )
        modified_events: list[str] = []
        browser.modifiedChanged.connect(lambda: modified_events.append("changed"))
        try:
            browser.set_model(PagedModel((row,)), "fixture")
            self.assertTrue(browser.replace_audio_button.isEnabled())
            self.assertFalse(browser.revert_audio_button.isEnabled())
            with patch(
                "mod_editor.apf_studio.gui.QFileDialog.getOpenFileName",
                return_value=(str(replacement), "RIFF XMA1 audio (*.xma)"),
            ):
                browser._replace_audio()
            self.assertEqual(
                queued["title"], "Validating exact-slot APF XMA1 replacement"
            )
            result = queued["operation"](lambda *_args: None)  # type: ignore[operator]
            queued["complete"](result)  # type: ignore[operator]
            self.assertEqual(calls, [(row.export_identity, replacement)])
            self.assertTrue(browser.revert_audio_button.isEnabled())
            self.assertEqual(browser.replace_audio_button.text(), "Replace XMA1 again…")
            self.assertIn("staged replacement", browser.audio_replace_note.text())
            self.assertEqual(modified_events, ["changed"])

            browser._revert_audio()
            self.assertEqual(queued["title"], "Reverting APF sound replacement")
            result = queued["operation"](lambda *_args: None)  # type: ignore[operator]
            queued["complete"](result)  # type: ignore[operator]
            self.assertFalse(browser.revert_audio_button.isEnabled())
            self.assertEqual(modified_events, ["changed", "changed"])
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_ausb_substream_replace_discloses_shared_effect_and_routes_writer(self) -> None:
        identity = ExportIdentity(
            "ausb_substream", 137, 8, 0, "cwdloop-00000"
        )
        row = _row(
            "apf:audio:ausb:137:8:0",
            "ausb_substream",
            "cwdloop-00000",
            "718 XMA packets",
            {
                "outer_table_index": 137,
                "inner_file_index": 8,
                "substream_index": 0,
                "sample_rate": 22_050,
                "derived_channel_count": 1,
                "range_length": 1_470_464,
                "declared_sample_count": 123_456,
                "shared_effect": True,
                "shared_owner_asset_ids": (
                    "apf:audio:ausb:137:8:0",
                    "apf:audio:ausb:659:289:0",
                ),
            },
            export_identity=identity,
        )
        replacement = Path("/tmp/user-authored-cwdloop.xma")
        queued: dict[str, object] = {}
        calls: list[tuple[ExportIdentity, Path]] = []
        facade = SimpleNamespace(modified_asset_ids=frozenset())

        def replace_ausb(
            selected: ExportIdentity, path: Path, _progress: object
        ) -> object:
            calls.append((selected, path))
            facade.modified_asset_ids = frozenset((row.row_id,))
            return object()

        facade.replace_ausb_exact_slot = replace_ausb
        facade.replace_audo_exact_slot = lambda *_args: self.fail(
            "AUSB edit routed to standalone writer"
        )
        facade.revert = lambda asset_id, _progress: (
            setattr(facade, "modified_asset_ids", frozenset())
            or asset_id == row.row_id
        )

        def run_task(
            title: str, operation: object, complete: object, blocking: bool
        ) -> None:
            queued.update(
                title=title,
                operation=operation,
                complete=complete,
                blocking=blocking,
            )

        browser = InspectorBrowser(
            "Complete audio", facade, run_task, audio_mode=True
        )
        try:
            browser.set_model(PagedModel((row,)), "fixture")
            self.assertTrue(browser.replace_audio_button.isEnabled())
            self.assertIn("AUSB bank substream", browser.audio_replace_note.text())
            self.assertIn("multiple owners", browser.audio_replace_note.text())
            self.assertIn("1.4 MB", browser.audio_replace_note.text())
            with patch(
                "mod_editor.apf_studio.gui.QFileDialog.getOpenFileName",
                return_value=(str(replacement), "RIFF XMA1 audio (*.xma)"),
            ):
                browser._replace_audio()
            self.assertEqual(
                queued["title"], "Validating exact AUSB-bank XMA1 replacement"
            )
            result = queued["operation"](lambda *_args: None)  # type: ignore[operator]
            queued["complete"](result)  # type: ignore[operator]
            self.assertEqual(calls, [(identity, replacement)])
            self.assertTrue(browser.revert_audio_button.isEnabled())
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_audio_shortlist_review_restores_browser_and_reorders_exact_export(self) -> None:
        rows = tuple(self._playable_row(index) for index in range(230))
        calls: list[tuple[str, ...]] = []
        queued: dict[str, object] = {}

        def export_audio_bundle(
            selected: tuple[object, ...],
            destination: Path,
            **_kwargs: object,
        ) -> Path:
            calls.append(tuple(row.row_id for row in selected))
            return destination

        def run_task(
            title: str, operation: object, complete: object, blocking: bool
        ) -> None:
            queued.update(
                title=title,
                operation=operation,
                complete=complete,
                blocking=blocking,
            )

        browser = InspectorBrowser(
            "Complete audio",
            SimpleNamespace(export_audio_bundle=export_audio_bundle),
            run_task,
            audio_mode=True,
        )
        modified_events: list[str] = []
        browser.modifiedChanged.connect(lambda: modified_events.append("modified"))
        try:
            browser.set_model(PagedModel(rows), "fixture")
            browser.search.setText("sound_")
            browser.kind_filter.setCurrentIndex(
                browser.kind_filter.findData("audo")
            )
            browser.role_filter.setCurrentIndex(
                browser.role_filter.findData("ui_menu_sfx")
            )
            browser.source_filter.setCurrentIndex(
                browser.source_filter.findData("audo:standalone")
            )
            browser.offset = 100
            browser.refresh()
            browser.table.selectRow(7)
            self.application.processEvents()
            self.assertEqual(browser._selected_row().row_id, "audo:107")

            insertion = (207, 3, 107, 88)
            browser._audio_shortlist.update(
                (rows[index].row_id, rows[index]) for index in insertion
            )
            browser._update_audio_shortlist_actions()
            browser._toggle_audio_review()

            self.assertTrue(browser._audio_review_mode)
            self.assertEqual(browser.shortlist_review_button.text(), "Back to audio browser")
            self.assertFalse(browser.search.isEnabled())
            self.assertFalse(browser.kind_filter.isEnabled())
            self.assertFalse(browser.role_filter.isEnabled())
            self.assertFalse(browser.source_filter.isEnabled())
            self.assertFalse(browser.shortlist_page_button.isEnabled())
            self.assertFalse(browser.export_matching_button.isEnabled())
            self.assertEqual(browser.count.text(), "4 shortlisted sounds")
            self.assertEqual(
                tuple(browser._visible),
                tuple(f"audo:{index}" for index in insertion),
            )
            self.assertTrue(browser.play_audio_button.isEnabled())
            self.assertFalse(browser.export_audio_button.isHidden())

            browser.table.selectRow(1)
            browser._move_shortlisted_audio(-1)
            self.assertEqual(
                tuple(row.row_id for row in browser._shortlisted_audio_rows()),
                ("audo:3", "audo:207", "audo:107", "audo:88"),
            )
            self.assertEqual(browser._selected_row().row_id, "audo:3")
            self.assertFalse(browser.shortlist_move_up_button.isEnabled())
            self.assertTrue(browser.shortlist_move_down_button.isEnabled())

            with tempfile.TemporaryDirectory() as directory:
                destination = Path(directory) / "ordered.zip"
                with patch(
                    "mod_editor.apf_studio.gui.QFileDialog.getSaveFileName",
                    return_value=(
                        str(destination),
                        "Original XMA1 sounds ZIP (*.zip)",
                    ),
                ):
                    browser._export_shortlisted_audio()
                operation = queued["operation"]
                self.assertEqual(
                    operation(lambda *_args: None), destination  # type: ignore[operator]
                )
            self.assertEqual(
                calls,
                [("audo:3", "audo:207", "audo:107", "audo:88")],
            )

            browser._toggle_audio_shortlist()
            self.assertTrue(browser._audio_review_mode)
            self.assertEqual(browser._selected_row().row_id, "audo:207")
            browser._toggle_audio_review()
            self.assertFalse(browser._audio_review_mode)
            self.assertEqual(browser.search.text(), "sound_")
            self.assertEqual(browser.kind_filter.currentData(), "audo")
            self.assertEqual(browser.role_filter.currentData(), "ui_menu_sfx")
            self.assertEqual(browser.source_filter.currentData(), "audo:standalone")
            self.assertEqual(browser.offset, 100)
            self.assertEqual(browser._selected_row().row_id, "audo:107")
            self.assertTrue(browser.search.isEnabled())
            self.assertEqual(modified_events, [])
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_audio_shortlist_review_pages_crosses_boundaries_and_resets_cleanly(self) -> None:
        rows = tuple(self._playable_row(index) for index in range(256))
        browser = InspectorBrowser(
            "Complete audio",
            object(),  # type: ignore[arg-type]
            lambda *_args, **_kwargs: None,
            audio_mode=True,
        )
        modified_events: list[str] = []
        browser.modifiedChanged.connect(lambda: modified_events.append("modified"))
        try:
            model = PagedModel(rows)
            browser.set_model(model, "fixture")
            browser._audio_shortlist.update((row.row_id, row) for row in rows)
            browser._update_audio_shortlist_actions()
            browser._toggle_audio_review()
            self.assertEqual(browser.table.rowCount(), 100)
            self.assertEqual(browser.page.text(), "Page 1 of 3")
            browser._move(100)
            self.assertEqual(tuple(browser._visible)[:2], ("audo:100", "audo:101"))
            browser._move(100)
            self.assertEqual(browser.table.rowCount(), 56)
            self.assertEqual(tuple(browser._visible)[-1], "audo:255")

            browser.offset = 100
            browser.refresh()
            browser.table.selectRow(0)
            browser._move_shortlisted_audio(-1)
            ordered = tuple(row.row_id for row in browser._shortlisted_audio_rows())
            self.assertEqual(ordered[99:101], ("audo:100", "audo:99"))
            self.assertEqual(browser.offset, 0)
            self.assertEqual(browser._selected_row().row_id, "audo:100")

            browser._clear_audio_shortlist()
            self.assertFalse(browser._audio_review_mode)
            self.assertEqual(browser._shortlisted_audio_rows(), ())

            browser._audio_shortlist[rows[0].row_id] = rows[0]
            browser._update_audio_shortlist_actions()
            browser._toggle_audio_review()
            browser._toggle_audio_shortlist()
            self.assertFalse(browser._audio_review_mode)
            self.assertEqual(browser._shortlisted_audio_rows(), ())

            browser._audio_shortlist.update(
                (row.row_id, row) for row in rows[:2]
            )
            browser._update_audio_shortlist_actions()
            browser._toggle_audio_review()
            browser.set_model(model, "reloaded fixture")
            self.assertFalse(browser._audio_review_mode)
            self.assertEqual(browser._shortlisted_audio_rows(), ())
            self.assertEqual(browser.shortlist_review_button.text(), "Review selected")
            self.assertEqual(modified_events, [])
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_soundtrack_album_pairs_exact_banks_with_stereo_default_and_mono_selector(self) -> None:
        browser_row = self._playable_row(999)
        model = PagedModel((browser_row, *self._soundtrack_rows()))
        browser = InspectorBrowser(
            "Complete audio",
            object(),  # type: ignore[arg-type]
            lambda *_args, **_kwargs: None,
            audio_mode=True,
        )
        modified_events: list[str] = []
        browser.modifiedChanged.connect(lambda: modified_events.append("modified"))
        try:
            browser.set_model(model, "fixture")
            self.assertTrue(browser.soundtrack_album_button.isEnabled())
            self.assertEqual(browser.soundtrack_album_button.text(), "Soundtrack album (15)")
            browser.search.setText("sound_999")
            browser.kind_filter.setCurrentIndex(
                browser.kind_filter.findData("audo")
            )
            browser.role_filter.setCurrentIndex(
                browser.role_filter.findData("ui_menu_sfx")
            )
            browser.source_filter.setCurrentIndex(
                browser.source_filter.findData("audo:standalone")
            )
            browser.refresh()
            self.assertEqual(browser._selected_row().row_id, "audo:999")

            browser._toggle_soundtrack_album()
            self.assertTrue(browser._soundtrack_album_mode)
            self.assertEqual(browser.soundtrack_version.currentData(), "jukeboxmusic")
            self.assertFalse(browser.soundtrack_version.isHidden())
            self.assertIn("Unknown", browser.soundtrack_album_note.text())
            self.assertIn("does not guess", browser.soundtrack_album_note.text())
            self.assertEqual(browser.table.rowCount(), 15)
            self.assertEqual(browser.count.text(), "15 soundtrack tracks · stereo masters")
            self.assertEqual(
                tuple(row.fields["substream_index"] for row in browser._visible.values()),
                tuple(range(15)),
            )
            self.assertTrue(
                all(
                    row.export_identity.outer_table_index == 8
                    for row in browser._visible.values()
                    if row.export_identity is not None
                )
            )
            self.assertTrue(browser.play_audio_button.isEnabled())
            self.assertFalse(browser.export_audio_button.isHidden())
            self.assertIn("(15)", browser.export_matching_button.text())
            self.assertEqual(browser.shortlist_page_button.text(), "Add this page (15)")

            browser.table.selectRow(7)
            browser.soundtrack_version.setCurrentIndex(
                browser.soundtrack_version.findData("jukebox22")
            )
            self.application.processEvents()
            self.assertEqual(browser.count.text(), "15 soundtrack tracks · mono companions")
            self.assertEqual(browser._selected_row().fields["logical_track_number"], 8)
            self.assertTrue(
                all(
                    row.export_identity.outer_table_index == 9
                    for row in browser._visible.values()
                    if row.export_identity is not None
                )
            )
            browser._add_visible_audio_to_shortlist()
            self.assertEqual(
                tuple(row.fields["logical_track_number"] for row in browser._shortlisted_audio_rows()),
                tuple(range(1, 16)),
            )

            browser._toggle_soundtrack_album()
            self.assertFalse(browser._soundtrack_album_mode)
            self.assertEqual(browser.search.text(), "sound_999")
            self.assertEqual(browser.kind_filter.currentData(), "audo")
            self.assertEqual(browser.role_filter.currentData(), "ui_menu_sfx")
            self.assertEqual(browser.source_filter.currentData(), "audo:standalone")
            self.assertEqual(browser._selected_row().row_id, "audo:999")
            self.assertEqual(modified_events, [])
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_audio_shortlist_crosses_filters_deduplicates_and_resets_with_model(self) -> None:
        rows = (
            self._playable_row(1),
            self._playable_row(
                2,
                source_id="ausb:8:2",
                source_label="jukeboxmusic · O8/I2",
            ),
            self._playable_row(
                3,
                source_id="ausb:8:2",
                source_label="jukeboxmusic · O8/I2",
            ),
        )
        browser = InspectorBrowser(
            "Complete audio",
            object(),  # type: ignore[arg-type]
            lambda *_args, **_kwargs: None,
            audio_mode=True,
        )
        try:
            model = PagedModel(rows)
            browser.set_model(model, "fixture")
            self.assertEqual(browser.shortlist_page_button.text(), "Add this page (3)")

            browser._toggle_audio_shortlist()
            self.assertEqual(
                tuple(row.row_id for row in browser._shortlisted_audio_rows()),
                ("audo:1",),
            )
            self.assertIn("Selected", browser.table.item(0, 5).text())
            self.assertEqual(browser.shortlist_count.text(), "Selected 1 / 256")

            browser.source_filter.setCurrentIndex(
                browser.source_filter.findData("ausb:8:2")
            )
            browser.refresh()
            browser._toggle_audio_shortlist()
            browser._add_visible_audio_to_shortlist()
            self.assertEqual(
                tuple(row.row_id for row in browser._shortlisted_audio_rows()),
                ("audo:1", "audo:2", "audo:3"),
            )
            browser._add_visible_audio_to_shortlist()
            self.assertEqual(len(browser._shortlisted_audio_rows()), 3)

            browser.source_filter.setCurrentIndex(0)
            browser.refresh()
            self.assertTrue(
                all("Selected" in browser.table.item(index, 5).text() for index in range(3))
            )
            browser.table.selectRow(0)
            browser._toggle_audio_shortlist()
            self.assertEqual(
                tuple(row.row_id for row in browser._shortlisted_audio_rows()),
                ("audo:2", "audo:3"),
            )
            browser._clear_audio_shortlist()
            self.assertEqual(browser._shortlisted_audio_rows(), ())
            self.assertFalse(browser.export_shortlist_button.isEnabled())

            browser._toggle_audio_shortlist()
            self.assertEqual(len(browser._shortlisted_audio_rows()), 1)
            browser.set_model(model, "reloaded fixture")
            self.assertEqual(browser._shortlisted_audio_rows(), ())
            self.assertEqual(browser.shortlist_count.text(), "Selected 0 / 256")
            self.assertTrue(browser.shortlist_matching_button.isEnabled())

            browser.set_loading("Loading a different APF game…")
            self.assertFalse(browser.shortlist_matching_button.isEnabled())
            self.assertEqual(
                browser.shortlist_matching_button.text(), "Add all matching"
            )
            browser.set_model(model, "loaded again")
            self.assertTrue(browser.shortlist_matching_button.isEnabled())
            browser.set_unavailable("APF audio unavailable")
            self.assertFalse(browser.shortlist_matching_button.isEnabled())
            self.assertEqual(
                browser.shortlist_matching_button.text(), "Add all matching"
            )
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_audio_shortlist_page_add_is_all_or_nothing_at_256_cap(self) -> None:
        rows = tuple(self._playable_row(index) for index in range(257))
        browser = InspectorBrowser(
            "Complete audio",
            object(),  # type: ignore[arg-type]
            lambda *_args, **_kwargs: None,
            audio_mode=True,
        )
        try:
            browser.set_model(PagedModel(rows), "fixture")
            browser._audio_shortlist.update(
                (row.row_id, row) for row in rows[:200]
            )
            browser.offset = 200
            browser.refresh()
            self.assertEqual(browser.table.rowCount(), 57)
            self.assertIn("56 spaces remain", browser.shortlist_page_button.toolTip())
            with patch(
                "mod_editor.apf_studio.gui.QMessageBox.information"
            ) as information:
                browser._add_visible_audio_to_shortlist()
            self.assertEqual(len(browser._shortlisted_audio_rows()), 200)
            self.assertIn("256", information.call_args.args[2])

            browser._audio_shortlist.clear()
            browser._audio_shortlist.update(
                (row.row_id, row) for row in rows[:256]
            )
            browser.table.selectRow(56)
            browser._update_audio_shortlist_actions()
            self.assertFalse(browser.shortlist_toggle_button.isEnabled())
            self.assertIn("full", browser.shortlist_toggle_button.toolTip())
            with patch(
                "mod_editor.apf_studio.gui.QMessageBox.information"
            ) as information:
                browser._toggle_audio_shortlist()
            self.assertEqual(len(browser._shortlisted_audio_rows()), 256)
            self.assertIn("up to 256", information.call_args.args[2])
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_audio_shortlist_adds_all_new_matches_once_in_stable_order(self) -> None:
        rows = (
            self._playable_row(5),
            self._playable_row(
                2,
                source_id="ausb:8:2",
                source_label="jukeboxmusic · O8/I2",
            ),
            self._playable_row(4),
            self._playable_row(7),
        )
        tasks: list[str] = []
        browser = InspectorBrowser(
            "Complete audio",
            object(),  # type: ignore[arg-type]
            lambda title, *_args, **_kwargs: tasks.append(title),
            audio_mode=True,
        )
        modified_events: list[str] = []
        browser.modifiedChanged.connect(
            lambda: modified_events.append("modified")
        )
        try:
            browser.set_model(PagedModel(rows), "fixture")
            browser._audio_shortlist.update(
                (row.row_id, row) for row in (rows[1], rows[2])
            )
            browser._cleared_audio_shortlist = ((rows[0].row_id, rows[0]),)
            browser.source_filter.setCurrentIndex(
                browser.source_filter.findData("audo:standalone")
            )
            browser.refresh()

            self.assertEqual(
                browser.shortlist_matching_button.text(),
                "Add all matching (2)",
            )
            self.assertTrue(browser.shortlist_matching_button.isEnabled())
            self.assertIn(
                "stable game catalog order",
                browser.shortlist_matching_button.toolTip(),
            )
            browser._add_matching_audio_to_shortlist()

            self.assertEqual(
                tuple(row.row_id for row in browser._shortlisted_audio_rows()),
                ("audo:2", "audo:4", "audo:5", "audo:7"),
            )
            self.assertEqual(browser._cleared_audio_shortlist, ())
            self.assertEqual(len(set(browser._audio_shortlist)), 4)
            self.assertTrue(
                all(
                    "Selected" in browser.table.item(index, 5).text()
                    for index in range(browser.table.rowCount())
                )
            )
            self.assertFalse(browser.shortlist_matching_button.isEnabled())
            self.assertEqual(
                browser.shortlist_matching_button.text(), "Add all matching"
            )
            self.assertEqual(tasks, [])
            self.assertEqual(modified_events, [])
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_audio_shortlist_add_all_matching_is_atomic_at_256_cap(self) -> None:
        rows = tuple(self._playable_row(index) for index in range(257))
        tasks: list[str] = []
        browser = InspectorBrowser(
            "Complete audio",
            object(),  # type: ignore[arg-type]
            lambda title, *_args, **_kwargs: tasks.append(title),
            audio_mode=True,
        )
        modified_events: list[str] = []
        browser.modifiedChanged.connect(
            lambda: modified_events.append("modified")
        )
        try:
            browser.set_model(PagedModel(rows), "fixture")
            browser._audio_shortlist.update(
                (row.row_id, row) for row in rows[:200]
            )
            cleared_snapshot = ((rows[256].row_id, rows[256]),)
            browser._cleared_audio_shortlist = cleared_snapshot
            browser._update_audio_shortlist_actions()
            before = browser._shortlisted_audio_rows()

            self.assertEqual(
                browser.shortlist_matching_button.text(),
                "Add all matching (57)",
            )
            self.assertTrue(browser.shortlist_matching_button.isEnabled())
            self.assertIn("56 spaces remain", browser.shortlist_matching_button.toolTip())
            self.assertIn(
                "Cannot add 57 matching playable sounds",
                browser.shortlist_matching_button.accessibleName(),
            )
            self.assertIn(
                "no sounds will be added",
                browser.shortlist_matching_button.accessibleDescription(),
            )
            with patch(
                "mod_editor.apf_studio.gui.QMessageBox.information"
            ) as information:
                browser._add_matching_audio_to_shortlist()

            self.assertEqual(browser._shortlisted_audio_rows(), before)
            self.assertEqual(browser._cleared_audio_shortlist, cleared_snapshot)
            message = information.call_args.args[2]
            for count in ("200", "57", "257", "256", "56"):
                self.assertIn(count, message)
            self.assertIn("no sounds were added", message)
            self.assertEqual(tasks, [])
            self.assertEqual(modified_events, [])
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_matching_audio_cache_avoids_full_rescan_on_selection_updates(self) -> None:
        rows = tuple(self._playable_row(index) for index in range(12))
        browser = InspectorBrowser(
            "Complete audio",
            object(),  # type: ignore[arg-type]
            lambda *_args, **_kwargs: None,
            audio_mode=True,
        )
        original_filtered_rows = PagedModel.filtered_rows
        filtered_calls: list[str] = []

        def counted_filtered_rows(model: PagedModel, **kwargs: object) -> object:
            filtered_calls.append(str(kwargs.get("search", "")))
            return original_filtered_rows(model, **kwargs)

        try:
            browser.set_model(PagedModel(rows), "fixture")
            browser._matching_audio_cache_key = None
            browser._matching_audio_cache = ()
            with patch.object(
                PagedModel,
                "filtered_rows",
                new=counted_filtered_rows,
            ):
                browser._update_audio_shortlist_actions()
                first_scan_count = len(filtered_calls)
                self.assertEqual(first_scan_count, 1)

                for row_index in (1, 4, 7, 2):
                    browser.table.selectRow(row_index)
                    browser._update_audio_shortlist_actions()
                self.assertEqual(len(filtered_calls), first_scan_count)

                browser.search.setText("sound_011")
                browser.refresh()
                self.assertGreater(len(filtered_calls), first_scan_count)
                self.assertEqual(
                    browser.shortlist_matching_button.text(),
                    "Add all matching (1)",
                )
                browser._begin_audio_catalog_transition()
                self.assertIsNone(browser._matching_audio_cache_key)
                self.assertEqual(browser._matching_audio_cache, ())
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_audio_shortlist_clear_has_one_level_exact_ordered_undo(self) -> None:
        rows = tuple(self._playable_row(index) for index in range(4))
        tasks: list[str] = []
        browser = InspectorBrowser(
            "Complete audio",
            object(),  # type: ignore[arg-type]
            lambda title, *_args, **_kwargs: tasks.append(title),
            audio_mode=True,
        )
        modified_events: list[str] = []
        browser.modifiedChanged.connect(
            lambda: modified_events.append("modified")
        )
        try:
            browser.set_model(PagedModel(rows), "fixture")
            expected = (rows[3], rows[1], rows[2])
            browser._audio_shortlist.update(
                (row.row_id, row) for row in expected
            )
            browser._update_audio_shortlist_actions()

            browser._clear_audio_shortlist()
            self.assertEqual(browser._shortlisted_audio_rows(), ())
            self.assertEqual(
                browser._cleared_audio_shortlist,
                tuple((row.row_id, row) for row in expected),
            )
            self.assertEqual(browser.shortlist_clear_button.text(), "Undo")
            self.assertTrue(browser.shortlist_clear_button.isEnabled())
            self.assertIn("3 sounds", browser.shortlist_clear_button.accessibleName())

            browser._clear_audio_shortlist()
            self.assertEqual(browser._shortlisted_audio_rows(), expected)
            self.assertEqual(browser._cleared_audio_shortlist, ())
            self.assertEqual(browser.shortlist_clear_button.text(), "Clear")
            self.assertEqual(modified_events, [])
            self.assertEqual(tasks, [])
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_audio_shortlist_clear_from_review_restores_without_reopening(
        self,
    ) -> None:
        rows = tuple(self._playable_row(index) for index in range(4))
        browser = InspectorBrowser(
            "Complete audio",
            object(),  # type: ignore[arg-type]
            lambda *_args, **_kwargs: None,
            audio_mode=True,
        )
        try:
            browser.set_model(PagedModel(rows), "fixture")
            expected = (rows[2], rows[0], rows[3])
            browser._audio_shortlist.update(
                (row.row_id, row) for row in expected
            )
            browser._update_audio_shortlist_actions()
            browser._toggle_audio_review()
            self.assertTrue(browser._audio_review_mode)

            browser._clear_audio_shortlist()
            self.assertFalse(browser._audio_review_mode)
            self.assertEqual(browser._shortlisted_audio_rows(), ())
            self.assertEqual(browser.shortlist_clear_button.text(), "Undo")

            browser._clear_audio_shortlist()
            self.assertEqual(browser._shortlisted_audio_rows(), expected)
            self.assertFalse(browser._audio_review_mode)
            self.assertTrue(browser.search.isEnabled())
            self.assertTrue(browser.shortlist_review_button.isEnabled())
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_audio_shortlist_clear_undo_expires_on_mutation_and_set_model(
        self,
    ) -> None:
        rows = tuple(self._playable_row(index) for index in range(3))
        replacement_rows = tuple(
            self._playable_row(index) for index in range(10, 12)
        )
        browser = InspectorBrowser(
            "Complete audio",
            object(),  # type: ignore[arg-type]
            lambda *_args, **_kwargs: None,
            audio_mode=True,
        )
        try:
            browser.set_model(PagedModel(rows), "fixture")
            browser._audio_shortlist.update(
                (row.row_id, row) for row in (rows[2], rows[1])
            )
            browser._update_audio_shortlist_actions()
            browser._clear_audio_shortlist()
            self.assertTrue(browser._cleared_audio_shortlist)

            browser._toggle_audio_shortlist()
            self.assertEqual(browser._shortlisted_audio_rows(), (rows[0],))
            self.assertEqual(browser._cleared_audio_shortlist, ())

            browser._clear_audio_shortlist()
            self.assertTrue(browser._cleared_audio_shortlist)
            browser.set_model(PagedModel(replacement_rows), "replacement")
            self.assertEqual(browser._shortlisted_audio_rows(), ())
            self.assertEqual(browser._cleared_audio_shortlist, ())
            self.assertFalse(browser.shortlist_clear_button.isEnabled())
            browser._clear_audio_shortlist()
            self.assertEqual(browser._shortlisted_audio_rows(), ())
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_pending_audio_query_guards_page_and_aggregate_actions(self) -> None:
        rows = tuple(self._playable_row(index) for index in range(150))
        tasks: list[str] = []
        browser = InspectorBrowser(
            "Complete audio",
            object(),  # type: ignore[arg-type]
            lambda title, *_args, **_kwargs: tasks.append(title),
            audio_mode=True,
        )
        try:
            browser.set_model(PagedModel(rows), "fixture")
            self.assertEqual(tuple(browser._visible), tuple(
                row.row_id for row in rows[:100]
            ))
            self.assertTrue(browser.shortlist_page_button.isEnabled())
            self.assertTrue(browser.shortlist_matching_button.isEnabled())
            self.assertEqual(
                browser.shortlist_matching_button.text(),
                "Add all matching (150)",
            )
            self.assertTrue(browser.next.isEnabled())
            self.assertTrue(browser.export_matching_button.isEnabled())
            self.assertTrue(
                browser.export_audio_replacement_template_button.isEnabled()
            )
            self.assertTrue(browser.export_rows_button.isEnabled())

            browser.search.setText("sound_149")
            self.assertTrue(browser._timer.isActive())
            self.assertEqual(tuple(browser._visible), tuple(
                row.row_id for row in rows[:100]
            ))
            self.assertFalse(browser.shortlist_page_button.isEnabled())
            self.assertFalse(browser.shortlist_matching_button.isEnabled())
            self.assertIn(
                "results update",
                browser.shortlist_matching_button.accessibleName(),
            )
            self.assertFalse(browser.previous.isEnabled())
            self.assertFalse(browser.next.isEnabled())
            self.assertFalse(browser.export_matching_button.isEnabled())
            self.assertFalse(
                browser.export_audio_replacement_template_button.isEnabled()
            )
            self.assertFalse(browser.export_rows_button.isEnabled())
            self.assertIn("Updating", browser.count.text())

            browser._add_visible_audio_to_shortlist()
            browser._add_matching_audio_to_shortlist()
            browser._move(100)
            self.assertEqual(browser._shortlisted_audio_rows(), ())
            self.assertEqual(browser.offset, 0)
            with patch(
                "mod_editor.apf_studio.gui.QFileDialog.getSaveFileName"
            ) as save_dialog:
                browser._export_matching_audio()
                browser._export_audio_replacement_template()
                browser._export_rows()
            save_dialog.assert_not_called()
            self.assertEqual(tasks, [])

            browser.refresh()
            self.assertFalse(browser._timer.isActive())
            self.assertEqual(tuple(browser._visible), (rows[149].row_id,))
            self.assertTrue(browser.shortlist_page_button.isEnabled())
            self.assertTrue(browser.shortlist_matching_button.isEnabled())
            self.assertEqual(
                browser.shortlist_matching_button.text(),
                "Add all matching (1)",
            )
            self.assertTrue(browser.export_matching_button.isEnabled())
            self.assertTrue(
                browser.export_audio_replacement_template_button.isEnabled()
            )
            self.assertTrue(browser.export_rows_button.isEnabled())
            browser._add_visible_audio_to_shortlist()
            self.assertEqual(browser._shortlisted_audio_rows(), (rows[149],))
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_audio_query_type_erase_restores_page_two_and_next_reaches_page_three(
        self,
    ) -> None:
        rows = tuple(self._playable_row(index) for index in range(350))
        browser = InspectorBrowser(
            "Complete audio",
            object(),  # type: ignore[arg-type]
            lambda *_args, **_kwargs: None,
            audio_mode=True,
        )
        try:
            browser.set_model(PagedModel(rows), "fixture")
            browser._move(100)
            self.assertEqual(browser.offset, 100)
            self.assertEqual(browser.page.text(), "Page 2 of 4")
            self.assertEqual(
                tuple(browser._visible),
                tuple(row.row_id for row in rows[100:200]),
            )
            self.assertTrue(browser.previous.isEnabled())
            self.assertTrue(browser.next.isEnabled())

            browser.search.setText("sound_349")
            self.assertTrue(browser._timer.isActive())
            self.assertEqual(browser.offset, 0)
            browser.search.clear()

            self.assertFalse(browser._timer.isActive())
            self.assertEqual(browser.offset, 100)
            self.assertEqual(browser.page.text(), "Page 2 of 4")
            self.assertEqual(
                tuple(browser._visible),
                tuple(row.row_id for row in rows[100:200]),
            )
            self.assertTrue(browser.previous.isEnabled())
            self.assertTrue(browser.next.isEnabled())

            browser.next.click()
            self.application.processEvents()
            self.assertEqual(browser.offset, 200)
            self.assertEqual(browser.page.text(), "Page 3 of 4")
            self.assertEqual(
                tuple(browser._visible),
                tuple(row.row_id for row in rows[200:300]),
            )
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_audio_shortlist_export_preserves_order_and_defaults_xma(self) -> None:
        rows = (self._playable_row(1), self._playable_row(2))
        calls: list[tuple[tuple[object, ...], Path, str, str]] = []

        def export_audio_bundle(
            selected: tuple[object, ...],
            destination: Path,
            *,
            bundle_name: str,
            output_extension: str,
            progress: object,
        ) -> Path:
            calls.append(
                (tuple(selected), destination, bundle_name, output_extension)
            )
            return destination

        queued: dict[str, object] = {}

        def run_task(
            title: str, operation: object, complete: object, blocking: bool
        ) -> None:
            queued.update(
                title=title,
                operation=operation,
                complete=complete,
                blocking=blocking,
            )

        browser = InspectorBrowser(
            "Complete audio",
            SimpleNamespace(export_audio_bundle=export_audio_bundle),
            run_task,
            audio_mode=True,
        )
        try:
            browser.set_model(PagedModel(rows), "fixture")
            browser._toggle_audio_shortlist()
            browser.table.selectRow(1)
            browser._toggle_audio_shortlist()
            with tempfile.TemporaryDirectory() as directory:
                destination = Path(directory) / "selected.zip"
                with patch(
                    "mod_editor.apf_studio.gui.QFileDialog.getSaveFileName",
                    return_value=(
                        str(destination),
                        "Original XMA1 sounds ZIP (*.zip)",
                    ),
                ) as dialog:
                    browser._export_shortlisted_audio()
                self.assertEqual(queued["title"], "Exporting selected APF sounds")
                self.assertTrue(dialog.call_args.args[2].endswith("original-xma.zip"))
                self.assertTrue(dialog.call_args.args[3].startswith("Original XMA1"))
                operation = queued["operation"]
                self.assertEqual(
                    operation(lambda *_args: None), destination  # type: ignore[operator]
                )
            self.assertEqual(calls[0][0], rows)
            self.assertEqual(calls[0][1], destination)
            self.assertEqual(calls[0][2], "APF audio shortlist")
            self.assertEqual(calls[0][3], ".xma")
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_matching_audio_action_forwards_filtered_rows_and_defaults_xma(self) -> None:
        identity = ExportIdentity("audo", 5, 1, None, "menu-back")
        row = _row(
            "audo:1",
            "audo",
            "menu_back",
            "AUDIO",
            {
                "outer_table_index": 5,
                "inner_file_index": 1,
                "audio_source_id": "audo:standalone",
                "audio_source_label": "Standalone AUDO",
                "role_id": "ui_menu_sfx",
                "role_label": "UI & Menu SFX",
                "audio_format": "XMA1",
                "sample_rate": 22_050,
                "derived_channel_count": 1,
                "duration_seconds": 1.0,
            },
            export_identity=identity,
        )
        calls: list[tuple[tuple[object, ...], Path, str, str]] = []

        def export_audio_bundle(
            rows: tuple[object, ...],
            destination: Path,
            *,
            bundle_name: str,
            output_extension: str,
            progress: object,
        ) -> Path:
            calls.append((tuple(rows), destination, bundle_name, output_extension))
            return destination

        queued: dict[str, object] = {}

        def run_task(
            title: str, operation: object, complete: object, blocking: bool
        ) -> None:
            queued.update(
                title=title,
                operation=operation,
                complete=complete,
                blocking=blocking,
            )

        browser = InspectorBrowser(
            "Complete audio",
            SimpleNamespace(export_audio_bundle=export_audio_bundle),
            run_task,
            audio_mode=True,
        )
        try:
            browser.set_model(PagedModel((row,)), "fixture")
            with tempfile.TemporaryDirectory() as directory:
                destination = Path(directory) / "matching.zip"
                with patch(
                    "mod_editor.apf_studio.gui.QFileDialog.getSaveFileName",
                    return_value=(
                        str(destination),
                        "Original XMA1 sounds ZIP (*.zip)",
                    ),
                ) as dialog:
                    browser._export_matching_audio()
                self.assertEqual(queued["title"], "Exporting matching APF sounds")
                dialog_default = dialog.call_args.args[2]
                dialog_filters = dialog.call_args.args[3]
                self.assertTrue(dialog_default.endswith("original-xma.zip"))
                self.assertTrue(dialog_filters.startswith("Original XMA1"))
                operation = queued["operation"]
                result = operation(lambda *_args: None)  # type: ignore[operator]
                self.assertEqual(result, destination)
                self.assertEqual(calls[0][0], (row,))
                self.assertEqual(calls[0][1], destination)
                self.assertEqual(calls[0][3], ".xma")
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_decoded_export_forwards_the_coordinate_backed_source_filter(self) -> None:
        row = _row(
            "bank:8:2:0",
            "ausb_substream",
            "Soundtrack Track 01 · Full stereo",
            "XMA packets",
            {
                "outer_table_index": 8,
                "inner_file_index": 2,
                "substream_index": 0,
                "audio_source_id": "ausb:8:2",
                "audio_source_label": "jukeboxmusic · O8/I2",
                "role_id": "soundtrack_music",
                "role_label": "Soundtrack & Music",
            },
            export_identity=ExportIdentity(
                "ausb_substream", 8, 2, 0, "jukeboxmusic-00000"
            ),
        )
        calls: list[dict[str, object]] = []

        def export_inspector_rows(
            model: PagedModel,
            destination: Path,
            **kwargs: object,
        ) -> Path:
            calls.append({"model": model, "destination": destination, **kwargs})
            return destination

        queued: dict[str, object] = {}

        def run_task(
            title: str, operation: object, complete: object, blocking: bool
        ) -> None:
            queued.update(operation=operation)

        browser = InspectorBrowser(
            "Complete audio",
            SimpleNamespace(export_inspector_rows=export_inspector_rows),
            run_task,
            audio_mode=True,
        )
        try:
            model = PagedModel((row,))
            browser.set_model(model, "fixture")
            browser.source_filter.setCurrentIndex(
                browser.source_filter.findData("ausb:8:2")
            )
            browser.refresh()
            with tempfile.TemporaryDirectory() as directory:
                destination = Path(directory) / "decoded.json"
                with patch(
                    "mod_editor.apf_studio.gui.QFileDialog.getSaveFileName",
                    return_value=(str(destination), "Structured JSON (*.json)"),
                ):
                    browser._export_rows()
                operation = queued["operation"]
                self.assertEqual(
                    operation(lambda *_args: None), destination  # type: ignore[operator]
                )
            self.assertEqual(calls[0]["model"], model)
            self.assertEqual(calls[0]["sources"], "ausb:8:2")
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_replacement_template_uses_filters_album_and_shortlist_order(self) -> None:
        first = self._pack_row(1)
        second = self._pack_row(2)
        other = self._pack_row(3, role_id="other_audio")
        model = PagedModel((first, second, other, *self._soundtrack_rows()))
        calls: list[tuple[tuple[object, ...], Path, str, str]] = []

        def export_template(
            rows: tuple[object, ...],
            destination: Path,
            _progress: object,
            *,
            container: str,
            input_kind: str = "xma1",
        ) -> object:
            selected = tuple(rows)
            calls.append((selected, destination, container, input_kind))
            return SimpleNamespace(
                path=destination,
                entry_count=len(selected),
                container=container,
                input_kind=input_kind,
            )

        def run_task(
            _title: str,
            operation: object,
            complete: object,
            _blocking: bool,
        ) -> None:
            result = operation(lambda *_args: None)  # type: ignore[operator]
            complete(result)  # type: ignore[operator]

        browser = InspectorBrowser(
            "Complete audio",
            SimpleNamespace(export_audio_replacement_template=export_template),
            run_task,
            audio_mode=True,
        )
        try:
            browser.set_model(model, "fixture")
            browser.role_filter.setCurrentIndex(
                browser.role_filter.findData("ui_menu_sfx")
            )
            browser.refresh()
            self.assertIn("(2)", browser.export_audio_replacement_template_button.text())
            self.assertEqual(browser._audio_replacement_template_rows(), (first, second))

            with tempfile.TemporaryDirectory() as directory:
                filtered = Path(directory) / "filtered-pack"
                album = Path(directory) / "album-pack"
                shortlist = Path(directory) / "shortlist-pack"
                with (
                    patch(
                        "mod_editor.apf_studio.gui.QFileDialog.getSaveFileName",
                        return_value=(str(filtered), "Replacement-template folder (*)"),
                    ),
                    patch("mod_editor.apf_studio.gui.QMessageBox.information"),
                ):
                    browser._export_audio_replacement_template()
                self.assertEqual(
                    calls[-1], ((first, second), filtered, "folder", "xma1")
                )

                browser.role_filter.setCurrentIndex(0)
                browser.refresh()
                browser._toggle_soundtrack_album()
                album_rows = browser._audio_replacement_template_rows()
                self.assertEqual(len(album_rows), 15)
                self.assertTrue(
                    all(row.fields["bank_name"] == "jukeboxmusic" for row in album_rows)
                )
                self.assertIn(
                    "(15)", browser.export_audio_replacement_template_button.text()
                )
                with (
                    patch(
                        "mod_editor.apf_studio.gui.QFileDialog.getSaveFileName",
                        return_value=(str(album), "Replacement-template folder (*)"),
                    ),
                    patch("mod_editor.apf_studio.gui.QMessageBox.information"),
                ):
                    browser._export_audio_replacement_template()
                self.assertEqual(
                    calls[-1], (album_rows, album, "folder", "xma1")
                )

                browser._toggle_soundtrack_album()
                browser._audio_shortlist.clear()
                browser._audio_shortlist[second.row_id] = second
                browser._audio_shortlist[first.row_id] = first
                browser._toggle_audio_review()
                reviewed = browser._audio_replacement_template_rows()
                self.assertEqual(reviewed, (second, first))
                self.assertIn(
                    "(2)", browser.export_audio_replacement_template_button.text()
                )
                with (
                    patch(
                        "mod_editor.apf_studio.gui.QFileDialog.getSaveFileName",
                        return_value=(
                            str(shortlist),
                            "Replacement-template folder (*)",
                        ),
                    ),
                    patch("mod_editor.apf_studio.gui.QMessageBox.information"),
                ):
                    browser._export_audio_replacement_template()
                self.assertEqual(
                    calls[-1], ((second, first), shortlist, "folder", "xma1")
                )

                pcm = Path(directory) / "pcm-pack"
                browser.audio_replacement_pack_input.setCurrentIndex(
                    browser.audio_replacement_pack_input.findData("pcm16")
                )
                self.assertEqual(
                    browser.audio_replacement_pack_input.currentText(),
                    "Exact PCM16 WAV",
                )
                self.assertEqual(
                    browser.audio_replacement_pack_input.accessibleName(),
                    "APF audio replacement template input format",
                )
                self.assertIn(
                    "PCM16 WAV folder",
                    browser.export_audio_replacement_template_button.text(),
                )
                with (
                    patch(
                        "mod_editor.apf_studio.gui.QFileDialog.getSaveFileName",
                        return_value=(str(pcm), "Replacement-template folder (*)"),
                    ),
                    patch(
                        "mod_editor.apf_studio.gui.QMessageBox.information"
                    ) as information,
                ):
                    browser._export_audio_replacement_template()
                self.assertEqual(
                    calls[-1], ((second, first), pcm, "folder", "pcm16")
                )
                self.assertIn("pcm16/ paths", information.call_args.args[2])
                self.assertIn(
                    "FLAC and MP3 cannot be imported directly",
                    information.call_args.args[2],
                )
                self.assertIn(
                    "not copyright clearance", information.call_args.args[2]
                )
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_replacement_import_preserves_selection_emits_signals_and_receipt(self) -> None:
        rows = (self._pack_row(1), self._pack_row(2))
        received: dict[str, object] = {}

        def preview_pack(
            root: Path,
            progress: object,
            *,
            encoder: object | None = None,
            cancel_requested: object,
        ) -> object:
            received.update(
                preview_root=root,
                preview_encoder=encoder,
                preview_cancel_requested=cancel_requested,
            )
            progress("Validated preview 1 of 1", 1, 1)  # type: ignore[operator]
            return SimpleNamespace(
                template_entry_count=2,
                supplied_count=1,
                would_change_count=1,
                already_current_count=0,
                missing_count=1,
                current_modified_audio_count=0,
                resulting_modified_audio_count=1,
                validated_count=1,
                confirmation_token="e" * 64,
                was_cancelled=False,
                input_kind="xma1",
            )

        def import_pack(
            root: Path,
            progress: object,
            *,
            encoder: object | None = None,
            cancel_requested: object,
            confirmation_token: str,
        ) -> object:
            received.update(
                apply_root=root,
                apply_encoder=encoder,
                apply_cancel_requested=cancel_requested,
                confirmation_token=confirmation_token,
            )
            progress("Validated 1 of 1", 1, 1)  # type: ignore[operator]
            return SimpleNamespace(
                template_entry_count=2,
                supplied_count=1,
                staged_count=1,
                unchanged_count=0,
                missing_count=1,
                validated_count=1,
                was_cancelled=False,
                input_kind="xma1",
            )

        def run_task(
            _title: str,
            operation: object,
            complete: object,
            _blocking: bool,
        ) -> None:
            result = operation(lambda *_args: None)  # type: ignore[operator]
            complete(result)  # type: ignore[operator]

        browser = InspectorBrowser(
            "Complete audio",
            SimpleNamespace(
                preview_audio_replacement_pack=preview_pack,
                import_audio_replacement_pack=import_pack,
            ),
            run_task,
            audio_mode=True,
        )
        modified: list[str] = []
        started: list[str] = []
        finished: list[str] = []
        browser.modifiedChanged.connect(lambda: modified.append("modified"))
        browser.audioImportStarted.connect(lambda: started.append("started"))
        browser.audioImportFinished.connect(lambda: finished.append("finished"))
        try:
            browser.set_model(PagedModel(rows), "fixture")
            browser.table.selectRow(1)
            self.application.processEvents()
            with (
                patch(
                    "mod_editor.apf_studio.gui.QFileDialog.getExistingDirectory",
                    return_value="/user/replacement-pack",
                ),
                patch(
                    "mod_editor.apf_studio.gui.QMessageBox.information"
                ) as information,
                patch(
                    "mod_editor.apf_studio.gui.QMessageBox.question",
                    return_value=QMessageBox.Apply,
                ),
                patch.object(
                    browser, "_external_xma1_encoder", return_value=None
                ),
            ):
                browser._import_audio_replacement_pack()
                for _index in range(3):
                    self.application.processEvents()
            self.assertEqual(received["preview_root"], Path("/user/replacement-pack"))
            self.assertEqual(received["apply_root"], Path("/user/replacement-pack"))
            self.assertIsNone(received["apply_encoder"])
            self.assertFalse(received["apply_cancel_requested"]())  # type: ignore[operator]
            self.assertEqual(received["confirmation_token"], "e" * 64)
            self.assertEqual(started, ["started", "started"])
            self.assertEqual(finished, ["finished", "finished"])
            self.assertEqual(modified, ["modified"])
            self.assertEqual(browser._selected_row().row_id, rows[1].row_id)
            self.assertIn("Project edits changed: 1", information.call_args.args[2])
            self.assertFalse(browser._audio_import_running)
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_replacement_pack_zip_selector_routes_export_and_import(self) -> None:
        row = self._pack_row(1)
        calls: dict[str, object] = {}

        def export_template(
            rows: tuple[object, ...],
            destination: Path,
            _progress: object,
            *,
            container: str,
            input_kind: str = "xma1",
        ) -> object:
            calls.update(
                export_rows=tuple(rows),
                destination=destination,
                container=container,
                input_kind=input_kind,
            )
            return SimpleNamespace(
                path=destination,
                entry_count=len(tuple(rows)),
                container=container,
                input_kind=input_kind,
            )

        def preview_pack(
            root: Path,
            _progress: object,
            *,
            encoder: object | None = None,
            cancel_requested: object,
        ) -> object:
            calls.update(
                preview_root=root,
                preview_encoder=encoder,
                preview_cancel_requested=cancel_requested,
            )
            return SimpleNamespace(
                template_entry_count=1,
                supplied_count=1,
                would_change_count=1,
                already_current_count=0,
                missing_count=0,
                current_modified_audio_count=0,
                resulting_modified_audio_count=1,
                validated_count=1,
                confirmation_token="e" * 64,
                was_cancelled=False,
                input_kind="xma1",
            )

        def import_pack(
            root: Path,
            _progress: object,
            *,
            encoder: object | None = None,
            cancel_requested: object,
            confirmation_token: str,
        ) -> object:
            calls.update(
                import_root=root,
                encoder=encoder,
                cancel_requested=cancel_requested,
                confirmation_token=confirmation_token,
            )
            return SimpleNamespace(
                template_entry_count=1,
                supplied_count=1,
                staged_count=1,
                unchanged_count=0,
                missing_count=0,
                validated_count=1,
                was_cancelled=False,
                input_kind="xma1",
            )

        def run_task(
            _title: str,
            operation: object,
            complete: object,
            _blocking: bool,
        ) -> None:
            complete(operation(lambda *_args: None))  # type: ignore[operator]

        browser = InspectorBrowser(
            "Complete audio",
            SimpleNamespace(
                export_audio_replacement_template=export_template,
                preview_audio_replacement_pack=preview_pack,
                import_audio_replacement_pack=import_pack,
            ),
            run_task,
            audio_mode=True,
        )
        try:
            browser.set_model(PagedModel((row,)), "fixture")
            browser.audio_replacement_pack_format.setCurrentIndex(
                browser.audio_replacement_pack_format.findData("zip")
            )
            self.assertEqual(
                browser.audio_replacement_pack_format.accessibleName(),
                "APF audio replacement pack format",
            )
            self.assertIn("ZIP", browser.export_audio_replacement_template_button.text())
            with (
                patch(
                    "mod_editor.apf_studio.gui.QFileDialog.getSaveFileName",
                    return_value=("/user/apf-audio", "APF audio replacement template ZIP (*.zip)"),
                ),
                patch("mod_editor.apf_studio.gui.QMessageBox.information"),
            ):
                browser._export_audio_replacement_template()
            self.assertEqual(calls["destination"], Path("/user/apf-audio.zip"))
            self.assertEqual(calls["container"], "zip")
            self.assertEqual(calls["input_kind"], "xma1")

            with (
                patch(
                    "mod_editor.apf_studio.gui.QFileDialog.getOpenFileName",
                    return_value=("/user/edited.ZIP", "APF audio replacement pack ZIP (*.zip)"),
                ),
                patch("mod_editor.apf_studio.gui.QMessageBox.information"),
                patch(
                    "mod_editor.apf_studio.gui.QMessageBox.question",
                    return_value=QMessageBox.Apply,
                ),
                patch.object(
                    browser, "_external_xma1_encoder", return_value=None
                ),
            ):
                browser._import_audio_replacement_pack()
                for _index in range(3):
                    self.application.processEvents()
            self.assertEqual(calls["import_root"], Path("/user/edited.ZIP"))
            self.assertIsNone(calls["encoder"])
            self.assertFalse(calls["cancel_requested"]())  # type: ignore[operator]
            self.assertEqual(calls["confirmation_token"], "e" * 64)
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_replacement_import_cancel_is_atomic_and_keeps_selection(self) -> None:
        rows = (self._pack_row(1), self._pack_row(2))
        browser: InspectorBrowser

        def preview_pack(
            _root: Path,
            _progress: object,
            *,
            encoder: object | None = None,
            cancel_requested: object,
        ) -> object:
            self.assertTrue(browser._audio_import_running)
            self.assertTrue(browser.cancel_audio_import_button.isEnabled())
            self.assertFalse(browser.audio_replacement_pack_input.isEnabled())
            self.assertFalse(browser.audio_replacement_pack_format.isEnabled())
            self.assertIsNone(encoder)
            browser._cancel_running_audio_import()
            self.assertTrue(cancel_requested())  # type: ignore[operator]
            return SimpleNamespace(
                template_entry_count=2,
                supplied_count=2,
                would_change_count=0,
                already_current_count=0,
                missing_count=0,
                current_modified_audio_count=0,
                resulting_modified_audio_count=0,
                validated_count=1,
                confirmation_token="",
                was_cancelled=True,
                input_kind="pcm16",
            )

        def run_task(
            _title: str,
            operation: object,
            complete: object,
            _blocking: bool,
        ) -> None:
            result = operation(lambda *_args: None)  # type: ignore[operator]
            complete(result)  # type: ignore[operator]

        browser = InspectorBrowser(
            "Complete audio",
            SimpleNamespace(preview_audio_replacement_pack=preview_pack),
            run_task,
            audio_mode=True,
        )
        modified: list[str] = []
        browser.modifiedChanged.connect(lambda: modified.append("modified"))
        try:
            browser.set_model(PagedModel(rows), "fixture")
            browser.table.selectRow(1)
            self.application.processEvents()
            with (
                patch(
                    "mod_editor.apf_studio.gui.QFileDialog.getExistingDirectory",
                    return_value="/user/replacement-pack",
                ),
                patch(
                    "mod_editor.apf_studio.gui.QMessageBox.information"
                ) as information,
                patch.object(
                    browser, "_external_xma1_encoder", return_value=None
                ),
            ):
                browser._import_audio_replacement_pack()
                for _index in range(2):
                    self.application.processEvents()
            self.assertEqual(modified, [])
            self.assertEqual(browser._selected_row().row_id, rows[1].row_id)
            self.assertIn("No project edits changed", information.call_args.args[2])
            self.assertIn("1 of 2", information.call_args.args[2])
            self.assertIn("PCM16 WAV files", information.call_args.args[2])
            self.assertFalse(browser._audio_import_running)
            self.assertFalse(browser.cancel_audio_import_button.isEnabled())
            self.assertTrue(browser.audio_replacement_pack_input.isEnabled())
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_player_command_never_uses_a_shell(self) -> None:
        resolved = {"ffplay": "/usr/bin/ffplay"}
        executable, arguments = _audio_player_command(
            Path("/private/preview.wav"), resolved.get
        )
        self.assertEqual(executable, "/usr/bin/ffplay")
        # The player command stringifies the path, so the final argument reads
        # back with the running OS's separator (backslashes on Windows). Compare
        # as Path so "the preview path is the last argument" holds on every OS
        # while the shell-free contract below is still asserted exactly.
        self.assertEqual(Path(arguments[-1]), Path("/private/preview.wav"))
        self.assertNotIn("sh", executable)

    def test_stale_audio_preview_success_after_selection_change_never_starts(
        self,
    ) -> None:
        rows = (self._playable_row(1), self._playable_row(2))
        queued: dict[str, object] = {}
        enqueued: list[object] = []

        def run_task(
            title: str,
            operation: object,
            complete: object,
            blocking: bool,
        ) -> None:
            enqueued.append(operation)
            queued.update(
                title=title,
                operation=operation,
                complete=complete,
                blocking=blocking,
            )

        browser = InspectorBrowser(
            "Complete audio",
            SimpleNamespace(),
            run_task,
            audio_mode=True,
        )
        try:
            browser.set_model(PagedModel(rows), "fixture")
            self.assertEqual(browser._selected_row(), rows[0])
            browser._play_or_stop_audio()
            self.assertEqual(
                queued["title"], "Preparing private APF audio preview"
            )
            self.assertIsNotNone(browser._audio_preview_request)

            browser.table.selectRow(1)
            self.application.processEvents()
            self.assertEqual(browser._selected_row(), rows[1])
            self.assertIsNone(browser._audio_preview_request)
            self.assertIsNotNone(browser._audio_preview_job)
            assert browser._audio_preview_job is not None
            self.assertTrue(browser._audio_preview_job[1].is_set())
            self.assertEqual(browser.play_audio_button.text(), "Cancelling…")
            self.assertFalse(browser.play_audio_button.isEnabled())

            # The cancelled worker still owns the blocking lane until its
            # completion signal drains. Clicking the disabled action through a
            # direct test call must not enqueue a second preview or leave a new
            # row stuck in Preparing state.
            browser._play_or_stop_audio()
            self.assertEqual(len(enqueued), 1)

            process = browser._audio_process
            self.assertIsNotNone(process)
            assert process is not None
            with (
                patch(
                    "mod_editor.apf_studio.gui._audio_player_command"
                ) as player_command,
                patch.object(process, "start") as start,
            ):
                complete = queued["complete"]
                complete(  # type: ignore[operator]
                    (True, Path("/private/stale-preview.wav"))
                )
            player_command.assert_not_called()
            start.assert_not_called()
            self.assertIsNone(browser._playing_audio_request)
            self.assertIsNone(browser._audio_preview_job)
            self.assertEqual(browser.play_audio_button.text(), "Play")
            self.assertTrue(browser.play_audio_button.isEnabled())

            browser._play_or_stop_audio()
            self.assertEqual(len(enqueued), 2)
            self.assertEqual(browser.play_audio_button.text(), "Cancel preview")
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_current_audio_preview_prepare_failure_resets_and_warns_once(
        self,
    ) -> None:
        row = self._playable_row(1)
        queued: dict[str, object] = {}

        callbacks: list[object] = []

        def prepare_audio_preview(
            *_args: object, cancel_requested: object
        ) -> Path:
            callbacks.append(cancel_requested)
            raise RuntimeError("fixture decoder failed")

        def run_task(
            title: str,
            operation: object,
            complete: object,
            blocking: bool,
        ) -> None:
            queued.update(
                title=title,
                operation=operation,
                complete=complete,
                blocking=blocking,
            )

        browser = InspectorBrowser(
            "Complete audio",
            SimpleNamespace(prepare_audio_preview=prepare_audio_preview),
            run_task,
            audio_mode=True,
        )
        try:
            browser.set_model(PagedModel((row,)), "fixture")
            browser._play_or_stop_audio()
            self.assertIsNotNone(browser._audio_preview_request)
            self.assertIsNotNone(browser._audio_preview_job)
            self.assertEqual(browser.play_audio_button.text(), "Cancel preview")
            self.assertTrue(browser.play_audio_button.isEnabled())
            operation = queued["operation"]
            result = operation(lambda *_args: None)  # type: ignore[operator]
            self.assertEqual(result, (False, "fixture decoder failed"))
            self.assertEqual(len(callbacks), 1)
            self.assertFalse(callbacks[0]())  # type: ignore[operator]

            with patch(
                "mod_editor.apf_studio.gui.QMessageBox.warning"
            ) as warning:
                complete = queued["complete"]
                complete(result)  # type: ignore[operator]
            warning.assert_called_once()
            self.assertEqual(warning.call_args.args[1], "Could not prepare audio")
            self.assertEqual(warning.call_args.args[2], "fixture decoder failed")
            self.assertIsNone(browser._audio_preview_request)
            self.assertIsNone(browser._audio_preview_job)
            self.assertIsNone(browser._playing_audio_request)
            self.assertEqual(browser.play_audio_button.text(), "Play")
            self.assertTrue(browser.play_audio_button.isEnabled())
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_rejected_audio_preview_admission_immediately_restores_play(
        self,
    ) -> None:
        row = self._playable_row(1)
        calls: list[tuple[object, object]] = []

        def run_task(
            _title: str,
            operation: object,
            complete: object,
            _blocking: bool,
        ) -> bool:
            calls.append((operation, complete))
            return False

        browser = InspectorBrowser(
            "Complete audio",
            SimpleNamespace(),
            run_task,
            audio_mode=True,
        )
        try:
            browser.set_model(PagedModel((row,)), "fixture")
            browser._play_or_stop_audio()

            self.assertEqual(len(calls), 1)
            self.assertIsNone(browser._audio_preview_request)
            self.assertIsNone(browser._audio_preview_job)
            self.assertIsNone(browser._playing_audio_request)
            self.assertEqual(browser.play_audio_button.text(), "Play")
            self.assertTrue(browser.play_audio_button.isEnabled())
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_current_audio_preview_cancel_is_cooperative_silent_and_reusable(
        self,
    ) -> None:
        row = self._playable_row(1)
        queued: dict[str, object] = {}
        enqueued: list[object] = []
        callbacks: list[object] = []

        def prepare_audio_preview(
            *_args: object, cancel_requested: object
        ) -> Path:
            callbacks.append(cancel_requested)
            if cancel_requested():  # type: ignore[operator]
                raise RuntimeError("preview cancelled")
            return Path("/private/preview.wav")

        def run_task(
            title: str,
            operation: object,
            complete: object,
            blocking: bool,
        ) -> None:
            enqueued.append(operation)
            queued.update(
                title=title,
                operation=operation,
                complete=complete,
                blocking=blocking,
            )

        browser = InspectorBrowser(
            "Complete audio",
            SimpleNamespace(prepare_audio_preview=prepare_audio_preview),
            run_task,
            audio_mode=True,
        )
        try:
            browser.set_model(PagedModel((row,)), "fixture")
            browser._play_or_stop_audio()
            self.assertEqual(browser.play_audio_button.text(), "Cancel preview")
            self.assertTrue(browser.play_audio_button.isEnabled())

            browser._play_or_stop_audio()
            self.assertEqual(browser.play_audio_button.text(), "Cancelling…")
            self.assertFalse(browser.play_audio_button.isEnabled())
            self.assertEqual(len(enqueued), 1)

            operation = queued["operation"]
            result = operation(lambda *_args: None)  # type: ignore[operator]
            self.assertEqual(result, (False, ""))
            self.assertEqual(len(callbacks), 1)
            self.assertTrue(callbacks[0]())  # type: ignore[operator]

            with patch(
                "mod_editor.apf_studio.gui.QMessageBox.warning"
            ) as warning:
                complete = queued["complete"]
                complete(result)  # type: ignore[operator]
            warning.assert_not_called()
            self.assertIsNone(browser._audio_preview_request)
            self.assertIsNone(browser._audio_preview_job)
            self.assertEqual(browser.play_audio_button.text(), "Play")
            self.assertTrue(browser.play_audio_button.isEnabled())

            # Draining the cancelled blocking job makes this row immediately
            # reusable instead of leaving a false Preparing state behind.
            browser._play_or_stop_audio()
            self.assertEqual(len(enqueued), 2)
            self.assertEqual(browser.play_audio_button.text(), "Cancel preview")
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_source_transition_cancels_preview_and_late_failure_is_silent(
        self,
    ) -> None:
        row = self._playable_row(1)
        queued: dict[str, object] = {}

        def run_task(
            title: str,
            operation: object,
            complete: object,
            blocking: bool,
        ) -> None:
            queued.update(
                title=title,
                operation=operation,
                complete=complete,
                blocking=blocking,
            )

        browser = InspectorBrowser(
            "Complete audio",
            SimpleNamespace(),
            run_task,
            audio_mode=True,
        )
        try:
            browser.set_model(PagedModel((row,)), "fixture")
            browser._play_or_stop_audio()
            job = browser._audio_preview_job
            self.assertIsNotNone(job)
            assert job is not None

            browser.set_loading("Loading a different APF game…")
            self.assertTrue(job[1].is_set())
            self.assertIs(browser._audio_preview_job, job)
            self.assertIsNone(browser._audio_preview_request)
            self.assertEqual(browser.play_audio_button.text(), "Cancelling…")
            self.assertFalse(browser.play_audio_button.isEnabled())

            with patch(
                "mod_editor.apf_studio.gui.QMessageBox.warning"
            ) as warning:
                complete = queued["complete"]
                complete((False, "obsolete source decoder failure"))  # type: ignore[operator]
            warning.assert_not_called()
            self.assertIsNone(browser._audio_preview_job)
            self.assertEqual(browser.play_audio_button.text(), "Play")
            self.assertFalse(browser.play_audio_button.isEnabled())
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_stale_audio_preview_prepare_failure_after_selection_change_is_silent(
        self,
    ) -> None:
        rows = (self._playable_row(1), self._playable_row(2))
        queued: dict[str, object] = {}

        def run_task(
            title: str,
            operation: object,
            complete: object,
            blocking: bool,
        ) -> None:
            queued.update(
                title=title,
                operation=operation,
                complete=complete,
                blocking=blocking,
            )

        browser = InspectorBrowser(
            "Complete audio",
            SimpleNamespace(),
            run_task,
            audio_mode=True,
        )
        try:
            browser.set_model(PagedModel(rows), "fixture")
            browser._play_or_stop_audio()
            self.assertIsNotNone(browser._audio_preview_request)
            browser.table.selectRow(1)
            self.application.processEvents()
            self.assertIsNone(browser._audio_preview_request)

            with patch(
                "mod_editor.apf_studio.gui.QMessageBox.warning"
            ) as warning:
                complete = queued["complete"]
                complete((False, "obsolete decoder failure"))  # type: ignore[operator]
            warning.assert_not_called()
            self.assertEqual(browser._selected_row(), rows[1])
            self.assertIsNone(browser._audio_preview_request)
            self.assertIsNone(browser._playing_audio_request)
            self.assertEqual(browser.play_audio_button.text(), "Play")
            self.assertTrue(browser.play_audio_button.isEnabled())
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_audio_workspace_uses_full_height_tabs_not_a_squeezed_splitter(self) -> None:
        page = InspectorCategoryPage(
            SimpleNamespace(),
            ApfCategory.AUDIO,
            lambda *_args, **_kwargs: None,
            "Complete audio",
            lambda _service: ("fixture", PagedModel(())),
        )
        try:
            # The exact visible labels are the durable UX contract; raw assets
            # remain universally reachable without sharing vertical height.
            from PyQt5.QtWidgets import QTabWidget

            workspace = page.findChild(QTabWidget, "workspaceTabs")
            self.assertIsNotNone(workspace)
            self.assertEqual(workspace.count(), 2)
            self.assertEqual(workspace.tabText(0), "Audio Browser")
            self.assertEqual(workspace.tabText(1), "Raw Audio Assets")
        finally:
            page.deleteLater()
            self.application.processEvents()


if __name__ == "__main__":
    unittest.main()
