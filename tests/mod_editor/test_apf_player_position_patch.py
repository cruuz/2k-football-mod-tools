"""Focused safety tests for the paired APF player-position writer."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Iterator, Mapping
import unittest

from mod_editor.apf_studio.backend import ensure_tools_importable


ensure_tools_importable()
import apf_inner  # type: ignore  # noqa: E402
import apf_outer  # type: ignore  # noqa: E402
import apf_player_position_patch as writer  # type: ignore  # noqa: E402
import apf_roster  # type: ignore  # noqa: E402
import apf_texture_patch  # type: ignore  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "extracted/All-Pro Football 2K8 (USA)/0A"


def _manifest_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        keys.update(str(key) for key in value)
        for child in value.values():
            keys.update(_manifest_keys(child))
    elif isinstance(value, (tuple, list)):
        for child in value:
            keys.update(_manifest_keys(child))
    return keys


class _DuplicateMapping(Mapping[int, int]):
    """Hostile mapping that yields one semantic target twice."""

    def __getitem__(self, key: int) -> int:
        return 3

    def __iter__(self) -> Iterator[int]:
        yield 7
        yield 7

    def __len__(self) -> int:
        return 2

    def items(self) -> Iterator[tuple[int, int]]:  # type: ignore[override]
        yield (7, 3)
        yield (7, 4)


class PlayerPositionTargetContractTests(unittest.TestCase):
    def test_target_payload_and_metadata_are_exact_and_retail_free(self) -> None:
        target = writer.target_for(2_253)
        self.assertEqual(target.asset_id, "apf:player-position:2253")
        self.assertEqual(writer.parse_asset_id(target.asset_id), target)
        self.assertEqual(
            writer.target_metadata(target),
            {
                "player_index": 2_253,
                "semantic_relative_offset": 0x34,
                "mirror_relative_offset": 0x35,
                "minimum_code": 0,
                "maximum_code": 16,
                "source_mirror_required": True,
            },
        )
        payload = writer.encode_replacement_payload(16)
        self.assertEqual(
            payload,
            b'{"schema":"apf2k8_player_position_replacement/v1","value":16}\n',
        )
        self.assertEqual(writer.decode_replacement_payload(payload), 16)

    def test_bounds_duplicate_and_noncanonical_inputs_fail_closed(self) -> None:
        for value in (-1, 17, True, 4.0, "4"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(writer.PlayerPositionPatchError, "0 to 16"):
                    writer.validate_code(value)
        for player in (-1, 2_254, True, 2.0):
            with self.subTest(player=player):
                with self.assertRaisesRegex(writer.PlayerPositionPatchError, "0 to 2253"):
                    writer.target_for(player)  # type: ignore[arg-type]
        with self.assertRaisesRegex(writer.PlayerPositionPatchError, "selected twice"):
            writer.normalize_replacements(_DuplicateMapping())
        with self.assertRaisesRegex(writer.PlayerPositionPatchError, "canonical"):
            writer.decode_replacement_payload(
                b'{"value":3,"schema":"apf2k8_player_position_replacement/v1"}'
            )


@unittest.skipUnless(SOURCE.is_file(), "private APF source is unavailable")
class RetailPlayerPositionWriterTests(unittest.TestCase):
    def _decoded_body(self, entry_bytes: bytes) -> bytes:
        archive = apf_outer.parse_archive(SOURCE)
        entry = archive.entries[apf_roster.OUTER_TABLE_INDEX]
        memory = apf_texture_patch.BytesReader(entry_bytes)
        record = apf_inner.parse_iff(memory, entry)
        block = apf_inner.decode_block(memory, record, 0, writer.MAX_DECOMPRESSED)
        part = record.files[0].parts[0]
        return block[part.offset : part.offset + part.length]

    def test_writer_changes_exact_pair_preserves_source_and_manifest_is_retail_free(self) -> None:
        source_body, _source = apf_roster.load_roster(SOURCE)
        player_index = 788
        start = apf_roster.ROOT_SIZE + player_index * apf_roster.PLAYER_STRIDE
        self.assertEqual(source_body[start + 0x34 : start + 0x36], b"\0\0")
        source_stat = SOURCE.stat()
        source_sha = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        result = writer.build_patch(SOURCE, {player_index: 3})
        after_stat = SOURCE.stat()
        self.assertEqual(
            (source_stat.st_dev, source_stat.st_ino, source_stat.st_size, source_stat.st_mtime_ns),
            (after_stat.st_dev, after_stat.st_ino, after_stat.st_size, after_stat.st_mtime_ns),
        )
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(), source_sha)
        rebuilt = self._decoded_body(result.entry_bytes)
        changed = {
            index
            for index, values in enumerate(zip(source_body, rebuilt, strict=True))
            if values[0] != values[1]
        }
        self.assertEqual(changed, {start + 0x34, start + 0x35})
        self.assertEqual(rebuilt[start + 0x34 : start + 0x36], b"\x03\x03")
        self.assertEqual(result.manifest["mode"], "patched")
        self.assertEqual(result.manifest["output"]["decoded_changed_byte_count"], 2)
        self.assertTrue(
            result.manifest["validation"][
                "every_effective_edit_changes_both_pair_bytes"
            ]
        )
        self.assertTrue(
            {
                "source_value",
                "replacement_value",
                "preimage",
                "record_bytes",
                "pack_offset",
                "byte_offset",
            }.isdisjoint(_manifest_keys(result.manifest))
        )

    def test_no_op_returns_exact_source_entry_without_recompression(self) -> None:
        body, _source = apf_roster.load_roster(SOURCE)
        stock = body[apf_roster.ROOT_SIZE + 0x34]
        result = writer.build_patch(SOURCE, {0: stock})
        archive = apf_outer.parse_archive(SOURCE)
        entry = archive.entries[apf_roster.OUTER_TABLE_INDEX]
        with apf_inner.ArchiveReader(archive) as reader:
            original_entry = reader.read(entry, 0, entry.size)
        self.assertEqual(result.entry_bytes, original_entry)
        self.assertEqual(result.manifest["mode"], "no_op")
        self.assertEqual(result.manifest["output"]["decoded_changed_byte_count"], 0)
        self.assertEqual(
            result.manifest["output"]["h7a_transport"]["strategy"],
            "source-entry-verbatim",
        )


if __name__ == "__main__":
    unittest.main()
