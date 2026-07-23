"""Retail-free source/persistence tests for private 2K5 PCM containment."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from mod_editor.core import nfl2k5_audio_source_fingerprints as private_cache
from mod_editor.core.nfl2k5_audio_catalog import Nfl2k5StreamingAudioRange
from mod_editor.core.nfl2k5_audio_containment_fingerprints import (
    AudioContainmentFingerprintCancelled,
    PcmContainmentInventory,
)
from mod_editor.core.nfl2k5_audio_source_containment import (
    AudioSourceContainmentError,
    Nfl2k5AudioSourceContainmentScanner,
    Nfl2k5AudioSourceContainmentStore,
)
from mod_editor.core.nfl2k5_audio_source_scan import (
    AudioSourceScanError,
    decode_xbox_ima_batch,
)
from mod_editor.core.nfl2k5_ausb_fixed_slots import (
    LogicalStreamingOwner,
    build_streaming_slot_catalog,
    decode_xbox_ima_time_block,
)
from tests.mod_editor.test_nfl2k5_audio_source_scan import (
    PACK1_OFFSET,
    SyntheticSourceFixture,
)


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


class Nfl2k5AudioSourceContainmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = SyntheticSourceFixture(Path(self.temporary.name))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def store(self, *, maximum: int | None = None):
        kwargs = {}
        if maximum is not None:
            kwargs["maximum_serialized_bytes"] = maximum
        return Nfl2k5AudioSourceContainmentStore(
            expected_source_sha256=self.fixture.source_sha256,
            expected_cue_count=3,
            expected_owner_count=3,
            **kwargs,
        )

    def scanner(self, *, store=None, **kwargs: object):
        return Nfl2k5AudioSourceContainmentScanner(
            pins=self.fixture.pins,
            capacity_report=self.fixture.capacity_report,
            store=store or self.store(),
            xdvdfs_parser=self.fixture.parser,
            decode_batch_bytes=144,
            **kwargs,
        )

    def test_complete_direct_source_build_is_private_canonical_and_complete(self) -> None:
        source_before = hashlib.sha256(self.fixture.source.read_bytes()).hexdigest()
        cached_pack1_before = self.fixture.cache_pack1.read_bytes()
        events = []

        result = self.scanner().ensure(
            self.fixture.source.resolve(),
            self.fixture.cache,
            progress=events.append,
        )

        self.assertFalse(result.reused_inventory)
        self.assertEqual(result.source_cue_count, 3)
        self.assertEqual(result.source_owner_count, 3)
        self.assertEqual(result.standalone_count, 1)
        self.assertEqual(result.streaming_slot_count, 2)
        self.assertEqual(result.streaming_owner_count, 2)
        self.assertEqual(result.inventory.source_cue_count, 3)
        self.assertEqual(len(result.inventory.source_owner_ids), 3)
        self.assertTrue(result.inventory.private)
        self.assertFalse(result.inventory.shareable)
        self.assertEqual(
            hashlib.sha256(self.fixture.source.read_bytes()).hexdigest(),
            source_before,
        )
        self.assertEqual(self.fixture.cache_pack1.read_bytes(), cached_pack1_before)

        standalone_matches = result.inventory.find_contained_source_pcm(
            self.fixture.standalone_pcm,
            channels=1,
            sample_rate=16_000,
            frame_count=64,
        )
        self.assertTrue(standalone_matches)
        self.assertEqual(
            standalone_matches[0].owner_asset_ids,
            ("nfl2k5.audio.audo.o0000.c0001",),
        )
        first_stream_pcm = decode_xbox_ima_time_block(
            self.fixture.bank_payload[:36], 1
        )
        stream_matches = result.inventory.find_contained_source_pcm(
            first_stream_pcm,
            channels=1,
            sample_rate=22_050,
            frame_count=64,
        )
        self.assertTrue(stream_matches)
        self.assertIn(
            "nfl2k5.audio.ausb.o0000.c0000.r00000",
            stream_matches[0].owner_asset_ids,
        )

        payload = result.inventory_path.read_bytes()
        document = json.loads(payload)
        self.assertEqual(payload, _canonical(document))
        self.assertEqual(document["schema"], "2k5_mod_studio_audio_pcm_containment/v2")
        self.assertEqual(document["privacy"]["audio_payload_bytes"], 0)
        self.assertNotIn(self.fixture.standalone_payload, payload)
        self.assertNotIn(self.fixture.bank_payload[:144], payload)
        self.assertNotIn(str(self.fixture.source).encode(), payload)
        info = result.inventory_path.stat()
        self.assertEqual(stat.S_IMODE(info.st_mode), 0o600)
        self.assertEqual(info.st_nlink, 1)
        self.assertEqual(events[-1].stage, "Private PCM containment inventory ready")

    def test_reuse_reauthenticates_xiso_and_standalone_without_stream_decode(self) -> None:
        first = self.scanner().ensure(
            self.fixture.source.resolve(), self.fixture.cache
        )
        decoded: list[bytes] = []

        def recording_decoder(payload: bytes, channels: int, cancelled):
            decoded.append(payload)
            return decode_xbox_ima_batch(payload, channels, cancelled)

        second = self.scanner(batch_decoder=recording_decoder).ensure(
            self.fixture.source.resolve(), self.fixture.cache
        )
        self.assertTrue(second.reused_inventory)
        self.assertEqual(decoded, [self.fixture.standalone_payload])
        self.assertEqual(first.inventory, second.inventory)
        self.assertEqual(first.inventory_path, second.inventory_path)

        original_payload = first.inventory_path.read_bytes()
        first.inventory_path.unlink()
        regenerated = self.scanner().ensure(
            self.fixture.source.resolve(), self.fixture.cache
        )
        self.assertEqual(regenerated.inventory_path.read_bytes(), original_payload)

    def test_cancellation_during_direct_source_build_publishes_nothing(self) -> None:
        should_cancel = False

        def progress(event) -> None:
            nonlocal should_cancel
            if (
                event.stage == "Indexing source PCM containment"
                and event.completed >= 1
            ):
                should_cancel = True

        scanner = self.scanner()
        with self.assertRaises(AudioContainmentFingerprintCancelled):
            scanner.ensure(
                self.fixture.source.resolve(),
                self.fixture.cache,
                progress=progress,
                cancelled=lambda: should_cancel,
            )
        self.assertFalse(scanner.store.inventory_path(self.fixture.cache).exists())

    def test_malformed_or_oversized_existing_inventory_is_never_repaired(self) -> None:
        store = self.store()
        path = store.inventory_path(self.fixture.cache)
        path.parent.mkdir(mode=0o700)
        path.write_bytes(b"{}\n")
        os.chmod(path, 0o600)
        with self.assertRaises(AudioSourceContainmentError):
            self.scanner(store=store).ensure(
                self.fixture.source.resolve(), self.fixture.cache
            )
        self.assertEqual(path.read_bytes(), b"{}\n")

        path.unlink()
        bounded = self.store(maximum=256)
        oversized_path = bounded.inventory_path(self.fixture.cache)
        oversized_path.write_bytes(b"x" * 257)
        os.chmod(oversized_path, 0o600)
        with self.assertRaisesRegex(
            AudioSourceContainmentError, "serialized-byte cap"
        ):
            self.scanner(store=bounded).ensure(
                self.fixture.source.resolve(), self.fixture.cache
            )
        self.assertEqual(oversized_path.read_bytes(), b"x" * 257)

    def test_store_refuses_nonsemantic_owner_text_before_persistence(self) -> None:
        scanner = self.scanner()
        completed = scanner.ensure(
            self.fixture.source.resolve(), self.fixture.cache
        )
        document = completed.inventory.to_private_document()
        original_owners = list(document["source_owner_ids"])
        path_owners = [
            "/tmp/retail-source-a.iso",
            "/tmp/retail-source-b.iso",
            "/tmp/retail-source-c.iso",
        ]
        replacements = dict(zip(original_owners, path_owners))
        document["source_owner_ids"] = path_owners
        document["zero_exempt_owner_ids"] = [
            replacements[owner]
            for owner in document["zero_exempt_owner_ids"]
        ]
        for row in document["fingerprints"]:
            row["owner_asset_ids"] = sorted(
                replacements[owner] for owner in row["owner_asset_ids"]
            )
        unsafe = PcmContainmentInventory.from_private_document(document)
        completed.inventory_path.unlink()

        with self.assertRaisesRegex(
            AudioSourceContainmentError,
            "owner coverage is invalid",
        ):
            scanner.store.ensure(
                self.fixture.cache,
                unsafe.policy,
                unsafe.source_owner_ids,
                lambda: unsafe,
                publication_guard=lambda _stage: None,
            )
        self.assertFalse(completed.inventory_path.exists())

    def test_incomplete_authenticated_count_contract_fails_before_decode_build(self) -> None:
        wrong = Nfl2k5AudioSourceContainmentStore(
            expected_source_sha256=self.fixture.source_sha256,
            expected_cue_count=4,
            expected_owner_count=4,
        )
        with self.assertRaisesRegex(
            AudioSourceContainmentError, "coverage is incomplete"
        ):
            self.scanner(store=wrong).ensure(
                self.fixture.source.resolve(), self.fixture.cache
            )
        self.assertFalse(wrong.inventory_path(self.fixture.cache).exists())

    def test_mutation_after_final_hash_rolls_back_owned_publication(self) -> None:
        real_publish = private_cache._rename_noreplace_at
        mutated = False

        def publish_then_mutate(
            directory_fd: int,
            source_name: str,
            destination_name: str,
        ) -> None:
            nonlocal mutated
            real_publish(directory_fd, source_name, destination_name)
            with self.fixture.source.open("r+b") as stream:
                stream.seek(PACK1_OFFSET + 300)
                value = stream.read(1)
                stream.seek(PACK1_OFFSET + 300)
                stream.write(bytes((value[0] ^ 0x20,)))
                stream.flush()
                os.fsync(stream.fileno())
            mutated = True

        scanner = self.scanner()
        with patch(
            "mod_editor.core.nfl2k5_audio_source_fingerprints._rename_noreplace_at",
            side_effect=publish_then_mutate,
        ):
            with self.assertRaisesRegex(
                AudioSourceScanError, "post-publication containment source recheck"
            ):
                scanner.ensure(
                    self.fixture.source.resolve(), self.fixture.cache
                )
        path = scanner.store.inventory_path(self.fixture.cache)
        self.assertTrue(mutated)
        self.assertFalse(path.exists())
        self.assertEqual(tuple(path.parent.glob("*.tmp")), ())

    def test_concurrent_winner_gets_post_source_guard_and_is_preserved(self) -> None:
        mutated = False

        def install_winner_then_mutate(
            directory_fd: int,
            source_name: str,
            destination_name: str,
        ) -> None:
            nonlocal mutated
            source_fd = os.open(source_name, os.O_RDONLY, dir_fd=directory_fd)
            destination_fd = os.open(
                destination_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=directory_fd,
            )
            try:
                while True:
                    block = os.read(source_fd, 64 * 1024)
                    if not block:
                        break
                    view = memoryview(block)
                    while view:
                        count = os.write(destination_fd, view)
                        self.assertGreater(count, 0)
                        view = view[count:]
                os.fsync(destination_fd)
            finally:
                os.close(source_fd)
                os.close(destination_fd)
            with self.fixture.source.open("r+b") as stream:
                stream.seek(PACK1_OFFSET + 300)
                value = stream.read(1)
                stream.seek(PACK1_OFFSET + 300)
                stream.write(bytes((value[0] ^ 0x20,)))
                stream.flush()
                os.fsync(stream.fileno())
            mutated = True
            raise private_cache._ConcurrentPublication(destination_name)

        scanner = self.scanner()
        with patch(
            "mod_editor.core.nfl2k5_audio_source_fingerprints._rename_noreplace_at",
            side_effect=install_winner_then_mutate,
        ):
            with self.assertRaisesRegex(
                AudioSourceScanError,
                "post-publication containment source recheck",
            ):
                scanner.ensure(
                    self.fixture.source.resolve(), self.fixture.cache
                )
        path = scanner.store.inventory_path(self.fixture.cache)
        self.assertTrue(mutated)
        self.assertTrue(path.is_file())
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(tuple(path.parent.glob("*.tmp")), ())

    def test_prepublication_authorization_failure_publishes_nothing(self) -> None:
        scanner = self.scanner()
        completed = scanner.ensure(
            self.fixture.source.resolve(), self.fixture.cache
        )
        completed.inventory_path.unlink()
        phases: list[str] = []

        def refuse(phase: str) -> None:
            phases.append(phase)
            if phase == "before_publication":
                raise RuntimeError("synthetic containment authorization failure")

        with self.assertRaisesRegex(
            RuntimeError, "synthetic containment authorization failure"
        ):
            scanner.store.ensure(
                self.fixture.cache,
                completed.inventory.policy,
                completed.inventory.source_owner_ids,
                lambda: completed.inventory,
                publication_guard=refuse,
            )
        self.assertEqual(phases, ["before_publication"])
        self.assertFalse(completed.inventory_path.exists())
        self.assertEqual(tuple(completed.inventory_path.parent.glob("*.tmp")), ())

    def test_publication_failure_never_unlinks_a_foreign_replacement(self) -> None:
        real_publish = private_cache._rename_noreplace_at
        foreign = b"foreign containment sentinel"

        def publish_then_replace(
            directory_fd: int,
            source_name: str,
            destination_name: str,
        ) -> None:
            real_publish(directory_fd, source_name, destination_name)
            os.unlink(destination_name, dir_fd=directory_fd)
            descriptor = os.open(
                destination_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=directory_fd,
            )
            try:
                os.write(descriptor, foreign)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

        scanner = self.scanner()
        with patch(
            "mod_editor.core.nfl2k5_audio_source_fingerprints._rename_noreplace_at",
            side_effect=publish_then_replace,
        ):
            with self.assertRaisesRegex(
                AudioSourceContainmentError, "changed during publication"
            ):
                scanner.ensure(
                    self.fixture.source.resolve(), self.fixture.cache
                )
        path = scanner.store.inventory_path(self.fixture.cache)
        self.assertEqual(path.read_bytes(), foreign)
        self.assertEqual(tuple(path.parent.glob("*.tmp")), ())

    def test_inventory_and_parent_links_fail_closed_without_touching_targets(self) -> None:
        scanner = self.scanner()
        result = scanner.ensure(
            self.fixture.source.resolve(), self.fixture.cache
        )
        outside_file = Path(self.temporary.name) / "outside-inventory.json"
        result.inventory_path.rename(outside_file)
        result.inventory_path.symlink_to(outside_file)
        with self.assertRaisesRegex(
            AudioSourceContainmentError, "mode-0600, non-linked"
        ):
            scanner.ensure(self.fixture.source.resolve(), self.fixture.cache)
        self.assertTrue(outside_file.is_file())

        result.inventory_path.unlink()
        os.link(outside_file, result.inventory_path)
        with self.assertRaisesRegex(
            AudioSourceContainmentError, "mode-0600, non-linked"
        ):
            scanner.ensure(self.fixture.source.resolve(), self.fixture.cache)
        self.assertEqual(outside_file.read_bytes(), result.inventory_path.read_bytes())

    def test_derived_directory_symlink_is_rejected_before_outside_write(self) -> None:
        outside = Path(self.temporary.name) / "outside-derived"
        outside.mkdir()
        os.chmod(outside, 0o755)
        derived = self.fixture.cache_root / "derived"
        derived.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(
            AudioSourceContainmentError, "non-link directory"
        ):
            self.scanner().ensure(
                self.fixture.source.resolve(), self.fixture.cache
            )
        self.assertEqual(tuple(outside.iterdir()), ())
        self.assertEqual(stat.S_IMODE(outside.stat().st_mode), 0o755)

    def test_parent_swap_during_staging_cannot_redirect_or_leak_temp(self) -> None:
        scanner = self.scanner()
        completed = scanner.ensure(
            self.fixture.source.resolve(), self.fixture.cache
        )
        completed.inventory_path.unlink()
        parent = completed.inventory_path.parent
        parked = parent.with_name("derived-parked-during-staging")
        outside = Path(self.temporary.name) / "outside-staging-race"
        outside.mkdir()
        real_open = os.open
        raced = False

        def swap_parent_before_temp_open(path, flags, *args, **kwargs):
            nonlocal raced
            if (
                not raced
                and isinstance(path, str)
                and path.startswith(".audio-source-pcm-containment-v2.")
                and flags & os.O_CREAT
            ):
                parent.rename(parked)
                parent.symlink_to(outside, target_is_directory=True)
                raced = True
            return real_open(path, flags, *args, **kwargs)

        try:
            with patch(
                "mod_editor.core.nfl2k5_audio_source_containment.os.open",
                side_effect=swap_parent_before_temp_open,
            ):
                with self.assertRaisesRegex(
                    AudioSourceContainmentError,
                    "changed during containment staging",
                ):
                    scanner.store.ensure(
                        self.fixture.cache,
                        completed.inventory.policy,
                        completed.inventory.source_owner_ids,
                        lambda: completed.inventory,
                        publication_guard=lambda _stage: None,
                    )
            self.assertTrue(raced)
            self.assertEqual(tuple(outside.iterdir()), ())
            self.assertEqual(tuple(parked.iterdir()), ())
        finally:
            if parent.is_symlink():
                parent.unlink()
            if parked.exists():
                parked.rename(parent)

    def test_parent_swap_during_load_cannot_redirect_inventory_read(self) -> None:
        scanner = self.scanner()
        completed = scanner.ensure(
            self.fixture.source.resolve(), self.fixture.cache
        )
        expected_payload = completed.inventory_path.read_bytes()
        parent = completed.inventory_path.parent
        parked = parent.with_name("derived-parked-during-load")
        outside = Path(self.temporary.name) / "outside-load-race"
        outside.mkdir()
        outside_inventory = outside / completed.inventory_path.name
        real_open = os.open
        raced = False

        def move_inventory_before_open(path, flags, *args, **kwargs):
            nonlocal raced
            if (
                not raced
                and path == completed.inventory_path.name
                and kwargs.get("dir_fd") is not None
                and not flags & os.O_CREAT
            ):
                parent.rename(parked)
                parent.symlink_to(outside, target_is_directory=True)
                (parked / completed.inventory_path.name).rename(outside_inventory)
                raced = True
            return real_open(path, flags, *args, **kwargs)

        try:
            with patch(
                "mod_editor.core.nfl2k5_audio_source_containment.os.open",
                side_effect=move_inventory_before_open,
            ):
                with self.assertRaisesRegex(
                    AudioSourceContainmentError,
                    "Could not open private containment inventory",
                ):
                    scanner.store.load_existing(
                        self.fixture.cache,
                        completed.inventory.policy,
                        completed.inventory.source_owner_ids,
                    )
            self.assertTrue(raced)
            self.assertEqual(outside_inventory.read_bytes(), expected_payload)
        finally:
            if parent.is_symlink():
                parent.unlink()
            if parked.exists():
                parked.rename(parent)
            if outside_inventory.exists():
                outside_inventory.rename(completed.inventory_path)

    def test_source_cue_adapter_retains_every_streaming_alias(self) -> None:
        scanner = self.scanner()
        source_scanner = scanner.source_scanner
        source = source_scanner._open_source(
            self.fixture.source.resolve(), self.fixture.cache
        )
        try:
            entries, _directory = self.fixture.parser(
                source.descriptor, self.fixture.pins.source_size
            )
            extents = source_scanner._pack_extents(entries)
            archive = source_scanner._parse_source_archive(
                source.descriptor, source.path, extents
            )
            banks = source_scanner._streaming_banks(
                source.descriptor,
                archive,
                extents,
                self.fixture.inventory_document,
            )
            ranges = tuple(
                Nfl2k5StreamingAudioRange(bank, index, start, end)
                for bank in banks
                for index, (start, end) in enumerate(
                    zip(bank.boundaries, bank.boundaries[1:])
                )
            )
            slot = build_streaming_slot_catalog(ranges, archive).slots[0]
            first = slot.owners[0]
            alias = LogicalStreamingOwner(
                asset_id="nfl2k5.audio.ausb.o0000.c0000.r00099",
                descriptor_asset_id=first.descriptor_asset_id,
                descriptor_outer_index=first.descriptor_outer_index,
                descriptor_chunk_index=first.descriptor_chunk_index,
                range_index=99,
            )
            aliased = replace(slot, owners=(first, alias))
            cue = next(scanner._source_cues(
                source.descriptor,
                archive,
                extents,
                self.fixture.inventory_document,
                (),
                (aliased,),
                None,
            ))
        finally:
            os.close(source.descriptor)
        self.assertEqual(cue.owner_asset_ids, tuple(sorted((
            first.asset_id,
            alias.asset_id,
        ))))
        self.assertEqual(
            cue.pcm16le,
            decode_xbox_ima_time_block(self.fixture.bank_payload[:36], 1),
        )


if __name__ == "__main__":
    unittest.main()
