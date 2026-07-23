from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from mod_editor.apf_studio.audio_batch_export import (
    AudioBatchExportError,
    AudioBatchSafetyError,
    ApfExternalAudioBankBundleExporter,
    EXTERNAL_BANK_MANIFEST_SCHEMA,
)
from mod_editor.apf_studio.facade import ApfStudioFacade, FacadeError
from mod_editor.apf_studio.inspectors import InspectorRow, PagedModel
from mod_editor.apf_studio.models import (
    ExternalAudioBankIdentity,
    ExternalAudioBankOwner,
)


SOURCE_SHA256 = "5c" * 32


def bank_identity(
    outer_index: int,
    filename: str,
    payload: bytes,
    *,
    bank_name: str = "lines",
    descriptor_outer: int | None = None,
) -> ExternalAudioBankIdentity:
    owner = ExternalAudioBankOwner(
        descriptor_outer_index=(
            outer_index + 100 if descriptor_outer is None else descriptor_outer
        ),
        descriptor_inner_index=4,
        bank_name=bank_name,
        substream_count=7,
        sample_rate=48_000,
        channel_count=2,
    )
    return ExternalAudioBankIdentity(
        external_filename=filename,
        outer_table_index=outer_index,
        name_id=0xA0000000 + outer_index,
        encoded_size=len(payload),
        owners=(owner,),
    )


def external_row(identity: ExternalAudioBankIdentity) -> InspectorRow:
    return InspectorRow(
        row_id=f"external:{identity.outer_table_index}",
        kind="external_bank",
        title=identity.external_filename,
        subtitle="Original physical bank",
        fields={},
        external_bank_identity=identity,
        _search_text="",
    )


def read_manifest(path: Path) -> tuple[dict[str, object], zipfile.ZipFile]:
    archive = zipfile.ZipFile(path)
    return json.loads(archive.read("manifest.json")), archive


class FakeExternalBankExporter:
    def __init__(self, payloads: dict[int, bytes]) -> None:
        self.payloads = payloads
        self.calls: list[tuple[ExternalAudioBankIdentity, Path]] = []
        self.fail_indices: set[int] = set()
        self.wrong_size_indices: set[int] = set()

    def export_external_audio_bank(
        self,
        identity: ExternalAudioBankIdentity,
        destination: Path,
        *,
        progress=None,
    ) -> Path:
        self.calls.append((identity, destination))
        if identity.outer_table_index in self.fail_indices:
            raise ValueError("fixture source read failed")
        payload = self.payloads[identity.outer_table_index]
        if identity.outer_table_index in self.wrong_size_indices:
            payload += b"unexpected"
        if progress is not None:
            progress(0, len(payload))
        destination.write_bytes(payload)
        if progress is not None:
            progress(len(payload), len(payload))
        return destination


