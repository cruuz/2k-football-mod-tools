"""Focused tests for the bounded private APF player-rating writer."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from mod_editor.core import platform_compat
from mod_editor.apf_studio.backend import ensure_tools_importable
from mod_editor.apf_studio.build import ApfBuildService, BuildError
from mod_editor.apf_studio.models import ApfSource, Modification


ensure_tools_importable()
import apf_inner  # type: ignore  # noqa: E402
import apf_outer  # type: ignore  # noqa: E402
import apf_player_rating_patch as writer  # type: ignore  # noqa: E402
import apf_roster  # type: ignore  # noqa: E402
import apf_texture_patch  # type: ignore  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "extracted/All-Pro Football 2K8 (USA)/0A"


def _manifest_keys(value: object) -> set[str]:
    result: set[str] = set()
    if isinstance(value, dict):
        result.update(str(key) for key in value)
        for child in value.values():
            result.update(_manifest_keys(child))
    elif isinstance(value, (list, tuple)):
        for child in value:
            result.update(_manifest_keys(child))
    return result


class PlayerRatingTargetContractTests(unittest.TestCase):
    def test_exact_asset_target_and_metadata_are_retail_free(self) -> None:
        target = writer.target_for(2_253, "scramble")
        self.assertEqual(target.asset_id, "apf:player-rating:2253:scramble")
        self.assertEqual(writer.parse_asset_id(target.asset_id), target)
        self.assertEqual(
            writer.target_metadata(target),
            {
                "player_index": 2_253,
                "field_id": "scramble",
                "record_relative_offset": 0xD6,
                "public_minimum": 0,
                "public_maximum": 99,
            },
        )

    def test_batch_accepts_zero_and_99_and_has_schema_order(self) -> None:
        rows = writer.normalize_replacements(
            {2: {"catch": 0, "speed": 99}, 0: {"scramble": 50}}
        )
        self.assertEqual(
            [(target.asset_id, value) for target, value in rows],
            [
                ("apf:player-rating:0:scramble", 50),
                ("apf:player-rating:2:speed", 99),
                ("apf:player-rating:2:catch", 0),
            ],
        )

    def test_bounds_unknown_fields_bool_and_native_100_fail_closed(self) -> None:
        invalid = (
            ({-1: {"speed": 50}}, "0 to 2253"),
            ({2_254: {"speed": 50}}, "0 to 2253"),
            ({0: {"speed": 100}}, "0 to 99"),
            ({0: {"speed": True}}, "whole number"),
            ({0: {"not_a_rating": 50}}, "Unknown"),
            ({0: {}}, "at least one"),
        )
        for edits, message in invalid:
            with self.subTest(edits=edits):
                with self.assertRaisesRegex(writer.PlayerRatingPatchError, message):
                    writer.normalize_replacements(edits)

    def test_replacement_payload_is_canonical_and_replacement_only(self) -> None:
        payload = writer.encode_replacement_payload(99)
        self.assertEqual(
            payload,
            b'{"schema":"apf2k8_player_rating_replacement/v1","value":99}\n',
        )
        self.assertEqual(writer.decode_replacement_payload(payload), 99)
        with self.assertRaisesRegex(writer.PlayerRatingPatchError, "canonical"):
            writer.decode_replacement_payload(b'{"value":99,"schema":"apf2k8_player_rating_replacement/v1"}')
        with self.assertRaisesRegex(writer.PlayerRatingPatchError, "0 to 99"):
            writer.decode_replacement_payload(
                b'{"schema":"apf2k8_player_rating_replacement/v1","value":100}\n'
            )

    def test_private_entry_publish_is_atomic_nonoverwriting_and_private(self) -> None:
        result = writer.PlayerRatingPatchResult(1126, b"private-fixture", {})
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "rost-entry.bin"
            self.assertEqual(
                writer.write_private_outer_entry(result, destination), destination
            )
            self.assertEqual(destination.read_bytes(), result.entry_bytes)
            # The writer asks platform_compat for 0o600.  POSIX enforces exactly
            # that, unchanged; Windows has no group/other bits to remove, so the
            # same private entry reports 0o666 there and privacy comes from the
            # per-user profile root's inherited ACL.  Both are asserted.
            expected_mode = 0o666 if platform_compat.IS_WINDOWS else 0o600
            self.assertEqual(platform_compat.private_file_mode(), expected_mode)
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), expected_mode)
            with self.assertRaises(FileExistsError):
                writer.write_private_outer_entry(result, destination)
            self.assertEqual(destination.read_bytes(), result.entry_bytes)

    def test_failed_private_entry_verification_removes_new_output(self) -> None:
        result = writer.PlayerRatingPatchResult(1126, b"private-fixture", {})
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "rost-entry.bin"
            with patch.object(Path, "read_bytes", return_value=b"wrong"):
                with self.assertRaisesRegex(
                    writer.PlayerRatingPatchError, "failed verification"
                ):
                    writer.write_private_outer_entry(result, destination)
            self.assertFalse(destination.exists())


@unittest.skipUnless(SOURCE.is_file(), "private APF source is unavailable")
class RetailPlayerRatingWriterTests(unittest.TestCase):
    def test_one_byte_writer_is_token_preserving_reparsed_and_source_safe(self) -> None:
        original_body, _source = apf_roster.load_roster(SOURCE)
        target_offset = (
            apf_roster.ROOT_SIZE + 788 * apf_roster.PLAYER_STRIDE + 0xBA
        )
        self.assertEqual(original_body[target_offset], 40)
        before = SOURCE.stat()
        result = writer.build_patch(SOURCE, {788: {"speed": 99}})
        after = SOURCE.stat()
        self.assertEqual(
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns),
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
        )
        self.assertEqual(result.outer_index, 1126)
        self.assertEqual(result.manifest["mode"], "patched")
        self.assertEqual(result.manifest["edit_count"], 1)
        self.assertEqual(result.manifest["effective_edit_count"], 1)
        self.assertEqual(
            result.manifest["output"]["decoded_changed_byte_count"], 1
        )
        self.assertEqual(
            result.manifest["output"]["selected_target_count"], 1
        )
        transport = result.manifest["output"]["h7a_transport"]
        self.assertEqual(transport["strategy"], "retail-token-preserving")
        self.assertEqual(transport["retail_token_count"], 284_015)
        self.assertEqual(
            transport["retail_tokens_preserved_semantically"], 284_014
        )
        self.assertEqual(transport["retail_tokens_split_or_replaced"], 1)
        self.assertEqual(
            hashlib.sha256(result.entry_bytes).hexdigest(),
            "e852d656ab304400ecef91fed19baed2b4285e212159800423421ad5d3d21836",
        )

        archive = apf_outer.parse_archive(SOURCE)
        entry = archive.entries[apf_roster.OUTER_TABLE_INDEX]
        memory = apf_texture_patch.BytesReader(result.entry_bytes)
        record = apf_inner.parse_iff(memory, entry)
        block = apf_inner.decode_block(memory, record, 0, writer.MAX_DECOMPRESSED)
        part = record.files[0].parts[0]
        rebuilt_body = block[part.offset : part.offset + part.length]
        changed = [
            index
            for index, values in enumerate(zip(original_body, rebuilt_body, strict=True))
            if values[0] != values[1]
        ]
        self.assertEqual(changed, [target_offset])
        self.assertEqual(rebuilt_body[target_offset], 99)

        manifest_keys = _manifest_keys(result.manifest)
        self.assertTrue(
            {"pack_offset", "byte_offset", "preimage", "source_value", "replacement_value"}.isdisjoint(
                manifest_keys
            )
        )
        self.assertFalse(
            result.manifest["distribution"]["manifest_contains_retail_bytes"]
        )
        self.assertTrue(
            result.manifest["validation"][
                "decoded_changes_equal_selected_rating_bytes"
            ]
        )

    def test_no_op_returns_exact_source_entry_without_recompression(self) -> None:
        body, _source = apf_roster.load_roster(SOURCE)
        stock = body[apf_roster.ROOT_SIZE + 0xBA]
        result = writer.build_patch(SOURCE, {0: {"speed": stock}})
        archive = apf_outer.parse_archive(SOURCE)
        entry = archive.entries[apf_roster.OUTER_TABLE_INDEX]
        with apf_inner.ArchiveReader(archive) as reader:
            original_entry = reader.read(entry, 0, entry.size)
        self.assertEqual(result.entry_bytes, original_entry)
        self.assertEqual(result.manifest["mode"], "no_op")
        self.assertEqual(result.manifest["effective_edit_count"], 0)
        self.assertEqual(
            result.manifest["output"]["h7a_transport"]["strategy"],
            "source-entry-verbatim",
        )


class PrivateBuildPipelineTests(unittest.TestCase):
    def test_private_complete_game_helper_uses_only_canonical_temp_payloads(self) -> None:
        source = SimpleNamespace(index_0a=Path("private-source/0A"))
        service = ApfBuildService(source)
        output = Path("private-output")
        returned = SimpleNamespace(output_game=output)
        observed: list[tuple[str, bytes, dict[str, object]]] = []

        def capture(
            modifications: tuple[Modification, ...],
            output_game: Path,
            _progress: object,
        ) -> object:
            self.assertEqual(output_game, output)
            for modification in modifications:
                observed.append(
                    (
                        modification.asset_id,
                        modification.replacement_path.read_bytes(),
                        dict(modification.metadata),
                    )
                )
                self.assertEqual(
                    hashlib.sha256(modification.replacement_path.read_bytes()).hexdigest(),
                    modification.replacement_sha256,
                )
                # Same private-file contract as above: 0o600 enforced on POSIX,
                # 0o666 honestly reported on Windows where mode bits confer
                # nothing and the profile root's ACL is the guarantee.
                self.assertEqual(
                    stat.S_IMODE(modification.replacement_path.stat().st_mode),
                    0o666 if platform_compat.IS_WINDOWS else 0o600,
                )
                self.assertEqual(
                    stat.S_IMODE(modification.replacement_path.stat().st_mode),
                    platform_compat.private_file_mode(),
                )
            return returned

        with patch.object(service, "build", side_effect=capture):
            result = service.build_private_player_rating_candidate(
                {788: {"speed": 99}}, output
            )
        self.assertIs(result, returned)
        self.assertEqual(
            observed,
            [
                (
                    "apf:player-rating:788:speed",
                    writer.encode_replacement_payload(99),
                    writer.target_metadata(writer.target_for(788, "speed")),
                )
            ],
        )

    def test_group_compiler_validates_payload_metadata_and_emits_private_receipt(self) -> None:
        target = writer.target_for(7, "catch")
        payload = writer.encode_replacement_payload(99)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rating.json"
            path.write_bytes(payload)
            modification = Modification(
                asset_id=target.asset_id,
                kind="player_base_rating",
                replacement_path=path,
                replacement_sha256=hashlib.sha256(payload).hexdigest(),
                metadata=writer.target_metadata(target),
            )
            patch_result = writer.PlayerRatingPatchResult(
                1126,
                b"private-entry",
                {
                    "schema": writer.SCHEMA,
                    "mode": "patched",
                    "edits": (
                        {
                            "asset_id": target.asset_id,
                            **writer.target_metadata(target),
                            "replacement_value_sha256": hashlib.sha256(payload).hexdigest(),
                        },
                    ),
                },
            )
            source = ApfSource(
                selected_path=Path(directory),
                game_root=Path(directory),
                index_0a=Path(directory) / "0A",
                source_sha256="a" * 64,
                source_size=0,
                xex_sha256="b" * 64,
                display_name="private rating fixture",
            )
            service = ApfBuildService(source)
            with patch.object(writer, "build_patch", return_value=patch_result) as built:
                result, row = service._compile_player_rating_group((modification,))
            self.assertIs(result, patch_result)
            built.assert_called_once_with(source.index_0a, {7: {"catch": 99}})
            self.assertEqual(row["kind"], "player_base_rating_batch")
            self.assertEqual(
                row["runtime_status"],
                "runtime_proved_xenia_player_card",
            )
            self.assertNotIn("value", json.dumps(row, sort_keys=True))

    def test_group_compiler_rejects_changed_target_metadata(self) -> None:
        target = writer.target_for(7, "catch")
        payload = writer.encode_replacement_payload(99)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rating.json"
            path.write_bytes(payload)
            modification = Modification(
                asset_id=target.asset_id,
                kind="player_base_rating",
                replacement_path=path,
                replacement_sha256=hashlib.sha256(payload).hexdigest(),
                metadata={**writer.target_metadata(target), "player_index": 8},
            )
            service = ApfBuildService(SimpleNamespace(index_0a=Path("unused")))
            with self.assertRaisesRegex(BuildError, "metadata changed"):
                service._compile_player_rating_group((modification,))

    def test_public_facade_surface_is_available_after_runtime_proof(self) -> None:
        from mod_editor.apf_studio.facade import ApfStudioFacade

        self.assertTrue(
            hasattr(ApfBuildService, "build_private_player_rating_candidate")
        )
        self.assertTrue(
            hasattr(ApfStudioFacade, "replace_player_base_rating")
        )
        self.assertTrue(hasattr(ApfStudioFacade, "player_base_rating_value"))
        self.assertFalse(hasattr(ApfStudioFacade, "import_player_rating_sheet"))


if __name__ == "__main__":
    unittest.main()
