"""Headless product tests for APF's selected-sound audio drop target."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import sip  # noqa: E402
from PyQt5.QtCore import QMimeData, QSettings, QUrl  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.apf_studio.audio_encoding import ExternalXma1Encoder  # noqa: E402
from mod_editor.apf_studio.gui import (  # noqa: E402
    AUDIO_DIRECT_DROP_CONTRACT,
    AudioReplacementDropZone,
    InspectorBrowser,
)
from mod_editor.apf_studio.inspectors import (  # noqa: E402
    ExportIdentity,
    InspectorRow,
    PagedModel,
    _row,
)


class _DropEvent:
    """Small drag/drop event double with observable admission state."""

    def __init__(self, mime: QMimeData) -> None:
        self._mime = mime
        self.accepted = False
        self.ignored = False

    def mimeData(self) -> QMimeData:  # noqa: N802 - Qt-compatible test double
        return self._mime

    def acceptProposedAction(self) -> None:  # noqa: N802 - Qt callback
        self.accepted = True
        self.ignored = False

    def ignore(self) -> None:
        self.accepted = False
        self.ignored = True


def _mime(*urls: QUrl) -> QMimeData:
    mime = QMimeData()
    mime.setUrls(list(urls))
    return mime


def _local_mime(*paths: Path) -> QMimeData:
    return _mime(*(QUrl.fromLocalFile(str(path)) for path in paths))


def _editable_row(index: int = 1) -> InspectorRow:
    identity = ExportIdentity("audo", 5, index, None, f"drop-{index:03d}")
    return _row(
        f"apf:audio:audo:5:{index}",
        "audo",
        f"Drop fixture {index}",
        "Synthetic standalone sound",
        {
            "outer_table_index": 5,
            "inner_file_index": index,
            "audio_source_id": "audo:standalone",
            "audio_source_label": "Standalone AUDO",
            "role_id": "ui_menu_sfx",
            "role_label": "UI & Menu SFX",
            "audio_format": "XMA1",
            "sample_rate": 22_050,
            "derived_channel_count": 1,
            "duration_seconds": 1.0,
            "encoded_size": 0x1800,
            "declared_sample_count": 21_604,
        },
        export_identity=identity,
    )


def _bank_row() -> InspectorRow:
    return _row(
        "apf:audio:ausb:8:2",
        "ausb_bank",
        "jukeboxmusic",
        "15 substreams",
        {
            "outer_table_index": 8,
            "inner_file_index": 2,
            "substream_count": 15,
            "audio_source_id": "ausb:8:2",
            "audio_source_label": "jukeboxmusic · O8/I2",
            "role_id": "soundtrack_music",
            "role_label": "Soundtrack & Music",
            "sample_rate": 48_000,
            "derived_channel_count": 2,
        },
    )


def _noneditable_row() -> InspectorRow:
    return _row(
        "apf:audio:index:0",
        "audo_index",
        "AUDO index",
        "Container metadata",
        {
            "outer_table_index": 5,
            "inner_file_index": 0,
            "audio_source_id": "audo:index",
            "audio_source_label": "AUDO index",
            "role_id": "other_audio",
            "role_label": "Other Audio",
        },
    )


class _DropFacade:
    def __init__(self) -> None:
        self.modified_asset_ids: frozenset[str] = frozenset()
        self.audo_calls: list[tuple[ExportIdentity, Path]] = []
        self.pcm_calls: list[dict[str, object]] = []

    def replace_audo_exact_slot(
        self,
        identity: ExportIdentity,
        source: Path,
        progress: object,
    ) -> object:
        self.audo_calls.append((identity, source))
        progress("Synthetic exact-slot replacement", 1, 1)  # type: ignore[operator]
        return SimpleNamespace(validated=True)

    def replace_ausb_exact_slot(self, *_args: object) -> object:
        raise AssertionError("Standalone drop routed to the AUSB writer")

    def replace_audio_from_pcm(
        self,
        identity: ExportIdentity,
        source: Path,
        encoder: ExternalXma1Encoder,
        progress: object,
        *,
        cancel_requested: object,
    ) -> object:
        self.pcm_calls.append(
            {
                "identity": identity,
                "source": source,
                "encoder": encoder,
                "cancel_requested": cancel_requested,
            }
        )
        if cancel_requested():  # type: ignore[operator]
            raise AssertionError("Fresh PCM drop unexpectedly began cancelled")
        progress("Synthetic PCM bridge", 1, 1)  # type: ignore[operator]
        self.modified_asset_ids = frozenset(
            (
                f"apf:audio:audo:{identity.outer_table_index}:"
                f"{identity.inner_file_index}",
            )
        )
        return SimpleNamespace(validated=True)


class ApfAudioDropZoneGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.application.quit()
        sip.delete(cls.application)
        cls.application = None

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="apf-audio-drop-gui-")
        self.root = Path(self.temporary.name)
        self.settings = QSettings(
            str(self.root / "audio-drop.ini"), QSettings.IniFormat
        )
        self.settings.clear()
        self.settings.sync()
        self.widgets: list[object] = []

    def tearDown(self) -> None:
        for widget in reversed(self.widgets):
            widget.close()  # type: ignore[attr-defined]
            sip.delete(widget)
        self.settings.clear()
        self.settings.sync()
        self.temporary.cleanup()

    def _browser(
        self,
        rows: tuple[InspectorRow, ...],
        *,
        facade: _DropFacade | None = None,
        synchronous: bool = True,
    ) -> tuple[
        InspectorBrowser,
        _DropFacade,
        list[dict[str, object]],
        list[Exception],
    ]:
        selected_facade = facade or _DropFacade()
        tasks: list[dict[str, object]] = []
        errors: list[Exception] = []

        def run_task(
            title: str,
            operation: object,
            complete: object,
            blocking: bool,
        ) -> None:
            task = {
                "title": title,
                "operation": operation,
                "complete": complete,
                "blocking": blocking,
            }
            tasks.append(task)
            if not synchronous:
                return
            try:
                result = operation(lambda *_args: None)  # type: ignore[operator]
            except Exception as exc:
                errors.append(exc)
                return
            complete(result)  # type: ignore[operator]

        browser = InspectorBrowser(
            "Complete audio inventory",
            selected_facade,  # type: ignore[arg-type]
            run_task,
            audio_mode=True,
            audio_settings=self.settings,
        )
        browser.set_model(PagedModel(rows), f"{len(rows)} synthetic audio rows")
        browser.table.selectRow(0)
        self.application.processEvents()
        self.widgets.append(browser)
        return browser, selected_facade, tasks, errors

    def test_drop_zone_is_visible_and_tracks_exact_slot_editability(self) -> None:
        browser, _facade, _tasks, _errors = self._browser(
            (_editable_row(), _bank_row(), _noneditable_row())
        )
        zone = browser.audio_replacement_drop_zone

        self.assertEqual(
            AUDIO_DIRECT_DROP_CONTRACT,
            "selected_exact_slot_xma1_or_pcm16_wav",
        )
        self.assertFalse(zone.isHidden())
        self.assertTrue(zone.isVisibleTo(browser))
        self.assertTrue(zone.isEnabled())
        self.assertEqual(zone.property("dropReady"), True)
        self.assertIn("Drop .xma", zone.title.text())

        browser.table.selectRow(1)
        self.application.processEvents()
        self.assertFalse(zone.isHidden())
        self.assertFalse(zone.isEnabled())
        self.assertEqual(zone.property("dropReady"), False)
        self.assertIn("Raw banks", zone.hint.text())

        browser.table.selectRow(2)
        self.application.processEvents()
        self.assertFalse(zone.isEnabled())
        self.assertIn("Select an Editable sound", zone.title.text())

    def test_file_admission_accepts_one_regular_local_audio_file_only(self) -> None:
        zone = AudioReplacementDropZone()
        zone.set_available(True)
        self.widgets.append(zone)
        dropped: list[Path] = []
        zone.audioDropped.connect(dropped.append)

        upper_xma = self.root / "replacement.XMA"
        mixed_wav = self.root / "replacement.WaV"
        upper_xma.write_bytes(b"synthetic XMA")
        mixed_wav.write_bytes(b"synthetic WAV")
        for path in (upper_xma, mixed_wav):
            with self.subTest(accepted=path.name):
                drag = _DropEvent(_local_mime(path))
                zone.dragEnterEvent(drag)
                self.assertTrue(drag.accepted)
                drop = _DropEvent(_local_mime(path))
                zone.dropEvent(drop)
                self.assertTrue(drop.accepted)
                self.assertEqual(dropped[-1], path)

        wrong = self.root / "replacement.mp3"
        wrong.write_bytes(b"synthetic MP3")
        directory = self.root / "folder.xma"
        directory.mkdir()
        symlink = self.root / "linked.wav"
        symlink.symlink_to(mixed_wav)
        invalid = {
            "multiple local URLs": _local_mime(upper_xma, mixed_wav),
            "remote URL": _mime(QUrl("https://example.invalid/replacement.xma")),
            "remote-host file URL": _mime(
                QUrl("file://remote-host/tmp/replacement.xma")
            ),
            "wrong extension": _local_mime(wrong),
            "directory": _local_mime(directory),
            "symlink": _local_mime(symlink),
        }
        admitted_count = len(dropped)
        for label, mime in invalid.items():
            with self.subTest(rejected=label):
                self.assertIsNone(AudioReplacementDropZone.local_audio_path(mime))
                drag = _DropEvent(mime)
                zone.dragEnterEvent(drag)
                self.assertTrue(drag.ignored)
                drop = _DropEvent(mime)
                zone.dropEvent(drop)
                self.assertTrue(drop.ignored)
                self.assertEqual(len(dropped), admitted_count)

    def test_xma_drop_captures_selected_identity_and_matches_button_route(self) -> None:
        first = _editable_row(4)
        second = _editable_row(9)
        browser, facade, tasks, _errors = self._browser(
            (first, second), synchronous=False
        )
        source = self.root / "user-authored.XmA"
        source.write_bytes(b"synthetic user XMA1")

        drop = _DropEvent(_local_mime(source))
        browser.audio_replacement_drop_zone.dropEvent(drop)
        self.assertTrue(drop.accepted)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(
            tasks[0]["title"], "Validating exact-slot APF XMA1 replacement"
        )

        # Change selection before the queued operation runs. The task must keep
        # the row identity that owned the drop, never retarget the new row.
        browser.table.selectRow(1)
        self.application.processEvents()
        tasks[0]["operation"](lambda *_args: None)  # type: ignore[operator]
        self.assertEqual(facade.audo_calls, [(first.export_identity, source)])

        browser.table.selectRow(0)
        self.application.processEvents()
        with patch(
            "mod_editor.apf_studio.gui.QFileDialog.getOpenFileName",
            return_value=(str(source), "RIFF XMA1 audio (*.xma)"),
        ):
            browser._replace_audio()
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[1]["title"], tasks[0]["title"])
        tasks[1]["operation"](lambda *_args: None)  # type: ignore[operator]
        self.assertEqual(
            facade.audo_calls,
            [(first.export_identity, source), (first.export_identity, source)],
        )

    def test_wav_drop_uses_configured_encoder_and_pcm_bridge(self) -> None:
        row = _editable_row(12)
        browser, facade, tasks, errors = self._browser((row,))
        encoder_tool = self.root / "fixture-encoder"
        encoder_tool.write_bytes(b"synthetic executable")
        encoder_tool.chmod(0o700)
        configured = ExternalXma1Encoder(encoder_tool)
        browser._save_external_xma1_encoder(configured)
        source = self.root / "user-authored.WAV"
        source.write_bytes(b"synthetic PCM16 fixture")

        with patch("mod_editor.apf_studio.gui.QMessageBox.information"):
            drop = _DropEvent(_local_mime(source))
            browser.audio_replacement_drop_zone.dropEvent(drop)

        self.assertTrue(drop.accepted)
        self.assertEqual(errors, [])
        self.assertEqual(len(tasks), 1)
        self.assertEqual(
            tasks[0]["title"], "Encoding and validating exact-slot APF audio"
        )
        self.assertEqual(len(facade.pcm_calls), 1)
        call = facade.pcm_calls[0]
        self.assertEqual(call["identity"], row.export_identity)
        self.assertEqual(call["source"], source)
        self.assertEqual(call["encoder"].executable, encoder_tool)  # type: ignore[union-attr]
        self.assertTrue(callable(call["cancel_requested"]))
        self.assertTrue(browser.audio_replacement_drop_zone.isEnabled())

    def test_wav_drop_without_encoder_refuses_without_task_or_mutation(self) -> None:
        row = _editable_row(15)
        browser, facade, tasks, errors = self._browser((row,))
        source = self.root / "user-authored.wav"
        source.write_bytes(b"synthetic PCM16 fixture")

        with patch(
            "mod_editor.apf_studio.gui.QMessageBox.information"
        ) as information:
            drop = _DropEvent(_local_mime(source))
            browser.audio_replacement_drop_zone.dropEvent(drop)

        self.assertTrue(drop.accepted)
        self.assertEqual(tasks, [])
        self.assertEqual(errors, [])
        self.assertEqual(facade.pcm_calls, [])
        self.assertEqual(facade.audo_calls, [])
        self.assertEqual(facade.modified_asset_ids, frozenset())
        self.assertEqual(
            information.call_args.args[1], "Configure an XMA1 encoder first"
        )
        self.assertIn("no project data changed", information.call_args.args[2])

    def test_active_pcm_or_pack_import_blocks_drop_and_direct_dispatch(self) -> None:
        row = _editable_row(18)
        browser, facade, tasks, errors = self._browser((row,))
        source = self.root / "user-authored.xma"
        source.write_bytes(b"synthetic XMA1 fixture")

        facade.modified_asset_ids = frozenset({row.row_id})
        unchanged_modifications = facade.modified_asset_ids
        for flag in (
            "_pcm_encoding_running",
            "_audio_import_running",
            "_direct_audio_replacement_running",
        ):
            with self.subTest(active_operation=flag):
                setattr(browser, flag, True)
                browser._configure_audio_replacement(row)
                self.assertFalse(browser.audio_replacement_drop_zone.isEnabled())
                self.assertFalse(browser.export_pcm_template_button.isEnabled())
                self.assertFalse(browser.replace_pcm_audio_button.isEnabled())
                self.assertFalse(browser.configure_audio_encoder_button.isEnabled())
                self.assertFalse(browser.replace_audio_button.isEnabled())
                self.assertFalse(browser.revert_audio_button.isEnabled())
                self.assertFalse(
                    browser.export_audio_replacement_template_button.isEnabled()
                )
                self.assertFalse(
                    browser.import_audio_replacement_pack_button.isEnabled()
                )
                self.assertFalse(browser.audio_replacement_pack_format.isEnabled())
                self.assertFalse(browser.audio_replacement_pack_input.isEnabled())
                drop = _DropEvent(_local_mime(source))
                browser.audio_replacement_drop_zone.dropEvent(drop)
                self.assertTrue(drop.ignored)
                browser._replace_audio_drop(source)
                self.assertEqual(tasks, [])
                self.assertEqual(facade.audo_calls, [])
                self.assertEqual(
                    facade.modified_asset_ids, unchanged_modifications
                )
                setattr(browser, flag, False)
                browser._configure_audio_replacement(row)
                self.assertTrue(browser.audio_replacement_drop_zone.isEnabled())

        self.assertEqual(errors, [])

    def test_direct_drop_stays_disabled_until_registered_worker_is_idle(self) -> None:
        row = _editable_row(21)
        facade = _DropFacade()
        queued: dict[str, object] = {}
        idle_callbacks: list[object] = []
        worker_registered = True

        def run_when_idle(callback: object) -> None:
            if worker_registered:
                idle_callbacks.append(callback)
            else:
                callback()  # type: ignore[operator]

        def run_task(
            title: str,
            operation: object,
            complete: object,
            blocking: bool,
        ) -> bool:
            queued.update(
                title=title,
                operation=operation,
                complete=complete,
                blocking=blocking,
            )
            return True

        browser = InspectorBrowser(
            "Complete audio inventory",
            facade,  # type: ignore[arg-type]
            run_task,
            run_when_idle=run_when_idle,  # type: ignore[arg-type]
            audio_mode=True,
            audio_settings=self.settings,
        )
        browser.set_model(PagedModel((row,)), "1 synthetic audio row")
        browser.table.selectRow(0)
        self.application.processEvents()
        self.widgets.append(browser)
        source = self.root / "owned-worker.xma"
        source.write_bytes(b"synthetic XMA1 fixture")

        first = _DropEvent(_local_mime(source))
        browser.audio_replacement_drop_zone.dropEvent(first)
        self.assertTrue(first.accepted)
        self.assertTrue(browser._direct_audio_replacement_running)
        self.assertFalse(browser.audio_replacement_drop_zone.isEnabled())

        second = _DropEvent(_local_mime(source))
        browser.audio_replacement_drop_zone.dropEvent(second)
        self.assertTrue(second.ignored)
        self.assertEqual(len(facade.audo_calls), 0)

        result = queued["operation"](lambda *_args: None)  # type: ignore[operator]
        queued["complete"](result)  # type: ignore[operator]
        self.assertEqual(len(facade.audo_calls), 1)
        self.assertEqual(len(idle_callbacks), 1)
        self.assertTrue(browser._direct_audio_replacement_running)
        self.assertFalse(browser.audio_replacement_drop_zone.isEnabled())

        worker_registered = False
        idle_callbacks.pop()()  # type: ignore[operator]
        self.assertFalse(browser._direct_audio_replacement_running)
        self.assertTrue(browser.audio_replacement_drop_zone.isEnabled())

    def test_runner_refusal_is_explained_and_restores_drop_immediately(self) -> None:
        row = _editable_row(24)
        facade = _DropFacade()
        operations: list[object] = []

        def refuse_task(
            _title: str,
            operation: object,
            _complete: object,
            _blocking: bool,
        ) -> bool:
            operations.append(operation)
            return False

        browser = InspectorBrowser(
            "Complete audio inventory",
            facade,  # type: ignore[arg-type]
            refuse_task,
            audio_mode=True,
            audio_settings=self.settings,
        )
        browser.set_model(PagedModel((row,)), "1 synthetic audio row")
        browser.table.selectRow(0)
        self.application.processEvents()
        self.widgets.append(browser)
        source = self.root / "busy-refusal.xma"
        source.write_bytes(b"synthetic XMA1 fixture")

        with patch(
            "mod_editor.apf_studio.gui.QMessageBox.information"
        ) as information:
            drop = _DropEvent(_local_mime(source))
            browser.audio_replacement_drop_zone.dropEvent(drop)

        self.assertTrue(drop.accepted)
        self.assertEqual(len(operations), 1)
        self.assertEqual(facade.audo_calls, [])
        self.assertFalse(browser._direct_audio_replacement_running)
        self.assertTrue(browser.audio_replacement_drop_zone.isEnabled())
        self.assertEqual(information.call_args.args[1], "Audio is still working")
        self.assertIn("Nothing was staged", information.call_args.args[2])


if __name__ == "__main__":
    unittest.main()
