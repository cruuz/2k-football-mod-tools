from __future__ import annotations

import csv
import hashlib
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from mod_editor.apf_studio.audio_batch_export import (
    AudioBatchExportError,
    ApfAudioBatchExporter,
    MANIFEST_SCHEMA,
    MAX_BATCH_ROWS,
    audio_snapshot_rows,
)
from mod_editor.apf_studio.inspectors import (
    AudioSnapshot,
    ExportIdentity,
    InspectorRow,
    PagedModel,
)


def playable_row(
    index: int,
    *,
    kind: str = "audo",
    row_id: str | None = None,
    basename: str = "same-name",
    supported_extensions: tuple[str, ...] = (".xma", ".wav"),
    title: str | None = None,
    fields: dict[str, object] | None = None,
) -> InspectorRow:
    if kind == "audo":
        identity = ExportIdentity(
            "audo", 7, index, None, basename, supported_extensions
        )
    else:
        identity = ExportIdentity(
            "ausb_substream", 12, 4, index, basename, supported_extensions
        )
    return InspectorRow(
        row_id=row_id or f"row:{kind}:{index}",
        kind=kind,
        title=title or f"Sound {index}",
        subtitle="Fixture metadata",
        fields=fields
        if fields is not None
        else {
            "audio_source_id": (
                "audo:standalone" if kind == "audo" else "ausb:12:4"
            ),
            "audio_source_label": (
                "Standalone AUDO" if kind == "audo" else "jukeboxmusic · O12/I4"
            ),
            "role_id": (
                "general_sfx" if kind == "audo" else "soundtrack_music"
            ),
            "role_label": (
                "General / Unknown SFX"
                if kind == "audo"
                else "Soundtrack & Music"
            ),
            "role_basis": "Fixture evidence boundary.",
            "audio_format": "XMA1",
            "sample_rate": 48_000,
            "derived_channel_count": 2,
            "duration_seconds": 1.25 if kind == "audo" else None,
            "duration_seconds_candidate": 2.5 if kind != "audo" else None,
            "logical_track_number": index + 1 if kind != "audo" else None,
            "paired_bank_name": "jukebox22" if kind != "audo" else None,
            "paired_encoding_role": (
                "48 kHz stereo" if kind != "audo" else None
            ),
            "track_title_status": (
                "Unknown; artist and title are not guessed."
                if kind != "audo"
                else None
            ),
            "packet_count": 8 + index,
            "encoded_size": 16_384 + index,
            "range_length": 8_192 + index if kind != "audo" else None,
        },
        export_identity=identity,
        _search_text="",
    )


def metadata_row(kind: str, index: int) -> InspectorRow:
    return InspectorRow(
        row_id=f"row:{kind}:{index}",
        kind=kind,
        title=f"Metadata {index}",
        subtitle="Not one playable cue",
        fields={},
        export_identity=None,
        _search_text="",
    )


def read_manifest(path: Path) -> tuple[dict[str, object], tuple[str, ...]]:
    with zipfile.ZipFile(path) as archive:
        names = tuple(archive.namelist())
        manifest = json.loads(archive.read("manifest.json"))
    return manifest, names


def read_catalog(path: Path) -> list[dict[str, str]]:
    with zipfile.ZipFile(path) as archive:
        payload = archive.read("catalog.csv").decode("utf-8")
    return list(csv.DictReader(StringIO(payload)))


class FakeIdentityExporter:
    def __init__(self) -> None:
        self.calls: list[tuple[ExportIdentity, Path]] = []
        self.fail_inner: set[int] = set()
        self.make_symlink = False

    def export_audio_identity(
        self, identity: ExportIdentity, destination: Path
    ) -> Path:
        self.calls.append((identity, destination))
        if identity.inner_file_index in self.fail_inner:
            raise ValueError("fixture decoder rejected this sound")
        if self.make_symlink:
            target = destination.parent / "not-the-export.bin"
            target.write_bytes(b"untrusted test payload")
            destination.symlink_to(target)
        else:
            destination.write_bytes(
                (
                    f"test-audio:{identity.kind}:{identity.outer_table_index}:"
                    f"{identity.inner_file_index}:{identity.substream_index}"
                ).encode("ascii")
            )
        return destination


