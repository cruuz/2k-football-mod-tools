"""Synthetic APF build tests for source-bound AUSB exact-slot overlays.

Every fixture byte is generated here.  No retail payload, preimage, physical
source coordinate, or archive record is embedded in this test module.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from mod_editor.apf_studio.build import ApfBuildService, BuildError
from mod_editor.apf_studio.models import (
    AUSB_EXACT_SLOT_KIND,
    AUSB_EXACT_SLOT_WRITER_SCHEMA,
    ApfSource,
    Modification,
)
import apf_ausb_exact_slot


PACKET_SIZE = 0x800
SOURCE_0A_OFFSET = 0x1000
SOURCE_0B_OFFSET = 0x0800
CANONICAL_ID = "apf:audio:ausb:physical:99:4096:4096"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _packet_payload(seed: int) -> bytes:
    packets = []
    for packet_index in range(2):
        packet = bytearray(PACKET_SIZE)
        packet[:4] = b"\x08\x00\x00\x00"
        packet[4:] = bytes(
            ((position + packet_index + seed) % 251) + 1
            for position in range(PACKET_SIZE - 4)
        )
        packets.append(bytes(packet))
    return b"".join(packets)


def _source(root: Path) -> ApfSource:
    data = bytes(range(256)) * 64
    (root / "0A").write_bytes(data)
    return ApfSource(
        selected_path=root,
        game_root=root,
        index_0a=root / "0A",
        source_sha256=_sha256(data),
        source_size=len(data),
        xex_sha256="f" * 64,
        display_name="Synthetic AUSB build fixture",
    )


def _complete_tree(root: Path) -> dict[str, tuple[int, str]]:
    siblings = {
        "0B": bytes(reversed(range(256))) * 32,
        "1A": b"synthetic-1a",
        "1B": b"synthetic-1b",
        "default.xex": b"synthetic-xex",
        "$SystemUpdate/su20076000_00000000": b"synthetic-update",
    }
    for relative, data in siblings.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    tree = {
        "0A": (
            (root / "0A").stat().st_size,
            _sha256((root / "0A").read_bytes()),
        )
    }
    tree.update(
        (relative, (len(data), _sha256(data)))
        for relative, data in siblings.items()
    )
    return tree


def _owner(outer: int, inner: int, substream: int) -> apf_ausb_exact_slot.AusbOwner:
    return apf_ausb_exact_slot.AusbOwner(
        descriptor_outer_index=outer,
        descriptor_inner_index=inner,
        substream_index=substream,
        bank_name="synthetic_bank",
        external_filename="synthetic_bank.bin",
        channels=2,
        sample_rate=48_000,
        duration_value_bits=0x3F800000,
        duration_seconds=1.0,
        declared_sample_count=48_000,
    )


def _resolved(
    source: ApfSource,
    requested: apf_ausb_exact_slot.AusbOwner,
    owners: tuple[apf_ausb_exact_slot.AusbOwner, ...],
    *,
    source_payload_sha256: str | None = None,
) -> apf_ausb_exact_slot.ResolvedExactSlot:
    spans = (
        apf_ausb_exact_slot.PhysicalSpan(
            "0A", SOURCE_0A_OFFSET, PACKET_SIZE, 0
        ),
        apf_ausb_exact_slot.PhysicalSpan(
            "0B", SOURCE_0B_OFFSET, PACKET_SIZE, PACKET_SIZE
        ),
    )
    source_payload = (
        (source.game_root / "0A").read_bytes()[
            SOURCE_0A_OFFSET : SOURCE_0A_OFFSET + PACKET_SIZE
        ]
        + (source.game_root / "0B").read_bytes()[
            SOURCE_0B_OFFSET : SOURCE_0B_OFFSET + PACKET_SIZE
        ]
    )
    return apf_ausb_exact_slot.ResolvedExactSlot(
        asset_id=requested.asset_id,
        requested_owner=requested,
        owners=owners,
        canonical_physical_id=CANONICAL_ID,
        external_outer_index=99,
        external_range_offset=4096,
        target=apf_ausb_exact_slot.ExactSlotTarget(
            channels=2,
            sample_rate=48_000,
            encoded_size=2 * PACKET_SIZE,
            declared_sample_count=48_000,
        ),
        physical_spans=spans,
        source_payload_sha256=(
            source_payload_sha256
            if source_payload_sha256 is not None
            else _sha256(source_payload)
        ),
    )


def _modification(
    root: Path,
    target: apf_ausb_exact_slot.ResolvedExactSlot,
    seed: int,
    *,
    bad_fingerprint: bool = False,
) -> Modification:
    payload = _packet_payload(seed)
    path = root / (
        "replacement-"
        + target.asset_id.removeprefix("apf:audio:ausb:").replace(":", "-")
        + ".xma1-packets"
    )
    path.write_bytes(payload)
    owner_asset_ids = [owner.asset_id for owner in target.owners]
    fingerprint = hashlib.sha256(
        "\n".join(owner_asset_ids).encode("ascii")
    ).hexdigest()
    return Modification(
        asset_id=target.asset_id,
        kind=AUSB_EXACT_SLOT_KIND,
        replacement_path=path,
        replacement_sha256=_sha256(payload),
        metadata={
            "outer_table_index": target.requested_owner.descriptor_outer_index,
            "inner_file_index": target.requested_owner.descriptor_inner_index,
            "substream_index": target.requested_owner.substream_index,
            "encoded_size": target.target.encoded_size,
            "sample_rate": target.target.sample_rate,
            "channel_count": target.target.channels,
            "declared_sample_count": target.target.declared_sample_count,
            "packet_count": target.target.encoded_size // PACKET_SIZE,
            "shared_owner_asset_ids": owner_asset_ids,
            "owner_fingerprint": "0" * 64 if bad_fingerprint else fingerprint,
            "writer_schema": AUSB_EXACT_SLOT_WRITER_SCHEMA,
        },
    )


def _archive(_path: Path) -> object:
    return SimpleNamespace(alignment=1, entries=())


def _manifest_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        keys.update(str(key) for key in value)
        for child in value.values():
            keys.update(_manifest_keys(child))
    elif isinstance(value, (list, tuple)):
        for child in value:
            keys.update(_manifest_keys(child))
    return keys


class AusbOverlayBuildTests(unittest.TestCase):
    def setUp(self) -> None:
        # Composition fixtures use a synthetic archive, so the real complete
        # cross-domain retail scan is covered by dedicated audio safety tests.
        self.audio_gate = patch.object(
            ApfBuildService, "_reject_any_source_audio_reuse"
        )
        self.audio_gate.start()

    def tearDown(self) -> None:
        self.audio_gate.stop()

    def _patches(
        self,
        source: ApfSource,
        tree: dict[str, tuple[int, str]],
        targets: dict[
            tuple[int, int, int], apf_ausb_exact_slot.ResolvedExactSlot
        ],
    ) -> tuple[object, ...]:
        def resolve_many(
            index_0a: Path,
            coordinates: object,
        ) -> dict[tuple[int, int, int], apf_ausb_exact_slot.ResolvedExactSlot]:
            self.assertEqual(index_0a, source.index_0a)
            return {
                coordinate: targets[coordinate]
                for coordinate in tuple(coordinates)  # type: ignore[arg-type]
            }

        return (
            patch("mod_editor.apf_studio.build.EXPECTED_TREE", tree),
            patch(
                "mod_editor.apf_studio.build.EXPECTED_0A_SHA256",
                tree["0A"][1],
            ),
            patch(
                "mod_editor.apf_studio.build.apf_outer.parse_archive",
                side_effect=lambda path: _archive(Path(path)),
            ),
            patch("mod_editor.apf_studio.build.apf_inner.parse_iff"),
            patch(
                "mod_editor.apf_studio.build.apf_ausb_exact_slot.resolve_targets",
                side_effect=resolve_many,
            ),
            patch.object(
                ApfBuildService,
                "_protected_ausb_fingerprints",
                return_value=SimpleNamespace(
                    payload_sha256s=frozenset({"1" * 64, "2" * 64})
                ),
            ),
            patch.object(
                apf_ausb_exact_slot,
                "EXPECTED_UNIQUE_SOURCE_PAYLOAD_HASH_COUNT",
                2,
            ),
        )

    def test_cross_volume_ausb_build_writes_both_packs_without_reparse_or_leaks(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="apf-build-ausb-cross-") as temporary:
            root = Path(temporary)
            game = root / "game"
            game.mkdir()
            source = _source(game)
            tree = _complete_tree(game)
            owner = _owner(10, 20, 3)
            resolved = _resolved(source, owner, (owner,))
            modification = _modification(root, resolved, 17)
            output = root / "output"
            source_0a = (game / "0A").read_bytes()
            source_0b = (game / "0B").read_bytes()
            contexts = self._patches(source, tree, {owner.coordinates: resolved})

            with (
                contexts[0],
                contexts[1],
                contexts[2],
                contexts[3] as parse_iff,
                contexts[4] as resolve_many,
                contexts[5] as source_hashes,
                contexts[6],
            ):
                receipt = ApfBuildService(source).build((modification,), output)

            payload = modification.replacement_path.read_bytes()
            expected_0a = bytearray(source_0a)
            expected_0a[
                SOURCE_0A_OFFSET : SOURCE_0A_OFFSET + PACKET_SIZE
            ] = payload[:PACKET_SIZE]
            expected_0b = bytearray(source_0b)
            expected_0b[
                SOURCE_0B_OFFSET : SOURCE_0B_OFFSET + PACKET_SIZE
            ] = payload[PACKET_SIZE:]
            self.assertEqual((output / "0A").read_bytes(), bytes(expected_0a))
            self.assertEqual((output / "0B").read_bytes(), bytes(expected_0b))
            self.assertEqual((game / "0A").read_bytes(), source_0a)
            self.assertEqual((game / "0B").read_bytes(), source_0b)
            self.assertEqual(receipt.changed_outer_entries, ())
            self.assertEqual(receipt.output_0a_sha256, _sha256(bytes(expected_0a)))
            resolve_many.assert_called_once_with(source.index_0a, (owner.coordinates,))
            source_hashes.assert_called_once_with()
            parse_iff.assert_not_called()

            manifest = json.loads(receipt.manifest.read_text(encoding="utf-8"))
            self.assertEqual(manifest["edit_count"], 1)
            self.assertEqual(manifest["compiled_entry_count"], 0)
            self.assertEqual(manifest["compiled_span_count"], 2)
            self.assertEqual(manifest["compiled_raw_overlay_count"], 2)
            self.assertEqual(manifest["compiled_span_packs"], ["0A", "0B"])
            self.assertFalse(
                manifest["verification"]["all_changed_entries_reparsed"]
            )
            self.assertTrue(
                manifest["verification"]["all_applicable_changed_entries_reparsed"]
            )
            row = manifest["edits"][0]
            self.assertEqual(row["asset_id"], owner.asset_id)
            self.assertEqual(row["changed_pack_names"], ["0A", "0B"])
            self.assertFalse(row["retail_bytes_embedded_in_receipt"])
            self.assertFalse(row["physical_source_coordinates_embedded_in_receipt"])
            forbidden_keys = {
                "canonical_physical_id",
                "external_outer_index",
                "external_range_offset",
                "pack_offset",
                "source_payload_sha256",
                "source_span_sha256",
            }
            self.assertTrue(forbidden_keys.isdisjoint(_manifest_keys(row)))
            manifest_text = json.dumps(row, sort_keys=True)
            self.assertNotIn(CANONICAL_ID, manifest_text)
            self.assertNotIn(resolved.source_payload_sha256, manifest_text)

    def test_identical_semantic_aliases_emit_two_rows_but_two_physical_spans(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="apf-build-ausb-alias-") as temporary:
            root = Path(temporary)
            game = root / "game"
            game.mkdir()
            source = _source(game)
            tree = _complete_tree(game)
            left = _owner(137, 8, 0)
            right = _owner(659, 289, 0)
            owners = (left, right)
            left_target = _resolved(source, left, owners)
            right_target = _resolved(source, right, owners)
            left_modification = _modification(root, left_target, 33)
            right_modification = _modification(root, right_target, 33)
            output = root / "output"
            contexts = self._patches(
                source,
                tree,
                {
                    left.coordinates: left_target,
                    right.coordinates: right_target,
                },
            )

            with (
                contexts[0],
                contexts[1],
                contexts[2],
                contexts[3] as parse_iff,
                contexts[4],
                contexts[5],
                contexts[6],
            ):
                receipt = ApfBuildService(source).build(
                    (left_modification, right_modification), output
                )

            parse_iff.assert_not_called()
            manifest = json.loads(receipt.manifest.read_text(encoding="utf-8"))
            self.assertEqual(manifest["edit_count"], 2)
            self.assertEqual(manifest["compiled_span_count"], 2)
            self.assertEqual(manifest["compiled_raw_overlay_count"], 2)
            self.assertEqual(
                [row["asset_id"] for row in manifest["edits"]],
                [left.asset_id, right.asset_id],
            )
            for row in manifest["edits"]:
                self.assertTrue(row["shared_effect"])
                self.assertEqual(
                    row["shared_owner_asset_ids"],
                    [left.asset_id, right.asset_id],
                )

    def test_divergent_semantic_aliases_are_rejected_before_output_exists(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="apf-build-ausb-diverge-") as temporary:
            root = Path(temporary)
            game = root / "game"
            game.mkdir()
            source = _source(game)
            tree = _complete_tree(game)
            left = _owner(137, 8, 0)
            right = _owner(659, 289, 0)
            owners = (left, right)
            left_target = _resolved(source, left, owners)
            right_target = _resolved(source, right, owners)
            output = root / "output"
            contexts = self._patches(
                source,
                tree,
                {
                    left.coordinates: left_target,
                    right.coordinates: right_target,
                },
            )

            with (
                contexts[0],
                contexts[1],
                contexts[2],
                contexts[3],
                contexts[4],
                contexts[5],
                contexts[6],
                self.assertRaisesRegex(BuildError, "Divergent AUSB edits"),
            ):
                ApfBuildService(source).build(
                    (
                        _modification(root, left_target, 41),
                        _modification(root, right_target, 73),
                    ),
                    output,
                )

            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob(".output.building-*")), [])

    def test_source_payload_hash_mismatch_is_rejected_before_output_exists(self) -> None:
        with tempfile.TemporaryDirectory(prefix="apf-build-ausb-source-") as temporary:
            root = Path(temporary)
            game = root / "game"
            game.mkdir()
            source = _source(game)
            tree = _complete_tree(game)
            owner = _owner(10, 20, 3)
            resolved = _resolved(
                source,
                owner,
                (owner,),
                source_payload_sha256="a" * 64,
            )
            output = root / "output"
            contexts = self._patches(source, tree, {owner.coordinates: resolved})

            with (
                contexts[0],
                contexts[1],
                contexts[2],
                contexts[3],
                contexts[4],
                contexts[5],
                contexts[6],
                self.assertRaisesRegex(BuildError, "source payload changed"),
            ):
                ApfBuildService(source).build(
                    (_modification(root, resolved, 91),), output
                )

            self.assertFalse(output.exists())

    def test_owner_fingerprint_mismatch_is_rejected_before_output_exists(self) -> None:
        with tempfile.TemporaryDirectory(prefix="apf-build-ausb-metadata-") as temporary:
            root = Path(temporary)
            game = root / "game"
            game.mkdir()
            source = _source(game)
            tree = _complete_tree(game)
            owner = _owner(10, 20, 3)
            resolved = _resolved(source, owner, (owner,))
            output = root / "output"
            contexts = self._patches(source, tree, {owner.coordinates: resolved})

            with (
                contexts[0],
                contexts[1],
                contexts[2],
                contexts[3],
                contexts[4],
                contexts[5],
                contexts[6],
                self.assertRaisesRegex(BuildError, "target metadata changed"),
            ):
                ApfBuildService(source).build(
                    (
                        _modification(
                            root, resolved, 101, bad_fingerprint=True
                        ),
                    ),
                    output,
                )

            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