class ApfExternalAudioBankBundleBackendTests(unittest.TestCase):
    def test_deterministic_stored_bundle_has_safe_paths_hashes_and_all_owners(self) -> None:
        first_payload = b"commentary-bank"
        second_payload = b"soundtrack-bank"
        first = bank_identity(91, "Same Name.bin", first_payload, bank_name="lines")
        second_owner = ExternalAudioBankOwner(
            descriptor_outer_index=202,
            descriptor_inner_index=9,
            bank_name="femusic",
            substream_count=11,
            sample_rate=48_000,
            channel_count=2,
        )
        second_base = bank_identity(
            12, "Same@Name.bin", second_payload, bank_name="jukeboxmusic"
        )
        second = ExternalAudioBankIdentity(
            external_filename=second_base.external_filename,
            outer_table_index=second_base.outer_table_index,
            name_id=second_base.name_id,
            encoded_size=second_base.encoded_size,
            owners=(*second_base.owners, second_owner),
        )
        payloads = {91: first_payload, 12: second_payload}

        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            left = root / "left.zip"
            right = root / "right.zip"
            left_receipt = ApfExternalAudioBankBundleExporter(
                FakeExternalBankExporter(payloads)
            ).export_all(
                (first, second),
                left,
                source_sha256=SOURCE_SHA256,
                bundle_name="  Complete   original banks  ",
            )
            right_receipt = ApfExternalAudioBankBundleExporter(
                FakeExternalBankExporter(payloads)
            ).export_all(
                (second, first),
                right,
                source_sha256=SOURCE_SHA256,
                bundle_name="Complete original banks",
            )
            manifest, archive = read_manifest(left)
            try:
                names = archive.namelist()
                infos = archive.infolist()
                first_archived = archive.read("banks/o00091-Same-Name.bin")
            finally:
                archive.close()

            self.assertEqual(left.read_bytes(), right.read_bytes())
            self.assertEqual(left_receipt.archive_sha256, right_receipt.archive_sha256)
            self.assertEqual(
                names,
                [
                    "banks/o00012-Same-Name.bin",
                    "banks/o00091-Same-Name.bin",
                    "manifest.json",
                ],
            )
            self.assertTrue(
                all(info.compress_type == zipfile.ZIP_STORED for info in infos)
            )
            self.assertEqual(first_archived, first_payload)
            self.assertEqual(manifest["schema"], EXTERNAL_BANK_MANIFEST_SCHEMA)
            self.assertEqual(manifest["bundle_name"], "Complete original banks")
            self.assertEqual(manifest["source_sha256"], SOURCE_SHA256)
            self.assertFalse(
                manifest["capability_boundary"]["replacement_supported"]
            )
            self.assertEqual(manifest["counts"]["success"], 2)
            self.assertEqual(
                [record["outer_table_index"] for record in manifest["banks"]],
                [12, 91],
            )
            second_record = manifest["banks"][0]
            self.assertEqual(second_record["descriptor_owner_count"], 2)
            self.assertEqual(
                [owner["bank_name"] for owner in second_record["descriptor_owners"]],
                ["jukeboxmusic", "femusic"],
            )
            self.assertTrue(
                all(
                    owner["role_id"] == "soundtrack_music"
                    for owner in second_record["descriptor_owners"]
                )
            )
            first_record = manifest["banks"][1]
            self.assertEqual(first_record["name_id"], "0xa000005b")
            self.assertEqual(first_record["source_encoded_size"], len(first_payload))
            self.assertEqual(first_record["file_size"], len(first_payload))
            self.assertEqual(
                first_record["file_sha256"],
                hashlib.sha256(first_payload).hexdigest(),
            )
            self.assertFalse(first_record["replacement_supported"])
            self.assertEqual(
                left_receipt.archive_sha256,
                hashlib.sha256(left.read_bytes()).hexdigest(),
            )

    def test_export_failure_and_wrong_size_are_recorded_then_later_bank_continues(self) -> None:
        payloads = {1: b"one", 2: b"two", 3: b"three"}
        identities = tuple(
            bank_identity(index, f"bank-{index}.bin", payloads[index])
            for index in payloads
        )
        route = FakeExternalBankExporter(payloads)
        route.fail_indices.add(1)
        route.wrong_size_indices.add(2)

        with tempfile.TemporaryDirectory() as name:
            destination = Path(name) / "partial.zip"
            receipt = ApfExternalAudioBankBundleExporter(route).export_all(
                identities,
                destination,
                source_sha256=SOURCE_SHA256,
            )
            manifest, archive = read_manifest(destination)
            try:
                names = archive.namelist()
            finally:
                archive.close()

        self.assertEqual((receipt.succeeded, receipt.failed), (1, 2))
        self.assertEqual(len(route.calls), 3)
        self.assertEqual(
            [record["status"] for record in manifest["banks"]],
            ["failure", "failure", "success"],
        )
        self.assertEqual(
            [record["error_code"] for record in manifest["banks"][:2]],
            ["original_bank_export_failed", "original_bank_export_failed"],
        )
        self.assertEqual(names, ["banks/o00003-bank-3.bin", "manifest.json"])
        self.assertNotIn("apf-external-audio-banks-work-", manifest["banks"][0]["message"])

    def test_cancellation_is_checked_between_whole_banks_and_manifested(self) -> None:
        payloads = {index: f"bank-{index}".encode("ascii") for index in range(4)}
        identities = tuple(
            bank_identity(index, f"bank-{index}.bin", payloads[index])
            for index in payloads
        )
        route = FakeExternalBankExporter(payloads)
        events = []

        with tempfile.TemporaryDirectory() as name:
            destination = Path(name) / "cancelled.zip"
            receipt = ApfExternalAudioBankBundleExporter(route).export_all(
                identities,
                destination,
                source_sha256=SOURCE_SHA256,
                progress=events.append,
                cancel_requested=lambda: len(route.calls) >= 1,
            )
            manifest, archive = read_manifest(destination)
            try:
                names = archive.namelist()
            finally:
                archive.close()

        self.assertTrue(receipt.was_cancelled)
        self.assertEqual((receipt.succeeded, receipt.cancelled), (1, 3))
        self.assertEqual(len(route.calls), 1)
        self.assertEqual(
            [record["status"] for record in manifest["banks"]],
            ["success", "cancelled", "cancelled", "cancelled"],
        )
        self.assertEqual(names, ["banks/o00000-bank-0.bin", "manifest.json"])
        self.assertEqual(events[-1].stage, "cancelled")
        self.assertEqual(events[-1].completed, 4)

    def test_existing_destination_duplicate_identity_and_bad_hash_fail_before_export(self) -> None:
        payload = b"bank"
        identity = bank_identity(4, "bank.bin", payload)
        route = FakeExternalBankExporter({4: payload})
        service = ApfExternalAudioBankBundleExporter(route)
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            destination = root / "existing.zip"
            destination.write_bytes(b"keep")
            with self.assertRaises(FileExistsError):
                service.export_all(
                    (identity,), destination, source_sha256=SOURCE_SHA256
                )
            self.assertEqual(destination.read_bytes(), b"keep")
            with self.assertRaisesRegex(AudioBatchExportError, "more than once"):
                service.export_all(
                    (identity, identity),
                    root / "duplicate.zip",
                    source_sha256=SOURCE_SHA256,
                )
            with self.assertRaisesRegex(AudioBatchExportError, "lowercase SHA-256"):
                service.export_all(
                    (identity,),
                    root / "bad-sha.zip",
                    source_sha256="A" * 64,
                )
        self.assertEqual(route.calls, [])

    def test_integrity_or_progress_failure_publishes_nothing_and_cleans_staging(self) -> None:
        payload = b"bank"
        identity = bank_identity(4, "bank.bin", payload)
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            destination = root / "integrity.zip"
            route = FakeExternalBankExporter({4: payload})
            with patch(
                "mod_editor.apf_studio.audio_batch_export._add_regular_payload",
                side_effect=AudioBatchSafetyError("fixture mutation"),
            ):
                with self.assertRaisesRegex(AudioBatchSafetyError, "fixture mutation"):
                    ApfExternalAudioBankBundleExporter(route).export_all(
                        (identity,), destination, source_sha256=SOURCE_SHA256
                    )
            self.assertFalse(destination.exists())
            self.assertEqual(tuple(root.iterdir()), ())

            callback_destination = root / "callback.zip"

            def broken_progress(_event: object) -> None:
                raise RuntimeError("consumer stopped")

            with self.assertRaisesRegex(RuntimeError, "consumer stopped"):
                ApfExternalAudioBankBundleExporter(
                    FakeExternalBankExporter({4: payload})
                ).export_all(
                    (identity,),
                    callback_destination,
                    source_sha256=SOURCE_SHA256,
                    progress=broken_progress,
                )
            self.assertFalse(callback_destination.exists())
            self.assertEqual(tuple(root.iterdir()), ())


