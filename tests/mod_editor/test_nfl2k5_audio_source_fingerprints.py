"""Retail-free synthetic tests for the private 2K5 PCM fingerprint store."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import threading
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

from mod_editor.core import platform_compat
from mod_editor.core import nfl2k5_audio_source_fingerprints as fingerprint_module
from mod_editor.core.model import GameId, SourceRecord
from mod_editor.core.nfl2k5_audio_source_fingerprints import (
    AudioSourceFingerprintCancelled,
    AudioSourceFingerprintError,
    Nfl2k5AudioSourceFingerprintStore,
    SourceDerivedPcmError,
)
from mod_editor.core.nfl2k5_ausb_fixed_slots import (
    CanonicalStreamingSlot,
    LogicalStreamingOwner,
    StreamingPackSpan,
)
from mod_editor.core.nfl2k5_source_cache import SOURCE_SHA256, SourceCache


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


def _records_hash(document: dict[str, object]) -> str:
    return hashlib.sha256(_canonical({
        "standalone": document["standalone"],
        "streaming_slots": document["streaming_slots"],
    })).hexdigest()


def _owner(descriptor: int, range_index: int) -> LogicalStreamingOwner:
    descriptor_id = f"nfl2k5.audio.ausb.o0003.c{descriptor:04d}"
    return LogicalStreamingOwner(
        asset_id=f"{descriptor_id}.r{range_index:05d}",
        descriptor_asset_id=descriptor_id,
        descriptor_outer_index=3,
        descriptor_chunk_index=descriptor,
        range_index=range_index,
    )


def _slot(
    *,
    external: int,
    start: int,
    channels: int,
    owners: tuple[LogicalStreamingOwner, ...],
) -> CanonicalStreamingSlot:
    encoded_size = 36 * channels
    return CanonicalStreamingSlot(
        canonical_id=(
            f"nfl2k5.audio.ausb.physical.o{external:04d}."
            f"s{start:010x}.n{encoded_size:010x}"
        ),
        external_outer_index=external,
        external_outer_id=0xA0000000 + external,
        range_start=start,
        range_end=start + encoded_size,
        channels=channels,
        sample_rate=22_050,
        frame_count=64,
        owners=owners,
        physical_spans=(StreamingPackSpan(
            pack_name="0",
            pack_ordinal=0,
            pack_offset=1_024 + start,
            length=encoded_size,
            payload_offset=0,
        ),),
    )


class FingerprintFixture:
    def __init__(self, root: Path) -> None:
        self.root = root / SOURCE_SHA256
        self.root.mkdir()
        pack0 = self.root / "pack0"
        inventory = self.root / "inventory.json"
        originals = self.root / "originals"
        pack0.write_bytes(b"synthetic non-retail archive metadata")
        inventory.write_text('{"synthetic":true}\n', encoding="utf-8")
        originals.mkdir()
        source = SourceRecord(
            selected_path=str(root / "synthetic.xiso"),
            inspected_path=str(root / "synthetic.xiso"),
            kind="xiso",
            sha256=SOURCE_SHA256,
            size=1,
            recognized=True,
            fingerprint_id="retail-free-test-fixture",
            detected_game=GameId.NFL2K5.value,
        )
        self.cache = SourceCache(
            source=source,
            root=self.root.resolve(),
            pack0=pack0,
            inventory=inventory,
            originals=originals,
            resource_count=4,
            outer_entry_count=2,
            kind_counts={"AUDO": 2, "AUSB": 2},
        )

        # Standalone A and streaming slot A deliberately share decoded PCM.
        # This proves digest lookup crosses both families rather than checking
        # only the selected target's family.
        self.shared_pcm = bytes((index * 7) & 0xFF for index in range(128))
        self.standalone_pcm_b = bytes((index * 11 + 3) & 0xFF for index in range(256))
        self.streaming_pcm_b = bytes((index * 13 + 9) & 0xFF for index in range(256))
        self.assets = (
            SimpleNamespace(
                asset_id="nfl2k5.audio.audo.o0003.c0100",
                channels=1,
                sample_rate=22_050,
                frame_count=64,
                decoded_pcm_sha256=hashlib.sha256(self.shared_pcm).hexdigest(),
            ),
            SimpleNamespace(
                asset_id="nfl2k5.audio.audo.o0003.c0101",
                channels=2,
                sample_rate=22_050,
                frame_count=64,
                decoded_pcm_sha256=hashlib.sha256(
                    self.standalone_pcm_b
                ).hexdigest(),
            ),
        )
        self.slots = (
            _slot(
                external=12,
                start=0,
                channels=1,
                owners=(_owner(200, 0), _owner(201, 0)),
            ),
            _slot(
                external=13,
                start=36,
                channels=2,
                owners=(_owner(202, 1),),
            ),
        )
        self.streaming_hashes = {
            self.slots[0].canonical_id: hashlib.sha256(self.shared_pcm).hexdigest(),
            self.slots[1].canonical_id: hashlib.sha256(
                self.streaming_pcm_b
            ).hexdigest(),
        }
        self.store = Nfl2k5AudioSourceFingerprintStore(
            expected_standalone_count=2,
            expected_streaming_slot_count=2,
            expected_streaming_owner_count=3,
            progress_interval_items=1,
        )

    def hash_slot(self, slot: CanonicalStreamingSlot) -> str:
        return self.streaming_hashes[slot.canonical_id]

    def ensure(self, **kwargs: object):
        return self.store.ensure(
            self.cache,
            self.assets,
            self.slots,
            self.hash_slot,
            **kwargs,
        )


class Nfl2k5AudioSourceFingerprintTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        # Resolve the temp root so paths the store canonicalises compare equal to
        # ours under a symlinked (macOS /private/var) or short-name (Windows) temp
        # location.
        self.fixture = FingerprintFixture(Path(self.temporary.name).resolve())

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_atomic_private_generation_load_and_deterministic_bytes(self) -> None:
        events = []
        first = self.fixture.ensure(progress=events.append)
        payload = first.path.read_bytes()
        second = self.fixture.ensure()

        self.assertEqual(first, second)
        self.assertTrue(first.private)
        self.assertFalse(first.shareable)
        self.assertEqual(first.source_sha256, SOURCE_SHA256)
        self.assertEqual(first.standalone_count, 2)
        self.assertEqual(first.streaming_slot_count, 2)
        self.assertEqual(first.streaming_owner_count, 3)
        self.assertEqual(
            first.path.parent,
            self.fixture.root / "derived",
        )
        # POSIX enforces the historical 0o600 on the private fingerprint file;
        # Windows has no group/other bits, reports 0o666 for the same file and
        # gets its confidentiality from the per-user profile root's ACL.
        self.assertEqual(stat_mode(first.path), platform_compat.private_file_mode())
        self.assertEqual(
            stat_mode(first.path), 0o666 if platform_compat.IS_WINDOWS else 0o600
        )
        self.assertEqual(
            (events[0].completed_items, events[0].total_items), (0, 4)
        )
        self.assertEqual(
            (events[-2].completed_items, events[-2].total_items), (4, 4)
        )
        self.assertEqual(events[-1].stage, "Private source-audio fingerprints ready")
        self.assertFalse(any(first.path.parent.glob("*.tmp")))

        # Regenerating the same source/catalog produces byte-identical JSON.
        first.path.unlink()
        regenerated = self.fixture.ensure()
        self.assertEqual(regenerated.path.read_bytes(), payload)

    def test_exact_pcm_lookup_and_rejection_cover_both_audio_families(self) -> None:
        inventory = self.fixture.ensure()
        matches = inventory.matches_pcm(
            self.fixture.shared_pcm,
            channels=1,
            sample_rate=22_050,
            frame_count=64,
        )
        self.assertEqual(
            tuple(match.family for match in matches),
            ("standalone", "streaming"),
        )
        with self.assertRaises(SourceDerivedPcmError) as raised:
            inventory.reject_exact_source_pcm(
                self.fixture.shared_pcm,
                channels=1,
                sample_rate=22_050,
                frame_count=64,
            )
        self.assertEqual(len(raised.exception.matches), 2)

        streaming = inventory.matches_pcm(
            self.fixture.streaming_pcm_b,
            channels=2,
            sample_rate=22_050,
            frame_count=64,
        )
        self.assertEqual(len(streaming), 1)
        self.assertEqual(streaming[0].family, "streaming")
        logical_id = self.fixture.slots[0].owners[1].asset_id
        self.assertIs(inventory.resolve(logical_id), inventory.resolve(
            self.fixture.slots[0].canonical_id
        ))

        authored = bytes((value ^ 0x55) for value in self.fixture.shared_pcm)
        inventory.reject_exact_source_pcm(
            authored,
            channels=1,
            sample_rate=22_050,
            frame_count=64,
        )
        with self.assertRaisesRegex(
            AudioSourceFingerprintError, "byte length does not match"
        ):
            inventory.matches_pcm(
                authored[:-2], channels=1, sample_rate=22_050, frame_count=64
            )

    def test_private_document_contains_metadata_not_audio_or_archive_spans(self) -> None:
        inventory = self.fixture.ensure()
        payload = inventory.path.read_bytes()
        document = json.loads(payload)
        self.assertEqual(document["privacy"], {
            "audio_payload_bytes": 0,
            "private_user_cache": True,
            "shareable": False,
        })
        self.assertNotIn(self.fixture.shared_pcm, payload)
        text = payload.decode("utf-8")
        for forbidden in (
            "RIFF", "pack_offset", "physical_spans", "range_start",
            "range_end", "selected_path", "wav_path", "encoded_payload",
        ):
            self.assertNotIn(forbidden, text)
        self.assertEqual(set(document["streaming_slots"][0]), {
            "canonical_id", "channels", "frame_count", "owner_asset_ids",
            "pcm_sha256", "sample_rate",
        })

    def test_cancel_or_hasher_failure_never_publishes_partial_inventory(self) -> None:
        calls: list[str] = []

        def hashing(slot: CanonicalStreamingSlot) -> str:
            calls.append(slot.canonical_id)
            return self.fixture.streaming_hashes[slot.canonical_id]

        with self.assertRaisesRegex(
            AudioSourceFingerprintCancelled, "no inventory was published"
        ):
            self.fixture.store.ensure(
                self.fixture.cache,
                self.fixture.assets,
                self.fixture.slots,
                hashing,
                cancelled=lambda: len(calls) == 1,
            )
        self.assertEqual(len(calls), 1)
        self.assertFalse(self.fixture.store.inventory_path(self.fixture.cache).exists())

    def test_publication_rechecks_the_owned_inode_after_rename(self) -> None:
        if platform_compat.IS_WINDOWS:
            self.skipTest(
                "requires POSIX directory-descriptor semantics -- the atomic publish pins its parent directory as an open descriptor and this test drives it through dir_fd= (os.open/os.unlink/os.stat) or reproduces an attacker by renaming/replacing a path the writer still holds open; Windows has no dir_fd, cannot open a directory descriptor, and refuses to rename or replace a path with an open handle, so this scenario cannot exist there"
            )
        real_publish = fingerprint_module._rename_noreplace_at

        def publish_then_change(
            directory_fd: int,
            source_name: str,
            destination_name: str,
        ) -> None:
            real_publish(directory_fd, source_name, destination_name)
            descriptor = os.open(destination_name, os.O_RDWR | getattr(os, "O_BINARY", 0), dir_fd=directory_fd)
            try:
                size = os.fstat(descriptor).st_size
                os.lseek(descriptor, size // 2, os.SEEK_SET)
                original = os.read(descriptor, 1)
                os.lseek(descriptor, -1, os.SEEK_CUR)
                os.write(descriptor, bytes((original[0] ^ 1,)))
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

        with mock.patch(
            "mod_editor.core.nfl2k5_audio_source_fingerprints._rename_noreplace_at",
            side_effect=publish_then_change,
        ):
            with self.assertRaisesRegex(
                AudioSourceFingerprintError, "changed during publication"
            ):
                self.fixture.ensure()
        path = self.fixture.store.inventory_path(self.fixture.cache)
        self.assertFalse(path.exists())
        self.assertEqual(tuple(path.parent.glob("*.tmp")), ())

        def failed(_slot: CanonicalStreamingSlot) -> str:
            raise RuntimeError("synthetic decoder failure")

        with self.assertRaisesRegex(RuntimeError, "synthetic decoder failure"):
            self.fixture.store.ensure(
                self.fixture.cache,
                self.fixture.assets,
                self.fixture.slots,
                failed,
            )
        self.assertFalse(self.fixture.store.inventory_path(self.fixture.cache).exists())

    def test_publication_guard_failure_before_rename_publishes_nothing(self) -> None:
        phases: list[str] = []

        def refuse(phase: str) -> None:
            phases.append(phase)
            if phase == "before_publication":
                raise RuntimeError("synthetic source authorization failure")

        with self.assertRaisesRegex(
            RuntimeError, "synthetic source authorization failure"
        ):
            self.fixture.ensure(publication_guard=refuse)
        path = self.fixture.store.inventory_path(self.fixture.cache)
        self.assertEqual(phases, ["before_publication"])
        self.assertFalse(path.exists())
        self.assertEqual(tuple(path.parent.glob("*.tmp")), ())

    def test_post_publication_guard_failure_unlinks_only_owned_inventory(self) -> None:
        phases: list[str] = []

        def fail_after_publish(phase: str) -> None:
            phases.append(phase)
            if phase == "after_publication":
                raise RuntimeError("synthetic post-publication source change")

        with self.assertRaisesRegex(
            RuntimeError, "synthetic post-publication source change"
        ):
            self.fixture.ensure(publication_guard=fail_after_publish)
        path = self.fixture.store.inventory_path(self.fixture.cache)
        self.assertEqual(phases, ["before_publication", "after_publication"])
        self.assertFalse(path.exists())
        self.assertEqual(tuple(path.parent.glob("*.tmp")), ())

    def test_publication_failure_never_unlinks_a_replacement_inode(self) -> None:
        if platform_compat.IS_WINDOWS:
            self.skipTest(
                "requires POSIX directory-descriptor semantics -- the atomic publish pins its parent directory as an open descriptor and this test drives it through dir_fd= (os.open/os.unlink/os.stat) or reproduces an attacker by renaming/replacing a path the writer still holds open; Windows has no dir_fd, cannot open a directory descriptor, and refuses to rename or replace a path with an open handle, so this scenario cannot exist there"
            )
        real_publish = fingerprint_module._rename_noreplace_at
        foreign = b"foreign replacement sentinel"

        def publish_then_replace(
            directory_fd: int,
            source_name: str,
            destination_name: str,
        ) -> None:
            real_publish(directory_fd, source_name, destination_name)
            os.unlink(destination_name, dir_fd=directory_fd)
            descriptor = os.open(
                destination_name,
                (os.O_WRONLY | os.O_CREAT | os.O_EXCL) | getattr(os, "O_BINARY", 0),
                0o600,
                dir_fd=directory_fd,
            )
            try:
                os.write(descriptor, foreign)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

        with mock.patch(
            "mod_editor.core.nfl2k5_audio_source_fingerprints._rename_noreplace_at",
            side_effect=publish_then_replace,
        ):
            with self.assertRaisesRegex(
                AudioSourceFingerprintError, "changed during publication"
            ):
                self.fixture.ensure()
        path = self.fixture.store.inventory_path(self.fixture.cache)
        self.assertEqual(path.read_bytes(), foreign)
        self.assertEqual(tuple(path.parent.glob("*.tmp")), ())

    def test_concurrent_reader_sees_only_the_complete_renamed_file(self) -> None:
        real_publish = fingerprint_module._rename_noreplace_at
        renamed = threading.Event()
        release = threading.Event()
        writer_result: list[object] = []

        def publish_then_wait(
            directory_fd: int,
            source_name: str,
            destination_name: str,
        ) -> None:
            real_publish(directory_fd, source_name, destination_name)
            renamed.set()
            if not release.wait(5):
                raise RuntimeError("synthetic concurrent reader timed out")

        def writer() -> None:
            try:
                writer_result.append(self.fixture.ensure())
            except BaseException as exc:  # pragma: no cover - asserted below
                writer_result.append(exc)

        with mock.patch(
            "mod_editor.core.nfl2k5_audio_source_fingerprints._rename_noreplace_at",
            side_effect=publish_then_wait,
        ):
            thread = threading.Thread(target=writer)
            thread.start()
            self.assertTrue(renamed.wait(5))
            try:
                reader = self.fixture.ensure()
            finally:
                release.set()
            thread.join(5)

        self.assertFalse(thread.is_alive())
        self.assertEqual(len(writer_result), 1)
        self.assertNotIsInstance(writer_result[0], BaseException)
        self.assertEqual(reader, writer_result[0])
        self.assertEqual(tuple(reader.path.parent.glob("*.tmp")), ())

    def test_semantic_tampering_fails_even_with_recomputed_integrity_fields(self) -> None:
        inventory = self.fixture.ensure()
        original = json.loads(inventory.path.read_bytes())

        cases = {
            "missing standalone": lambda doc: doc["standalone"].pop(),
            "duplicate standalone": lambda doc: doc["standalone"].append(
                dict(doc["standalone"][0])
            ),
            "wrong owner map": lambda doc: doc["streaming_slots"][0].update({
                "owner_asset_ids": [self.fixture.slots[1].owners[0].asset_id]
            }),
            "wrong shape": lambda doc: doc["streaming_slots"][0].update({
                "frame_count": 128
            }),
        }
        for label, mutate in cases.items():
            with self.subTest(label=label):
                document = json.loads(json.dumps(original))
                mutate(document)
                document["records_sha256"] = _records_hash(document)
                inventory.path.write_bytes(_canonical(document))
                with self.assertRaises(AudioSourceFingerprintError):
                    self.fixture.store.load_existing(
                        self.fixture.cache, self.fixture.assets, self.fixture.slots
                    )
                inventory.path.write_bytes(_canonical(original))

    def test_wrong_source_noncanonical_and_digest_tampering_fail_closed(self) -> None:
        inventory = self.fixture.ensure()
        original = json.loads(inventory.path.read_bytes())

        wrong_source = json.loads(json.dumps(original))
        wrong_source["source"] = {"xiso_sha256": "0" * 64}
        inventory.path.write_bytes(_canonical(wrong_source))
        with self.assertRaisesRegex(
            AudioSourceFingerprintError, "different XISO"
        ):
            self.fixture.store.load_existing(
                self.fixture.cache, self.fixture.assets, self.fixture.slots
            )

        inventory.path.write_bytes(json.dumps(original, indent=2).encode("utf-8"))
        with self.assertRaisesRegex(
            AudioSourceFingerprintError, "not canonical"
        ):
            self.fixture.store.load_existing(
                self.fixture.cache, self.fixture.assets, self.fixture.slots
            )

        changed = json.loads(json.dumps(original))
        changed["streaming_slots"][0]["pcm_sha256"] = "a" * 64
        inventory.path.write_bytes(_canonical(changed))
        with self.assertRaisesRegex(
            AudioSourceFingerprintError, "record digest does not match"
        ):
            self.fixture.store.load_existing(
                self.fixture.cache, self.fixture.assets, self.fixture.slots
            )

    def test_incomplete_inputs_and_existing_invalid_file_are_not_repaired(self) -> None:
        with self.assertRaisesRegex(
            AudioSourceFingerprintError, "Standalone fingerprint source is incomplete"
        ):
            self.fixture.store.ensure(
                self.fixture.cache,
                self.fixture.assets[:1],
                self.fixture.slots,
                self.fixture.hash_slot,
            )

        path = self.fixture.store.inventory_path(self.fixture.cache)
        path.parent.mkdir()
        path.write_bytes(b"{}\n")
        calls = 0

        def hashing(slot: CanonicalStreamingSlot) -> str:
            nonlocal calls
            calls += 1
            return self.fixture.hash_slot(slot)

        with self.assertRaises(AudioSourceFingerprintError):
            self.fixture.store.ensure(
                self.fixture.cache,
                self.fixture.assets,
                self.fixture.slots,
                hashing,
            )
        self.assertEqual(calls, 0)
        self.assertEqual(path.read_bytes(), b"{}\n")

    def test_private_derived_directory_symlink_is_rejected(self) -> None:
        outside = Path(self.temporary.name) / "outside"
        outside.mkdir()
        (self.fixture.root / "derived").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(
            AudioSourceFingerprintError, "private, non-link directory"
        ):
            self.fixture.ensure()
        self.assertEqual(tuple(outside.iterdir()), ())

    def test_existing_inventory_beneath_derived_symlink_is_rejected(self) -> None:
        inventory = self.fixture.ensure()
        derived = inventory.path.parent
        outside = Path(self.temporary.name) / "outside-derived"
        derived.rename(outside)
        derived.symlink_to(outside, target_is_directory=True)

        with self.assertRaisesRegex(
            AudioSourceFingerprintError, "private, non-link directory"
        ):
            self.fixture.store.load_existing(
                self.fixture.cache,
                self.fixture.assets,
                self.fixture.slots,
            )
        self.assertTrue((outside / inventory.path.name).is_file())

    def test_streaming_owner_and_shape_inputs_are_validated_before_hashing(self) -> None:
        calls = 0

        def hashing(slot: CanonicalStreamingSlot) -> str:
            nonlocal calls
            calls += 1
            return self.fixture.hash_slot(slot)

        duplicated_owner = replace(
            self.fixture.slots[1], owners=(self.fixture.slots[0].owners[0],)
        )
        with self.assertRaisesRegex(
            AudioSourceFingerprintError, "mapped more than once"
        ):
            self.fixture.store.ensure(
                self.fixture.cache,
                self.fixture.assets,
                (self.fixture.slots[0], duplicated_owner),
                hashing,
            )
        self.assertEqual(calls, 0)


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


if __name__ == "__main__":
    unittest.main()