class ApfAudioBatchExportTests(unittest.TestCase):
    def test_snapshot_rows_include_every_semantic_family_in_product_order(self) -> None:
        audo = playable_row(1)
        index = metadata_row("ausb_bank", 2)
        substream = playable_row(3, kind="ausb_substream")
        physical = metadata_row("external_bank", 4)
        snapshot = AudioSnapshot(
            summary={
                "audo": 1,
                "ausb_banks": 1,
                "ausb_substreams": 1,
                "external_bins": 1,
            },
            audo=PagedModel((audo,)),
            ausb_banks=PagedModel((index,)),
            ausb_substreams=PagedModel((substream,)),
            external_banks=PagedModel((physical,)),
        )

        self.assertEqual(
            audio_snapshot_rows(snapshot), (audo, index, substream, physical)
        )

    def test_coordinate_paths_are_deterministic_and_ignore_colliding_names(self) -> None:
        exporter = FakeIdentityExporter()
        service = ApfAudioBatchExporter(exporter)
        rows = (
            playable_row(2, basename="same/name"),
            playable_row(9, basename="same/name"),
            playable_row(3, kind="ausb_substream", basename="same/name"),
        )
        with tempfile.TemporaryDirectory() as name:
            destination = Path(name) / "batch.zip"
            receipt = service.export_selected(
                rows,
                destination,
                source_sha256="1" * 64,
                batch_name="  Stable   fixture  ",
            )
            copy = Path(name) / "batch-copy.zip"
            second_receipt = service.export_selected(
                rows,
                copy,
                source_sha256="1" * 64,
                batch_name="  Stable   fixture  ",
            )
            manifest, names = read_manifest(destination)
            catalog = read_catalog(destination)

            self.assertEqual(receipt.succeeded, 3)
            self.assertEqual(receipt.failed, 0)
            self.assertEqual(destination.read_bytes(), copy.read_bytes())
            self.assertEqual(receipt.archive_sha256, second_receipt.archive_sha256)
            self.assertEqual(
                names,
                (
                    "audio/audo/o00007-i00002.xma",
                    "audio/audo/o00007-i00009.xma",
                    "audio/ausb/o00012-i00004/s00003.xma",
                    "catalog.csv",
                    "playlist.m3u8",
                    "manifest.json",
                ),
            )
            self.assertEqual(manifest["schema"], MANIFEST_SCHEMA)
            self.assertEqual(
                MANIFEST_SCHEMA, "apf2k8_mod_studio_audio_batch_export/v2"
            )
            self.assertEqual(manifest["batch_name"], "Stable fixture")
            self.assertEqual(manifest["source_sha256"], "1" * 64)
            self.assertEqual(manifest["counts"]["success"], 3)
            self.assertEqual(manifest["catalog"], "catalog.csv")
            self.assertEqual(manifest["catalog_record_count"], 3)
            self.assertEqual(manifest["playlist"], "playlist.m3u8")
            self.assertEqual(manifest["playlist_record_count"], 3)
            self.assertEqual(receipt.catalog_record_count, 3)
            self.assertEqual(receipt.playlist_record_count, 3)
            self.assertEqual([row["order"] for row in catalog], ["1", "2", "3"])
            self.assertEqual(
                [row["status"] for row in catalog],
                ["success", "success", "success"],
            )
            with zipfile.ZipFile(destination) as archive:
                self.assertEqual(
                    manifest["catalog_sha256"],
                    hashlib.sha256(archive.read("catalog.csv")).hexdigest(),
                )
                self.assertEqual(
                    manifest["playlist_sha256"],
                    hashlib.sha256(archive.read("playlist.m3u8")).hexdigest(),
                )
            expected_payloads = (
                b"test-audio:audo:7:2:None",
                b"test-audio:audo:7:9:None",
                b"test-audio:ausb_substream:12:4:3",
            )
            self.assertEqual(receipt.payload_bytes, sum(map(len, expected_payloads)))
            self.assertEqual(manifest["payload_bytes"], receipt.payload_bytes)
            for record, payload in zip(
                manifest["records"], expected_payloads, strict=True
            ):
                self.assertEqual(record["file_size"], len(payload))
                self.assertEqual(
                    record["file_sha256"], hashlib.sha256(payload).hexdigest()
                )
            metadata = manifest["records"][2]["metadata"]
            self.assertEqual(metadata["audio_source_id"], "ausb:12:4")
            self.assertEqual(metadata["role_id"], "soundtrack_music")
            self.assertEqual(metadata["audio_format"], "XMA1")
            self.assertEqual(metadata["sample_rate"], 48_000)
            self.assertEqual(metadata["channel_count"], 2)
            self.assertEqual(metadata["duration_seconds"], 2.5)
            self.assertEqual(metadata["duration_basis"], "ausb_boundary_candidate")
            self.assertEqual(metadata["logical_track_number"], 4)
            self.assertEqual(metadata["paired_bank_name"], "jukebox22")
            self.assertEqual(metadata["packet_count"], 11)
            self.assertEqual(metadata["encoded_size"], 16_387)
            self.assertEqual(metadata["range_length"], 8_195)
            self.assertFalse(
                manifest["capability_boundary"]["replacement_supported"]
            )
            self.assertIn(
                "does not encode XMA1",
                manifest["capability_boundary"]["replacement_note"],
            )
            self.assertEqual(
                receipt.archive_sha256,
                hashlib.sha256(destination.read_bytes()).hexdigest(),
            )

    def test_metadata_and_csv_text_are_control_and_formula_safe(self) -> None:
        fields = {
            "audio_source_id": "=SUM(1,\n2)\x00",
            "audio_source_label": "@source\rlabel",
            "role_id": "+role",
            "role_label": "-role",
            "role_basis": "\u202ehidden\tclaim",
            "audio_format": "=XMA1",
            "sample_rate": True,
            "derived_channel_count": -2,
            "duration_seconds": float("inf"),
            "logical_track_number": 0,
            "paired_bank_name": "@paired\nbank",
            "paired_encoding_role": "+stereo",
            "track_title_status": "=UNKNOWN",
            "packet_count": -1,
            "encoded_size": True,
            "range_length": 4,
        }
        row = playable_row(
            1,
            row_id="@row\nid",
            title="=HYPERLINK(\"bad\")\nnext",
            fields=fields,
        )
        with tempfile.TemporaryDirectory() as name:
            destination = Path(name) / "safe.zip"
            ApfAudioBatchExporter(FakeIdentityExporter()).export_selected(
                (row,), destination, batch_name="+Playlist\rName"
            )
            manifest, _names = read_manifest(destination)
            catalog = read_catalog(destination)
            with zipfile.ZipFile(destination) as archive:
                raw_catalog = archive.read("catalog.csv")
                playlist = archive.read("playlist.m3u8").decode("utf-8")

        metadata = manifest["records"][0]["metadata"]
        self.assertEqual(metadata["audio_source_id"], "=SUM(1, 2)")
        self.assertEqual(metadata["audio_source_label"], "@source label")
        self.assertEqual(metadata["role_basis"], "hidden claim")
        self.assertEqual(metadata["paired_bank_name"], "@paired bank")
        self.assertIsNone(metadata["sample_rate"])
        self.assertIsNone(metadata["channel_count"])
        self.assertIsNone(metadata["duration_seconds"])
        self.assertIsNone(metadata["duration_basis"])
        self.assertIsNone(metadata["logical_track_number"])
        self.assertIsNone(metadata["packet_count"])
        self.assertIsNone(metadata["encoded_size"])
        self.assertEqual(metadata["range_length"], 4)
        self.assertNotIn(b"\x00", raw_catalog)
        self.assertNotIn(b"\r", raw_catalog)
        safe = catalog[0]
        for name in (
            "row_id",
            "title",
            "audio_source_id",
            "audio_source_label",
            "role_id",
            "role_label",
            "audio_format",
            "paired_bank_name",
            "paired_encoding_role",
            "track_title_status",
        ):
            self.assertTrue(safe[name].startswith("'"), (name, safe[name]))
        self.assertEqual(
            playlist.splitlines(),
            [
                "#EXTM3U",
                "#PLAYLIST:+Playlist Name",
                '#EXTINF:-1,=HYPERLINK("bad") next',
                "audio/audo/o00007-i00001.xma",
            ],
        )

    def test_playlist_preserves_success_order_and_normalized_durations(self) -> None:
        rows = (
            playable_row(
                8,
                title="First",
                fields={"duration_seconds": 1.25},
            ),
            playable_row(
                2,
                kind="ausb_substream",
                title="Second",
                fields={"duration_seconds_candidate": 2.5},
            ),
            playable_row(6, title="Third", fields={}),
        )
        with tempfile.TemporaryDirectory() as name:
            destination = Path(name) / "ordered.zip"
            receipt = ApfAudioBatchExporter(FakeIdentityExporter()).export_selected(
                rows, destination, batch_name="Requested order"
            )
            with zipfile.ZipFile(destination) as archive:
                playlist = archive.read("playlist.m3u8").decode("utf-8").splitlines()

        self.assertEqual(receipt.playlist_record_count, 3)
        self.assertEqual(
            playlist,
            [
                "#EXTM3U",
                "#PLAYLIST:Requested order",
                "#EXTINF:1.25,First",
                "audio/audo/o00007-i00008.xma",
                "#EXTINF:2.5,Second",
                "audio/ausb/o00012-i00004/s00002.xma",
                "#EXTINF:-1,Third",
                "audio/audo/o00007-i00006.xma",
            ],
        )

    def test_physical_bank_and_ausb_index_rows_fail_closed_as_unsupported(self) -> None:
        exporter = FakeIdentityExporter()
        service = ApfAudioBatchExporter(exporter)
        malicious_index = playable_row(1)
        malicious_index = InspectorRow(
            row_id=malicious_index.row_id,
            kind="ausb_bank",
            title=malicious_index.title,
            subtitle=malicious_index.subtitle,
            fields=malicious_index.fields,
            export_identity=malicious_index.export_identity,
            _search_text="",
        )
        malicious_physical = playable_row(2)
        malicious_physical = InspectorRow(
            row_id=malicious_physical.row_id,
            kind="external_bank",
            title=malicious_physical.title,
            subtitle=malicious_physical.subtitle,
            fields=malicious_physical.fields,
            export_identity=malicious_physical.export_identity,
            _search_text="",
        )
        with tempfile.TemporaryDirectory() as name:
            destination = Path(name) / "banks.zip"
            receipt = service.export_selected(
                (malicious_index, malicious_physical), destination
            )
            manifest, names = read_manifest(destination)

        self.assertEqual(exporter.calls, [])
        self.assertEqual(receipt.unsupported, 2)
        self.assertEqual(receipt.succeeded, 0)
        self.assertEqual(names, ("catalog.csv", "manifest.json"))
        self.assertEqual(receipt.payload_bytes, 0)
        self.assertEqual(receipt.catalog_record_count, 2)
        self.assertEqual(receipt.playlist_record_count, 0)
        self.assertEqual(manifest["catalog"], "catalog.csv")
        self.assertEqual(manifest["catalog_record_count"], 2)
        self.assertIsNone(manifest["playlist"])
        self.assertEqual(manifest["playlist_record_count"], 0)
        self.assertEqual(
            [record["error_code"] for record in manifest["records"]],
            ["ausb_index_not_playable", "physical_bank_not_a_cue"],
        )
        self.assertTrue(
            all(
                record["replacement_supported"] is False
                for record in manifest["records"]
            )
        )

    def test_no_identity_and_unknown_identity_are_manifested_not_exported(self) -> None:
        exporter = FakeIdentityExporter()
        unknown = InspectorRow(
            row_id="unknown:1",
            kind="future_audio",
            title="Future row",
            subtitle="",
            fields={},
            export_identity=ExportIdentity("future", 1, 2, None, "future"),
            _search_text="",
        )
        with tempfile.TemporaryDirectory() as name:
            destination = Path(name) / "unsupported.zip"
            receipt = ApfAudioBatchExporter(exporter).export_selected(
                (metadata_row("semantic_metadata", 0), unknown), destination
            )
            manifest, _names = read_manifest(destination)

        self.assertEqual(receipt.unsupported, 2)
        self.assertEqual(exporter.calls, [])
        self.assertEqual(
            [record["error_code"] for record in manifest["records"]],
            [
                "no_single_sound_export_identity",
                "invalid_or_unsupported_export_identity",
            ],
        )

    def test_per_sound_failure_is_recorded_and_later_rows_continue(self) -> None:
        exporter = FakeIdentityExporter()
        exporter.fail_inner.add(2)
        rows = (playable_row(1), playable_row(2), playable_row(3))
        with tempfile.TemporaryDirectory() as name:
            destination = Path(name) / "partial.zip"
            receipt = ApfAudioBatchExporter(exporter).export_selected(
                rows, destination
            )
            manifest, names = read_manifest(destination)

        self.assertEqual(len(exporter.calls), 3)
        self.assertEqual((receipt.succeeded, receipt.failed), (2, 1))
        self.assertEqual(
            [record["status"] for record in manifest["records"]],
            ["success", "failure", "success"],
        )
        self.assertEqual(
            manifest["records"][1]["error_code"], "single_sound_export_failed"
        )
        self.assertNotIn("selected.xma", manifest["records"][1]["message"])
        self.assertEqual(
            names,
            (
                "audio/audo/o00007-i00001.xma",
                "audio/audo/o00007-i00003.xma",
                "catalog.csv",
                "playlist.m3u8",
                "manifest.json",
            ),
        )

    def test_cancellation_publishes_accounted_partial_manifest(self) -> None:
        exporter = FakeIdentityExporter()
        events = []
        rows = tuple(playable_row(index) for index in range(4))
        with tempfile.TemporaryDirectory() as name:
            destination = Path(name) / "cancelled.zip"
            receipt = ApfAudioBatchExporter(exporter).export_selected(
                rows,
                destination,
                progress=events.append,
                cancel_requested=lambda: len(exporter.calls) >= 1,
            )
            manifest, names = read_manifest(destination)
            catalog = read_catalog(destination)

        self.assertTrue(receipt.was_cancelled)
        self.assertEqual((receipt.succeeded, receipt.cancelled), (1, 3))
        self.assertEqual(manifest["counts"]["requested"], 4)
        self.assertEqual(
            [record["status"] for record in manifest["records"]],
            ["success", "cancelled", "cancelled", "cancelled"],
        )
        self.assertEqual(events[0].stage, "preparing")
        self.assertEqual(events[-1].stage, "cancelled")
        self.assertEqual(events[-1].completed, 4)
        self.assertEqual(
            names,
            (
                "audio/audo/o00007-i00000.xma",
                "catalog.csv",
                "playlist.m3u8",
                "manifest.json",
            ),
        )
        self.assertEqual(len(catalog), 4)
        self.assertEqual(
            [row["status"] for row in catalog],
            ["success", "cancelled", "cancelled", "cancelled"],
        )

    def test_duplicate_coordinates_cannot_overwrite_an_archive_member(self) -> None:
        exporter = FakeIdentityExporter()
        first = playable_row(3, row_id="first")
        duplicate = playable_row(3, row_id="second")
        with tempfile.TemporaryDirectory() as name:
            destination = Path(name) / "duplicate.zip"
            receipt = ApfAudioBatchExporter(exporter).export_selected(
                (first, duplicate), destination
            )
            manifest, names = read_manifest(destination)

        self.assertEqual(len(exporter.calls), 1)
        self.assertEqual((receipt.succeeded, receipt.failed), (1, 1))
        self.assertEqual(names.count("audio/audo/o00007-i00003.xma"), 1)
        self.assertIn("catalog.csv", names)
        self.assertIn("playlist.m3u8", names)
        self.assertEqual(
            manifest["records"][1]["error_code"],
            "duplicate_export_coordinates",
        )

    def test_symlink_payload_is_never_copied(self) -> None:
        exporter = FakeIdentityExporter()
        exporter.make_symlink = True
        with tempfile.TemporaryDirectory() as name:
            destination = Path(name) / "symlink.zip"
            receipt = ApfAudioBatchExporter(exporter).export_selected(
                (playable_row(1),), destination
            )
            manifest, names = read_manifest(destination)

        self.assertEqual((receipt.succeeded, receipt.failed), (0, 1))
        self.assertEqual(names, ("catalog.csv", "manifest.json"))
        self.assertEqual(
            manifest["records"][0]["error_code"], "single_sound_export_failed"
        )

    def test_wav_request_is_forwarded_only_for_an_advertised_identity(self) -> None:
        exporter = FakeIdentityExporter()
        rows = (
            playable_row(1),
            playable_row(2, supported_extensions=(".xma",)),
        )
        with tempfile.TemporaryDirectory() as name:
            destination = Path(name) / "wav.zip"
            receipt = ApfAudioBatchExporter(exporter).export_selected(
                rows, destination, output_extension=".WAV"
            )
            manifest, names = read_manifest(destination)

        self.assertEqual((receipt.succeeded, receipt.unsupported), (1, 1))
        self.assertEqual(receipt.output_extension, ".wav")
        self.assertIn("audio/audo/o00007-i00001.wav", names)
        self.assertEqual(manifest["requested_format"], "wav")
        self.assertEqual(
            manifest["records"][1]["error_code"],
            "format_not_supported_by_identity",
        )

    def test_existing_destination_is_never_overwritten(self) -> None:
        exporter = FakeIdentityExporter()
        with tempfile.TemporaryDirectory() as name:
            destination = Path(name) / "existing.zip"
            destination.write_bytes(b"keep me")
            with self.assertRaises(FileExistsError):
                ApfAudioBatchExporter(exporter).export_selected(
                    (playable_row(1),), destination
                )
            self.assertEqual(destination.read_bytes(), b"keep me")
        self.assertEqual(exporter.calls, [])

    def test_progress_hook_failure_leaves_no_published_or_staging_archive(self) -> None:
        exporter = FakeIdentityExporter()
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            destination = root / "callback.zip"

            def broken_progress(_event: object) -> None:
                raise RuntimeError("consumer stopped")

            with self.assertRaisesRegex(RuntimeError, "consumer stopped"):
                ApfAudioBatchExporter(exporter).export_selected(
                    (playable_row(1),), destination, progress=broken_progress
                )
            self.assertFalse(destination.exists())
            self.assertEqual(tuple(root.iterdir()), ())

    def test_invalid_requests_are_rejected_before_any_export(self) -> None:
        exporter = FakeIdentityExporter()
        service = ApfAudioBatchExporter(exporter)
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            with self.assertRaisesRegex(AudioBatchExportError, "end in .zip"):
                service.export_selected((playable_row(1),), root / "audio.bin")
            with self.assertRaisesRegex(AudioBatchExportError, "lowercase SHA-256"):
                service.export_selected(
                    (playable_row(1),),
                    root / "audio.zip",
                    source_sha256="A" * 64,
                )
            with self.assertRaisesRegex(AudioBatchExportError, "original .xma"):
                service.export_selected(
                    (playable_row(1),),
                    root / "audio.zip",
                    output_extension=".mp3",
                )
            with self.assertRaisesRegex(AudioBatchExportError, "at least one"):
                service.export_selected((), root / "audio.zip")
        self.assertEqual(exporter.calls, [])

    def test_global_batch_limit_matches_the_complete_pinned_surface(self) -> None:
        self.assertEqual(MAX_BATCH_ROWS, 2_261 + 20 + 45_514 + 19)


if __name__ == "__main__":
    unittest.main()