class FakeSession:
    def __init__(self, asset_io: FakeExternalBankExporter) -> None:
        self.asset_io = asset_io
        self.modified_count = 6


class FakeInspectors:
    def __init__(self, identities: tuple[ExternalAudioBankIdentity, ...]) -> None:
        rows = tuple(external_row(identity) for identity in identities)
        self._audio = SimpleNamespace(external_banks=PagedModel(rows))

    def audio(self):
        return self._audio


def loaded_facade(
    route: FakeExternalBankExporter,
    identities: tuple[ExternalAudioBankIdentity, ...] = (),
) -> ApfStudioFacade:
    facade = ApfStudioFacade()
    facade.source = SimpleNamespace(source_sha256=SOURCE_SHA256)
    facade.session = FakeSession(route)  # type: ignore[assignment]
    facade.inspectors = FakeInspectors(identities)  # type: ignore[assignment]
    return facade


class ApfExternalAudioBankBundleFacadeTests(unittest.TestCase):
    def test_direct_facade_route_preserves_project_and_build_state(self) -> None:
        payloads = {8: b"eight", 3: b"three"}
        identities = tuple(
            bank_identity(index, f"bank-{index}.bin", payloads[index])
            for index in payloads
        )
        route = FakeExternalBankExporter(payloads)
        facade = loaded_facade(route)
        previous_build = object()
        facade.last_build = previous_build  # type: ignore[assignment]
        progress: list[tuple[str, int, int]] = []

        with tempfile.TemporaryDirectory() as name:
            destination = Path(name) / "all-banks.zip"
            before = facade.modified_count
            receipt = facade.export_external_audio_bank_bundle(
                identities,
                destination,
                progress=lambda stage, completed, total: progress.append(
                    (stage, completed, total)
                ),
            )
            manifest, archive = read_manifest(destination)
            archive.close()

        self.assertEqual((receipt.requested, receipt.succeeded), (2, 2))
        self.assertEqual(
            [call[0].outer_table_index for call in route.calls], [3, 8]
        )
        self.assertEqual(manifest["source_sha256"], SOURCE_SHA256)
        self.assertEqual(facade.modified_count, before)
        self.assertIs(facade.last_build, previous_build)
        self.assertEqual(progress[0], ("Preparing original APF audio-bank bundle", 0, 2))
        self.assertIn("complete", progress[-1][0])
        self.assertEqual(progress[-1][1:], (2, 2))

    def test_convenience_facade_exports_the_complete_inspector_bank_set(self) -> None:
        payloads = {2: b"two", 6: b"six"}
        identities = tuple(
            bank_identity(index, f"bank-{index}.bin", payloads[index])
            for index in payloads
        )
        route = FakeExternalBankExporter(payloads)
        facade = loaded_facade(route, identities)

        with tempfile.TemporaryDirectory() as name:
            receipt = facade.export_all_external_audio_banks(
                Path(name) / "complete.zip"
            )

        self.assertEqual((receipt.requested, receipt.succeeded), (2, 2))
        self.assertEqual(
            [call[0].outer_table_index for call in route.calls], [2, 6]
        )

    def test_facade_requires_a_loaded_source(self) -> None:
        facade = ApfStudioFacade()
        with tempfile.TemporaryDirectory() as name:
            destination = Path(name) / "unloaded.zip"
            with self.assertRaisesRegex(FacadeError, "Load your APF 2K8 game first"):
                facade.export_external_audio_bank_bundle((), destination)
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
