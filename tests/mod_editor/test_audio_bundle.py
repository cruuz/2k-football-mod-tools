"""Pure headless tests for transactional 2K5 audio-collection exports."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import zipfile

from mod_editor.core.nfl2k5_audio_catalog import (
    Nfl2k5AudioAsset,
    Nfl2k5StreamingAudioBank,
    Nfl2k5StreamingAudioRange,
)
from mod_editor.studio.audio_bundle import (
    AUDIO_BUNDLE_SCHEMA,
    MAX_BUNDLE_PAYLOAD_BYTES,
    AudioBundleError,
    AudioBundleRow,
    bundle_row_for_asset,
    export_audio_bundle,
)


def _row(
    index: int,
    *,
    extension: str = ".wav",
    predicted: int = 16,
    origin: str = "retail_derived",
    stable_id: str | None = None,
) -> AudioBundleRow:
    return AudioBundleRow(
        stable_id=stable_id or f"nfl2k5.audio.fixture.{index:03d}",
        display_name=f"Fixture sound {index}",
        suggested_basename=f"unsafe / Sound {index}.WAV",
        extension=extension,
        predicted_payload_bytes=predicted,
        content_origin=origin,
        metadata={
            "scope": "standalone" if extension == ".wav" else "streaming",
            "family_id": "music",
            "selector": {"outer_index": 3, "chunk_index": index},
        },
    )


class AudioBundleTests(unittest.TestCase):
    def test_soundtrack_scale_bundle_is_deterministic_and_self_describing(self) -> None:
        rows = tuple(
            _row(
                index,
                extension=".bin" if index == 136 else ".wav",
                predicted=len(f"payload-{index}"),
                origin="user_replacement" if index == 1 else "retail_derived",
            )
            for index in range(1, 137)
        )

        def writer(row: AudioBundleRow, destination: Path) -> Path:
            index = int(row.stable_id.rsplit(".", 1)[1])
            destination.write_bytes(f"payload-{index}".encode("ascii"))
            return destination.resolve()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            progress: list[tuple[int, int]] = []
            first = export_audio_bundle(
                rows,
                root / "soundtrack.zip",
                bundle_name="Soundtrack & music",
                payload_writer=writer,
                progress=lambda completed, total: progress.append((completed, total)),
            )
            second = export_audio_bundle(
                rows,
                root / "soundtrack-copy.ZIP",
                bundle_name="Soundtrack & music",
                payload_writer=writer,
            )
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(progress[0], (0, 136))
            self.assertEqual(progress[-1], (136, 136))
            self.assertEqual(len(progress), 137)

            with zipfile.ZipFile(first) as archive:
                self.assertEqual(
                    archive.namelist()[0], "audio/001-unsafe-Sound-1.wav"
                )
                self.assertEqual(
                    archive.namelist()[-3:],
                    [
                        "audio/136-unsafe-Sound-136.bin",
                        "playlist.m3u8",
                        "manifest.json",
                    ],
                )
                manifest = json.loads(archive.read("manifest.json"))
                self.assertEqual(manifest["schema"], AUDIO_BUNDLE_SCHEMA)
                self.assertEqual(manifest["record_count"], 136)
                self.assertEqual(manifest["bundle_name"], "Soundtrack & music")
                first_record = manifest["records"][0]
                self.assertEqual(first_record["content_origin"], "user_replacement")
                self.assertEqual(first_record["metadata"]["family_id"], "music")
                self.assertEqual(first_record["payload_bytes"], len(b"payload-1"))
                self.assertEqual(
                    first_record["sha256"], hashlib.sha256(b"payload-1").hexdigest()
                )
                self.assertEqual(
                    manifest["payload_bytes"],
                    sum(len(f"payload-{index}") for index in range(1, 137)),
                )
                self.assertEqual(manifest["playlist"], "playlist.m3u8")
                self.assertEqual(manifest["playlist_record_count"], 135)
                playlist = archive.read("playlist.m3u8").decode("utf-8").splitlines()
                self.assertEqual(playlist[:2], ["#EXTM3U", "#PLAYLIST:Soundtrack & music"])
                self.assertEqual(
                    playlist[2:6],
                    [
                        "#EXTINF:-1,Fixture sound 1",
                        "audio/001-unsafe-Sound-1.wav",
                        "#EXTINF:-1,Fixture sound 2",
                        "audio/002-unsafe-Sound-2.wav",
                    ],
                )
                self.assertNotIn("audio/136-unsafe-Sound-136.bin", playlist)

    def test_count_identity_and_predicted_size_are_preflighted(self) -> None:
        calls = 0

        def writer(_row: AudioBundleRow, destination: Path) -> None:
            nonlocal calls
            calls += 1
            destination.write_bytes(b"payload")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = (
                ((), root / "empty.zip", None),
                (tuple(_row(index) for index in range(257)), root / "large.zip", None),
                ((_row(1), _row(2, stable_id=_row(1).stable_id)), root / "dupe.zip", None),
                ((_row(1, predicted=7), _row(2, predicted=7)), root / "cap.zip", 10),
            )
            for rows, destination, cap in cases:
                with self.subTest(destination=destination.name), self.assertRaises(
                    AudioBundleError
                ):
                    keywords = {} if cap is None else {"max_payload_bytes": cap}
                    export_audio_bundle(
                        rows,
                        destination,
                        bundle_name="preflight",
                        payload_writer=writer,
                        **keywords,
                    )
                self.assertFalse(destination.exists())
            self.assertEqual(calls, 0)
            with self.assertRaises(AudioBundleError):
                export_audio_bundle(
                    (_row(1),),
                    root / "cap.zip",
                    bundle_name="invalid hard cap",
                    payload_writer=writer,
                    max_payload_bytes=MAX_BUNDLE_PAYLOAD_BYTES + 1,
                )
            self.assertEqual(calls, 0)

    def test_format_origin_metadata_and_zip_suffix_fail_closed(self) -> None:
        bad_rows = (
            AudioBundleRow("id", "name", "name", ".xma", 1, "retail_derived"),
            AudioBundleRow("id", "name", "name", ".wav", 1, "unknown"),
            AudioBundleRow(
                "id", "name", "name", ".wav", 1, "retail_derived", {"bad": Path("x")}
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, row in enumerate(bad_rows):
                destination = root / f"bad-{index}.zip"
                with self.subTest(index=index), self.assertRaises(AudioBundleError):
                    export_audio_bundle(
                        (row,),
                        destination,
                        bundle_name="invalid",
                        payload_writer=lambda _row, path: path.write_bytes(b"x"),
                    )
                self.assertFalse(destination.exists())
            with self.assertRaisesRegex(AudioBundleError, r"\.zip"):
                export_audio_bundle(
                    (_row(1),),
                    root / "wrong.tar",
                    bundle_name="invalid",
                    payload_writer=lambda _row, path: path.write_bytes(b"x"),
                )

    def test_writer_failure_or_oversize_actual_payload_leaves_no_output(self) -> None:
        rows = (_row(1, predicted=2), _row(2, predicted=2))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            failed = root / "failed.zip"

            def fail_second(row: AudioBundleRow, destination: Path) -> None:
                if row.stable_id.endswith("002"):
                    raise RuntimeError("fixture decode failure")
                destination.write_bytes(b"ok")

            with self.assertRaisesRegex(RuntimeError, "fixture decode"):
                export_audio_bundle(
                    rows,
                    failed,
                    bundle_name="all or nothing",
                    payload_writer=fail_second,
                    max_payload_bytes=4,
                )
            self.assertFalse(failed.exists())

            oversized = root / "oversized.zip"
            with self.assertRaisesRegex(AudioBundleError, "actual audio payload"):
                def oversized_writer(_row: AudioBundleRow, path: Path) -> None:
                    path.write_bytes(b"too large")

                export_audio_bundle(
                    (_row(1, predicted=1),),
                    oversized,
                    bundle_name="actual cap",
                    payload_writer=oversized_writer,
                    max_payload_bytes=2,
                )
            self.assertFalse(oversized.exists())

    def test_existing_dangling_symlink_and_publication_race_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            existing = root / "existing.zip"
            existing.write_bytes(b"user bytes")
            with self.assertRaises(FileExistsError):
                export_audio_bundle(
                    (_row(1),),
                    existing,
                    bundle_name="refuse overwrite",
                    payload_writer=lambda _row, path: path.write_bytes(b"payload"),
                )
            self.assertEqual(existing.read_bytes(), b"user bytes")

            link = root / "link.zip"
            link.symlink_to(root / "missing-target.zip")
            with self.assertRaisesRegex(AudioBundleError, "symbolic link"):
                export_audio_bundle(
                    (_row(1),),
                    link,
                    bundle_name="refuse link",
                    payload_writer=lambda _row, path: path.write_bytes(b"payload"),
                )
            self.assertTrue(link.is_symlink())

            raced = root / "raced.zip"

            def racing_writer(_row: AudioBundleRow, path: Path) -> None:
                path.write_bytes(b"payload")
                raced.write_bytes(b"concurrent user bytes")

            with self.assertRaises(FileExistsError):
                export_audio_bundle(
                    (_row(1),),
                    raced,
                    bundle_name="race",
                    payload_writer=racing_writer,
                )
            self.assertEqual(raced.read_bytes(), b"concurrent user bytes")

    def test_writer_must_create_the_exact_regular_non_link_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / "outside.wav"
            outside.write_bytes(b"outside")

            def wrong_return(_row: AudioBundleRow, destination: Path) -> Path:
                destination.write_bytes(b"payload")
                return outside

            with self.assertRaisesRegex(AudioBundleError, "unexpected path"):
                export_audio_bundle(
                    (_row(1),),
                    root / "wrong.zip",
                    bundle_name="wrong return",
                    payload_writer=wrong_return,
                )
            self.assertFalse((root / "wrong.zip").exists())

            def link_writer(_row: AudioBundleRow, destination: Path) -> Path:
                destination.symlink_to(outside)
                return destination

            with self.assertRaisesRegex(AudioBundleError, "regular, non-link"):
                export_audio_bundle(
                    (_row(1),),
                    root / "link-payload.zip",
                    bundle_name="link payload",
                    payload_writer=link_writer,
                )
            self.assertFalse((root / "link-payload.zip").exists())

    def test_catalog_asset_adapter_owns_formats_metadata_and_size_predictions(self) -> None:
        standalone = Mock(spec=Nfl2k5AudioAsset)
        standalone.asset_id = "nfl2k5.audio.outer0003.chunk0101"
        standalone.name = "menu-back_01"
        standalone.scope_id = "standalone"
        standalone.family_id = "frontend_ui"
        standalone.family_label = "Frontend & UI"
        standalone.container_label = "Standalone AUDO"
        standalone.format_label = "Playable PCM16 WAV export"
        standalone.edit_status = "Editable"
        standalone.editable = True
        standalone.outer_index = 3
        standalone.outer_id = "AUDO"
        standalone.chunk_index = 101
        standalone.sample_rate = 22_050
        standalone.channels = 1
        standalone.frame_count = 6_400
        standalone.duration_seconds = 6_400 / 22_050
        standalone.suggested_filename = "menu-back_01.wav"
        adapted = bundle_row_for_asset(
            standalone, output_format="wav", content_origin="user_replacement"
        )
        self.assertEqual(adapted.extension, ".wav")
        self.assertEqual(adapted.predicted_payload_bytes, 44 + 6_400 * 2)
        self.assertEqual(adapted.metadata["current_status"], "Modified")
        self.assertEqual(adapted.metadata["frame_count"], 6_400)

        bank = Mock(spec=Nfl2k5StreamingAudioBank)
        bank.asset_id = "nfl2k5.audio.ausb.outer0004.chunk0002"
        bank.name = "jukeboxmusic"
        bank.scope_id = "streaming"
        bank.family_id = "music"
        bank.family_label = "Music"
        bank.container_label = "AUSB streaming bank"
        bank.format_label = "Indexed Xbox IMA bank"
        bank.edit_status = "Export-only"
        bank.outer_index = 4
        bank.outer_id = "AUSB"
        bank.chunk_index = 2
        bank.sample_rate = 44_100
        bank.role_class = "jukeboxmusic"
        bank.external_filename = "jukeboxmusic.bin"
        bank.external_outer_index = 99
        bank.external_size = 123_456
        bank.entry_count = 136
        bank.channel_word = 2
        bank.suggested_filename = "jukeboxmusic.bin"
        bank_row = bundle_row_for_asset(
            bank, output_format=".bin", content_origin="retail_derived"
        )
        self.assertEqual(bank_row.predicted_payload_bytes, 123_456)
        self.assertEqual(bank_row.metadata["entry_count"], 136)
        self.assertEqual(bank_row.metadata["external_outer_index"], 99)
        with self.assertRaisesRegex(AudioBundleError, "raw BIN"):
            bundle_row_for_asset(
                bank, output_format="wav", content_origin="retail_derived"
            )

        audio_range = Mock(spec=Nfl2k5StreamingAudioRange)
        audio_range.asset_id = f"{bank.asset_id}.r00007"
        audio_range.name = "jukeboxmusic / range 7"
        audio_range.scope_id = "streaming_ranges"
        audio_range.family_id = "music"
        audio_range.family_label = "Music"
        audio_range.container_label = "AUSB streaming range"
        audio_range.format_label = "Xbox IMA ADPCM"
        audio_range.edit_status = "Editable"
        audio_range.editable = True
        audio_range.outer_index = 4
        audio_range.outer_id = "AUSB"
        audio_range.chunk_index = 2
        audio_range.sample_rate = 44_100
        audio_range.role_class = "jukeboxmusic"
        audio_range.external_filename = "jukeboxmusic.bin"
        audio_range.external_outer_index = 99
        audio_range.range_index = 7
        audio_range.start = 1_000
        audio_range.end = 1_720
        audio_range.stored_size = 720
        audio_range.channels = 2
        audio_range.frame_count = 640
        audio_range.duration_seconds = 640 / 44_100
        audio_range.suggested_filename = "jukeboxmusic_range_00007.bin"
        audio_range.suggested_wav_filename = "jukeboxmusic_range_00007.wav"
        wav_row = bundle_row_for_asset(
            audio_range, output_format="wav", content_origin="retail_derived"
        )
        raw_row = bundle_row_for_asset(
            audio_range, output_format="bin", content_origin="retail_derived"
        )
        self.assertEqual(wav_row.predicted_payload_bytes, 44 + 640 * 2 * 2)
        self.assertEqual(raw_row.predicted_payload_bytes, 720)
        self.assertEqual(raw_row.metadata["range_index"], 7)
        self.assertEqual(raw_row.metadata["start"], 1_000)
        self.assertEqual(raw_row.metadata["duration_seconds"], 640 / 44_100)
        modified_wav_row = bundle_row_for_asset(
            audio_range,
            output_format="wav",
            content_origin="user_replacement",
        )
        self.assertEqual(modified_wav_row.extension, ".wav")
        self.assertEqual(
            modified_wav_row.predicted_payload_bytes, 44 + 640 * 2 * 2
        )
        self.assertEqual(modified_wav_row.metadata["current_status"], "Modified")
        with self.assertRaisesRegex(AudioBundleError, "playable WAV"):
            bundle_row_for_asset(
                audio_range,
                output_format="bin",
                content_origin="user_replacement",
            )
        with self.assertRaisesRegex(AudioBundleError, "Complete streaming banks"):
            bundle_row_for_asset(
                bank,
                output_format="bin",
                content_origin="user_replacement",
            )

    def test_raw_only_collection_has_no_misleading_player_playlist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "raw-banks.zip"

            def write_raw(_row: AudioBundleRow, path: Path) -> None:
                path.write_bytes(b"encoded")

            export_audio_bundle(
                (_row(1, extension=".bin"),),
                destination,
                bundle_name="Raw streaming bank",
                payload_writer=write_raw,
            )
            with zipfile.ZipFile(destination) as archive:
                self.assertNotIn("playlist.m3u8", archive.namelist())
                manifest = json.loads(archive.read("manifest.json"))
                self.assertIsNone(manifest["playlist"])
                self.assertEqual(manifest["playlist_record_count"], 0)


if __name__ == "__main__":
    unittest.main()
