from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
import zipfile

from mod_editor.apf_studio.audio_batch_export import AudioBatchExportError
from mod_editor.apf_studio.facade import ApfStudioFacade, FacadeError
from mod_editor.apf_studio.inspectors import ExportIdentity, InspectorRow


SOURCE_SHA256 = "a7" * 32


def audio_row(index: int) -> InspectorRow:
    return InspectorRow(
        row_id=f"audio:{index}",
        kind="audo",
        title=f"Sound {index}",
        subtitle="Facade fixture",
        fields={},
        export_identity=ExportIdentity(
            "audo",
            9,
            index,
            None,
            f"sound-{index}",
            (".xma", ".wav"),
        ),
        _search_text="",
    )


class RoutedAssetIO:
    def __init__(self) -> None:
        self.calls: list[tuple[ExportIdentity, Path]] = []

    def export_audio_identity(
        self, identity: ExportIdentity, destination: Path
    ) -> Path:
        self.calls.append((identity, destination))
        destination.write_bytes(
            f"routed:{identity.outer_table_index}:{identity.inner_file_index}".encode(
                "ascii"
            )
        )
        return destination


class FakeSession:
    def __init__(self, asset_io: RoutedAssetIO, modified_count: int = 4) -> None:
        self.asset_io = asset_io
        self.modified_count = modified_count


def loaded_facade(
    route: RoutedAssetIO,
) -> tuple[ApfStudioFacade, FakeSession]:
    facade = ApfStudioFacade()
    session = FakeSession(route)
    facade.source = SimpleNamespace(source_sha256=SOURCE_SHA256)
    facade.session = session  # type: ignore[assignment]
    return facade, session


class ApfAudioBatchFacadeTests(unittest.TestCase):
    def test_routes_wav_rows_with_source_fingerprint_and_read_only_state(self) -> None:
        route = RoutedAssetIO()
        facade, session = loaded_facade(route)
        previous_build = object()
        facade.last_build = previous_build  # type: ignore[assignment]
        progress: list[tuple[str, int, int]] = []

        with tempfile.TemporaryDirectory() as name:
            destination = Path(name) / "selected-audio.zip"
            before = facade.modified_count
            receipt = facade.export_audio_batch(
                (audio_row(2), audio_row(5)),
                destination,
                output_extension=".wav",
                batch_name="My selected sounds",
                progress=lambda stage, completed, total: progress.append(
                    (stage, completed, total)
                ),
            )
            with zipfile.ZipFile(destination) as archive:
                manifest_bytes = archive.read("manifest.json")
                manifest = json.loads(manifest_bytes)

            self.assertEqual(receipt.path, destination)
            self.assertEqual(receipt.output_extension, ".wav")
            self.assertEqual((receipt.requested, receipt.succeeded), (2, 2))
            self.assertEqual(
                [call[0] for call in route.calls],
                [audio_row(2).export_identity, audio_row(5).export_identity],
            )
            self.assertTrue(all(path.suffix == ".wav" for _identity, path in route.calls))
            self.assertEqual(manifest["source_sha256"], SOURCE_SHA256)
            self.assertEqual(manifest["batch_name"], "My selected sounds")
            self.assertEqual(
                receipt.archive_sha256,
                hashlib.sha256(destination.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                receipt.manifest_sha256, hashlib.sha256(manifest_bytes).hexdigest()
            )

        self.assertEqual(facade.modified_count, before)
        self.assertEqual(session.modified_count, 4)
        self.assertIs(facade.last_build, previous_build)
        self.assertEqual(progress[0], ("Preparing APF audio batch export", 0, 2))
        self.assertEqual(progress[-1][1:], (2, 2))
        self.assertIn("complete", progress[-1][0])
        self.assertIn("2 exported", progress[-1][0])

    def test_optional_cancellation_is_forwarded_and_explained_in_progress(self) -> None:
        route = RoutedAssetIO()
        facade, _session = loaded_facade(route)
        progress: list[tuple[str, int, int]] = []

        with tempfile.TemporaryDirectory() as name:
            receipt = facade.export_audio_batch(
                (audio_row(1), audio_row(2), audio_row(3)),
                Path(name) / "partial.zip",
                cancel_requested=lambda: len(route.calls) >= 1,
                progress=lambda stage, completed, total: progress.append(
                    (stage, completed, total)
                ),
            )

        self.assertTrue(receipt.was_cancelled)
        self.assertEqual((receipt.succeeded, receipt.cancelled), (1, 2))
        self.assertEqual(len(route.calls), 1)
        self.assertEqual(progress[-1][1:], (3, 3))
        self.assertIn("cancelled", progress[-1][0])
        self.assertIn("2 skipped", progress[-1][0])

    def test_requires_a_loaded_source_and_rejects_invalid_batch_requests(self) -> None:
        unloaded = ApfStudioFacade()
        with tempfile.TemporaryDirectory() as name:
            destination = Path(name) / "unloaded.zip"
            with self.assertRaisesRegex(FacadeError, "Load your APF 2K8 game first"):
                unloaded.export_audio_batch((audio_row(1),), destination)
            self.assertFalse(destination.exists())

        route = RoutedAssetIO()
        facade, session = loaded_facade(route)
        with tempfile.TemporaryDirectory() as name:
            destination = Path(name) / "invalid.zip"
            with self.assertRaisesRegex(AudioBatchExportError, "original .xma"):
                facade.export_audio_batch(
                    (audio_row(1),), destination, output_extension=".mp3"
                )
            self.assertFalse(destination.exists())

        self.assertEqual(route.calls, [])
        self.assertEqual(session.modified_count, 4)


if __name__ == "__main__":
    unittest.main()
