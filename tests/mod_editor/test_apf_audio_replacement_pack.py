from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from mod_editor.core import platform_compat
from mod_editor.apf_studio.audio_replacement_pack import (
    AudioReplacementApplyProgress,
    AudioReplacementApplyReceipt,
    AudioReplacementDirectoryIdentity,
    AudioReplacementEntry,
    AudioReplacementFileIdentity,
    AudioReplacementPackError,
    AudioReplacementPackPlan,
    AudioReplacementPreviewReceipt,
    AudioReplacementTemplateReceipt,
    AudioTargetBaselineState,
    MANIFEST_FILENAME,
    MAX_PCM_PACK_SUPPLIED,
    PCM_MANIFEST_SCHEMA,
    PCM_PAYLOAD_DIRECTORY,
    README_FILENAME,
    SuppliedAudioReplacement,
    create_audio_replacement_template,
    current_audio_target_baseline,
    load_audio_replacement_pack,
    materialize_audio_replacement_pcm,
    open_audio_replacement_pack,
)
from mod_editor.apf_studio.audio_encoding import (
    ExternalXma1Encoder,
    Pcm16Target,
    export_pcm16_template,
)
from mod_editor.apf_studio.facade import ApfStudioFacade, FacadeError
from mod_editor.apf_studio.inspectors import ExportIdentity, InspectorRow
from mod_editor.apf_studio.models import (
    AUDO_EXACT_SLOT_KIND,
    AUDO_EXACT_SLOT_WRITER_SCHEMA,
    AUSB_EXACT_SLOT_KIND,
    AUSB_EXACT_SLOT_WRITER_SCHEMA,
    Modification,
)
from mod_editor.apf_studio.session import ApfSession, SessionError
import apf_audo_exact_slot
import apf_ausb_exact_slot
from mod_editor.apf_studio import audio_replacement_pack


SOURCE_SHA256 = "1" * 64


def _skip_without_directory_descriptor_transactions(test: unittest.TestCase) -> None:
    """Skip a test that can only be expressed with POSIX directory descriptors.

    The pack writer publishes atomically by pinning a directory as an open
    descriptor and addressing every step through it -- ``os.open(<dir>)`` then
    ``os.stat``/``os.rename``/``os.unlink`` with ``dir_fd=`` -- and the race
    tests below reproduce an attacker by mutating a path *while the writer still
    holds it open* (renaming it, symlinking over it, replacing its parent).
    Windows has neither of those: it cannot open a directory descriptor at all
    (``os.open`` raises ``PermissionError``), it has no ``dir_fd``, and it
    refuses to rename or replace a path with an open handle.  So the *scenario*
    these tests set up cannot exist on Windows; the POSIX guarantee they assert
    is exercised for real on Linux and macOS, where it runs unchanged.  This is
    an honest, named skip -- not a silent pass, and not a weakened assertion.
    """

    if platform_compat.IS_WINDOWS:
        test.skipTest(
            "requires POSIX directory-descriptor semantics (os.open(<dir>) / "
            "dir_fd= / mutating a path the writer holds open); unavailable on "
            "Windows"
        )


def _audo_row(outer: int = 4, inner: int = 1) -> InspectorRow:
    asset_id = f"apf:audio:audo:{outer}:{inner}"
    identity = ExportIdentity("audo", outer, inner, None, "retail-secret-name")
    return InspectorRow(
        row_id=asset_id,
        kind="audo",
        title="Retail Secret Sound Name",
        subtitle="Source-owned title must not enter a template",
        fields={
            "outer_table_index": outer,
            "inner_file_index": inner,
            "sample_rate": 22_050,
            "derived_channel_count": 1,
            "declared_sample_count": 21_604,
            "encoded_size": 0x1800,
            "packet_count": 3,
        },
        export_identity=identity,
    )


def _ausb_row(
    outer: int = 8,
    inner: int = 2,
    substream: int = 1,
    *,
    owners: tuple[str, ...] | None = None,
) -> InspectorRow:
    asset_id = f"apf:audio:ausb:{outer}:{inner}:{substream}"
    selected_owners = owners or (asset_id,)
    identity = ExportIdentity(
        "ausb_substream", outer, inner, substream, "retail-bank-name"
    )
    return InspectorRow(
        row_id=asset_id,
        kind="ausb_substream",
        title="Retail Bank Sound Name",
        subtitle="Source-owned bank title must not enter a template",
        fields={
            "outer_table_index": outer,
            "inner_file_index": inner,
            "substream_index": substream,
            "sample_rate": 48_000,
            "derived_channel_count": 2,
            "declared_sample_count": 96_000,
            "range_length": 0x1000,
            "packet_count": 2,
            "shared_owner_asset_ids": selected_owners,
        },
        export_identity=identity,
    )


def _read_manifest(root: Path) -> dict[str, object]:
    return json.loads((root / MANIFEST_FILENAME).read_text(encoding="utf-8"))


def _write_manifest(root: Path, document: dict[str, object]) -> None:
    (root / MANIFEST_FILENAME).write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _mutate_regular_file_preserving_size_and_mtime(
    parent_descriptor: int,
    name: str,
) -> None:
    """Change one byte through the pinned parent while hiding easy metadata drift."""

    before = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    descriptor = os.open(
        name,
        os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=parent_descriptor,
    )
    try:
        # platform_compat.pread, not os.pread: the latter does not exist on
        # Windows.  On POSIX it *is* os.pread, unchanged; elsewhere it is the
        # seek/read stand-in, so this fixture reads the same byte either way.
        # (The rest of this helper -- and the pack publisher it mutates -- is
        # dir_fd-relative, which Windows does not support at all, so this file
        # remains POSIX-only for that separate, product-level reason.)
        original = platform_compat.pread(descriptor, 1, 0)
        if len(original) != 1:
            raise AssertionError("ZIP fixture unexpectedly has no first byte")
        os.pwrite(descriptor, bytes((original[0] ^ 0xFF,)), 0)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.utime(
        name,
        ns=(before.st_atime_ns, before.st_mtime_ns),
        dir_fd=parent_descriptor,
        follow_symlinks=False,
    )
    after = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    if (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
        raise AssertionError("mutation fixture failed to preserve size and mtime")


class AudioReplacementTemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="apf-audio-pack-")
        self.root = Path(self.temporary.name)
        self.rows = (_audo_row(), _ausb_row())

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _template(
        self,
        name: str = "pack",
        *,
        active_modifications: tuple[Modification, ...] = (),
    ) -> Path:
        destination = self.root / name
        receipt = create_audio_replacement_template(
            self.rows,
            destination,
            source_sha256=SOURCE_SHA256,
            active_modifications=active_modifications,
        )
        self.assertEqual(receipt.path, destination)
        self.assertEqual(receipt.entry_count, 2)
        self.assertEqual(receipt.payload_count, 0)
        return destination

    def test_template_is_metadata_only_and_loads_supplied_subset(self) -> None:
        destination = self._template()
        manifest_bytes = (destination / MANIFEST_FILENAME).read_bytes()
        readme_bytes = (destination / "README.md").read_bytes()
        self.assertNotIn(b"Retail Secret", manifest_bytes)
        self.assertNotIn(b"retail-secret-name", manifest_bytes)
        self.assertNotIn(b"Retail Bank", manifest_bytes)
        self.assertIn(b"RIFF XMA1", readme_bytes)
        self.assertEqual(tuple((destination / "xma1").iterdir()), ())
        manifest = _read_manifest(destination)
        self.assertIs(manifest["payloads_included"], False)
        self.assertEqual(manifest["source"], {"sha256": SOURCE_SHA256})
        self.assertFalse(manifest["input_contract"]["wav_flac_input_supported"])

        first = manifest["entries"][0]
        payload = destination / first["replacement_file"]
        payload.write_bytes(b"user-authored placeholder; writer validates later")
        plan = load_audio_replacement_pack(
            destination,
            expected_source_sha256=SOURCE_SHA256,
            live_rows=self.rows,
        )
        self.assertEqual(plan.template_entry_count, 2)
        self.assertEqual(len(plan.supplied), 1)
        self.assertEqual(plan.missing_count, 1)
        self.assertEqual(plan.supplied[0].entry.asset_id, self.rows[0].row_id)
        self.assertEqual(plan.baseline_sha256, manifest["project_baseline"]["sha256"])

    def test_zip_template_is_metadata_only_and_byte_deterministic(self) -> None:
        left = self.root / "left.zip"
        right = self.root / "right.ZIP"
        first = create_audio_replacement_template(
            self.rows,
            left,
            source_sha256=SOURCE_SHA256,
            active_modifications=(),
            container="zip",
        )
        second = create_audio_replacement_template(
            self.rows,
            right,
            source_sha256=SOURCE_SHA256,
            active_modifications=(),
            container="zip",
        )
        self.assertEqual(first.container, "zip")
        self.assertEqual(second.container, "zip")
        self.assertEqual(left.read_bytes(), right.read_bytes())
        with zipfile.ZipFile(left, "r") as archive:
            self.assertEqual(
                archive.namelist(),
                [MANIFEST_FILENAME, README_FILENAME, "xma1/"],
            )
            self.assertFalse(any(name.endswith(".xma") for name in archive.namelist()))
            self.assertTrue(
                all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist())
            )
            self.assertNotIn(b"Retail Secret", archive.read(MANIFEST_FILENAME))

    def test_zip_prepublication_rejects_same_inode_hidden_content_mutation(self) -> None:
        _skip_without_directory_descriptor_transactions(self)
        destination = self.root / "prepublication-mutated.zip"
        original_create = audio_replacement_pack._create_audio_replacement_zip_at

        def create_then_mutate(
            parent_descriptor: int,
            staging_name: str,
            *,
            manifest_data: bytes,
        ) -> object:
            identity = original_create(
                parent_descriptor,
                staging_name,
                manifest_data=manifest_data,
            )
            _mutate_regular_file_preserving_size_and_mtime(
                parent_descriptor,
                staging_name,
            )
            return identity

        with (
            patch(
                "mod_editor.apf_studio.audio_replacement_pack._create_audio_replacement_zip_at",
                side_effect=create_then_mutate,
            ),
            self.assertRaisesRegex(
                AudioReplacementPackError,
                "staging file changed before publication",
            ),
        ):
            create_audio_replacement_template(
                self.rows,
                destination,
                source_sha256=SOURCE_SHA256,
                active_modifications=(),
                container="zip",
            )
        self.assertFalse(destination.exists())
        self.assertEqual(tuple(self.root.glob(".apf-audio-*.tmp")), ())

    def test_zip_postpublication_rejects_hidden_content_mutation_and_cleans_owned_inode(
        self,
    ) -> None:
        _skip_without_directory_descriptor_transactions(self)
        destination = self.root / "postpublication-mutated.zip"
        original_publish = audio_replacement_pack._publish_file_noreplace

        def publish_then_mutate(
            parent_descriptor: int,
            staging_name: str,
            destination_name: str,
        ) -> None:
            original_publish(
                parent_descriptor,
                staging_name,
                destination_name,
            )
            _mutate_regular_file_preserving_size_and_mtime(
                parent_descriptor,
                destination_name,
            )

        with (
            patch(
                "mod_editor.apf_studio.audio_replacement_pack._publish_file_noreplace",
                side_effect=publish_then_mutate,
            ),
            self.assertRaisesRegex(
                AudioReplacementPackError,
                "ZIP changed during publication",
            ),
        ):
            create_audio_replacement_template(
                self.rows,
                destination,
                source_sha256=SOURCE_SHA256,
                active_modifications=(),
                container="zip",
            )
        self.assertFalse(destination.exists())
        self.assertEqual(tuple(self.root.glob(".apf-audio-*.tmp")), ())

    def test_zip_failed_publication_cleanup_preserves_foreign_race_winner(self) -> None:
        _skip_without_directory_descriptor_transactions(self)
        destination = self.root / "foreign-race-winner.zip"
        moved_writer_inode = self.root / "writer-owned-moved.zip"
        foreign_bytes = b"foreign race winner must survive"
        original_publish = audio_replacement_pack._publish_file_noreplace

        def publish_then_substitute(
            parent_descriptor: int,
            staging_name: str,
            destination_name: str,
        ) -> None:
            original_publish(
                parent_descriptor,
                staging_name,
                destination_name,
            )
            os.rename(
                destination_name,
                moved_writer_inode.name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
            )
            descriptor = os.open(
                destination_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=parent_descriptor,
            )
            try:
                os.write(descriptor, foreign_bytes)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

        with (
            patch(
                "mod_editor.apf_studio.audio_replacement_pack._publish_file_noreplace",
                side_effect=publish_then_substitute,
            ),
            self.assertRaisesRegex(
                AudioReplacementPackError,
                "ZIP changed during publication",
            ),
        ):
            create_audio_replacement_template(
                self.rows,
                destination,
                source_sha256=SOURCE_SHA256,
                active_modifications=(),
                container="zip",
            )
        self.assertEqual(destination.read_bytes(), foreign_bytes)
        self.assertTrue(moved_writer_inode.is_file())

    def test_zip_content_check_rebinds_destination_name_after_hash(self) -> None:
        _skip_without_directory_descriptor_transactions(self)
        destination = self.root / "hash-time-name-race.zip"
        moved_writer_inode = self.root / "hash-time-writer-owned-moved.zip"
        foreign_bytes = b"foreign replacement during the content hash"
        original_read = audio_replacement_pack.os.read
        substituted = False

        def read_then_substitute(descriptor: int, amount: int) -> bytes:
            nonlocal substituted
            data = original_read(descriptor, amount)
            if substituted or not destination.exists():
                return data
            opened = os.fstat(descriptor)
            named = destination.stat(follow_symlinks=False)
            if (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino):
                return data
            destination.rename(moved_writer_inode)
            destination.write_bytes(foreign_bytes)
            substituted = True
            return data

        with (
            patch(
                "mod_editor.apf_studio.audio_replacement_pack.os.read",
                side_effect=read_then_substitute,
            ),
            self.assertRaisesRegex(
                AudioReplacementPackError,
                "ZIP changed during publication",
            ),
        ):
            create_audio_replacement_template(
                self.rows,
                destination,
                source_sha256=SOURCE_SHA256,
                active_modifications=(),
                container="zip",
            )
        self.assertTrue(substituted)
        self.assertEqual(destination.read_bytes(), foreign_bytes)
        self.assertTrue(moved_writer_inode.is_file())

    def test_zip_import_reports_archive_and_removes_private_extraction(self) -> None:
        template = self.root / "template.zip"
        create_audio_replacement_template(
            self.rows,
            template,
            source_sha256=SOURCE_SHA256,
            active_modifications=(),
        )
        with zipfile.ZipFile(template, "r") as archive:
            members = {
                info.filename: archive.read(info)
                for info in archive.infolist()
                if not info.is_dir()
            }
        manifest = json.loads(members[MANIFEST_FILENAME])
        replacement_name = manifest["entries"][0]["replacement_file"]
        edited = self.root / "edited.zip"
        with zipfile.ZipFile(edited, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(MANIFEST_FILENAME, members[MANIFEST_FILENAME])
            archive.writestr(README_FILENAME, members[README_FILENAME])
            archive.writestr("xma1/", b"")
            archive.writestr(replacement_name, b"user-authored xma fixture")

        extracted: Path | None = None
        with open_audio_replacement_pack(
            edited,
            expected_source_sha256=SOURCE_SHA256,
            live_rows=self.rows,
        ) as plan:
            extracted = plan.root
            self.assertNotEqual(extracted, edited)
            self.assertTrue(extracted.is_dir())
            self.assertEqual(plan.reported_root, edited)
            self.assertEqual(len(plan.supplied), 1)
            self.assertEqual(plan.supplied[0].path.read_bytes(), b"user-authored xma fixture")
        assert extracted is not None
        self.assertFalse(extracted.exists())

    def test_zip_rejects_traversal_wrapper_and_corruption_without_escape(self) -> None:
        traversal = self.root / "traversal.zip"
        with zipfile.ZipFile(traversal, "w") as archive:
            archive.writestr(MANIFEST_FILENAME, b"{}")
            archive.writestr(README_FILENAME, b"readme")
            archive.writestr("../outside.xma", b"payload")
        with self.assertRaisesRegex(AudioReplacementPackError, "escapes the pack"):
            with open_audio_replacement_pack(
                traversal,
                expected_source_sha256=SOURCE_SHA256,
                live_rows=self.rows,
            ):
                self.fail("unsafe ZIP opened")
        self.assertFalse((self.root / "outside.xma").exists())

        wrapper = self.root / "wrapper.zip"
        with zipfile.ZipFile(wrapper, "w") as archive:
            archive.writestr(f"pack/{MANIFEST_FILENAME}", b"{}")
            archive.writestr(f"pack/{README_FILENAME}", b"readme")
            archive.writestr("pack/xma1/", b"")
        with self.assertRaisesRegex(AudioReplacementPackError, "extra folder level"):
            with open_audio_replacement_pack(
                wrapper,
                expected_source_sha256=SOURCE_SHA256,
                live_rows=self.rows,
            ):
                self.fail("wrapped ZIP opened")

        corrupt = self.root / "corrupt.zip"
        corrupt.write_bytes(b"not a zip")
        with self.assertRaisesRegex(AudioReplacementPackError, "Could not open"):
            with open_audio_replacement_pack(
                corrupt,
                expected_source_sha256=SOURCE_SHA256,
                live_rows=self.rows,
            ):
                self.fail("corrupt ZIP opened")

    def test_import_pins_pack_root_before_enumeration(self) -> None:
        _skip_without_directory_descriptor_transactions(self)
        selected = self._template("root-race")
        alternate = self._template("alternate-root")
        for root, data in ((selected, b"selected"), (alternate, b"alternate")):
            manifest = _read_manifest(root)
            (root / manifest["entries"][0]["replacement_file"]).write_bytes(data)
        moved = self.root / "root-race-moved"
        original_scandir = os.scandir
        substituted = False

        def substitute_before_enumeration(path: object) -> object:
            nonlocal substituted
            if not substituted:
                substituted = True
                selected.rename(moved)
                selected.symlink_to(alternate, target_is_directory=True)
            return original_scandir(path)  # type: ignore[arg-type]

        with (
            patch(
                "mod_editor.apf_studio.audio_replacement_pack.os.scandir",
                side_effect=substitute_before_enumeration,
            ),
            self.assertRaisesRegex(
                AudioReplacementPackError,
                "folder changed",
            ),
        ):
            load_audio_replacement_pack(
                selected,
                expected_source_sha256=SOURCE_SHA256,
                live_rows=self.rows,
            )
        self.assertTrue(substituted)

    def test_output_parent_swap_cannot_publish_recreated_staging_name(self) -> None:
        _skip_without_directory_descriptor_transactions(self)
        parent = self.root / "output-parent"
        parent.mkdir()
        destination = parent / "safe-pack"
        moved_parent = self.root / "output-parent-moved"
        original_publish = audio_replacement_pack._publish_directory_noreplace
        attacker_paths: list[Path] = []

        def replace_parent_then_publish(
            parent_descriptor: int,
            staging_name: str,
            destination_name: str,
        ) -> None:
            parent.rename(moved_parent)
            parent.mkdir()
            attacker = parent / staging_name
            attacker.mkdir()
            (attacker / "attacker-marker").write_text("must survive")
            attacker_paths.append(attacker)
            original_publish(
                parent_descriptor,
                staging_name,
                destination_name,
            )

        with (
            patch(
                "mod_editor.apf_studio.audio_replacement_pack._publish_directory_noreplace",
                side_effect=replace_parent_then_publish,
            ),
            self.assertRaisesRegex(
                AudioReplacementPackError,
                "parent changed during publication",
            ),
        ):
            create_audio_replacement_template(
                self.rows,
                destination,
                source_sha256=SOURCE_SHA256,
                active_modifications=(),
            )
        self.assertFalse(destination.exists())
        self.assertFalse((moved_parent / destination.name).exists())
        self.assertEqual(len(attacker_paths), 1)
        self.assertTrue((attacker_paths[0] / "attacker-marker").is_file())

    def test_hardlinked_payload_is_rejected(self) -> None:
        destination = self._template("hardlinked-payload")
        manifest = _read_manifest(destination)
        payload = destination / manifest["entries"][0]["replacement_file"]
        outside = self.root / "outside-authored.xma"
        outside.write_bytes(b"user-authored placeholder")
        os.link(outside, payload)
        with self.assertRaisesRegex(AudioReplacementPackError, "hardlinked"):
            load_audio_replacement_pack(
                destination,
                expected_source_sha256=SOURCE_SHA256,
                live_rows=self.rows,
            )

    def test_payload_identity_is_rechecked_when_session_reads_it(self) -> None:
        original = b"A" * 64
        replacement = b"B" * 64
        for index in range(20):
            with self.subTest(iteration=index):
                destination = self._template(f"payload-swap-{index}")
                manifest = _read_manifest(destination)
                payload = destination / manifest["entries"][0]["replacement_file"]
                payload.write_bytes(original)
                plan = load_audio_replacement_pack(
                    destination,
                    expected_source_sha256=SOURCE_SHA256,
                    live_rows=self.rows,
                )
                self.assertEqual(
                    plan.supplied[0].file_identity.content_sha256,
                    hashlib.sha256(original).hexdigest(),
                )
                # Same size and immediate recreation deliberately invites inode
                # reuse and a coarse timestamp collision. Content binding must
                # still reject every iteration.
                payload.unlink()
                payload.write_bytes(replacement)
                session = _bare_session()
                with self.assertRaisesRegex(SessionError, "changed"):
                    session.apply_audio_replacement_pack(plan)
                self.assertEqual(session._modifications, {})
                self.assertEqual(session._undo, [])

    def test_baseline_is_canonical_target_only_and_retail_free(self) -> None:
        selected = _entry(self.rows[0])
        active = Modification(
            selected.asset_id,
            AUDO_EXACT_SLOT_KIND,
            Path("/private/RETAIL_SECRET_BYTES.xma1-packets"),
            "a" * 64,
            dict(selected.target),
        )
        unrelated = Modification(
            "apf:uniform:unrelated",
            "uniform",
            Path("/private/OTHER_SECRET_RETAIL_BYTES.png"),
            "b" * 64,
            {},
        )
        first = self._template(
            "baseline-first",
            active_modifications=(active, unrelated),
        )
        second = self._template(
            "baseline-second",
            active_modifications=(unrelated, active),
        )
        first_manifest = _read_manifest(first)
        second_manifest = _read_manifest(second)
        self.assertEqual(first_manifest, second_manifest)
        data = (first / MANIFEST_FILENAME).read_bytes()
        self.assertNotIn(b"RETAIL_SECRET", data)
        self.assertNotIn(b"/private/", data)
        self.assertEqual(
            first_manifest["entries"][0]["baseline"]["owners"],
            [
                {
                    "asset_id": selected.asset_id,
                    "state": "modified",
                    "kind": AUDO_EXACT_SLOT_KIND,
                    "replacement_sha256": "a" * 64,
                }
            ],
        )

    def test_changed_readme_and_hardlinked_contract_files_are_rejected(self) -> None:
        changed = self._template("changed-readme")
        (changed / "README.md").write_bytes(b"retail bytes do not belong here")
        with self.assertRaisesRegex(AudioReplacementPackError, "README changed"):
            load_audio_replacement_pack(
                changed,
                expected_source_sha256=SOURCE_SHA256,
                live_rows=self.rows,
            )

        for filename in ("README.md", MANIFEST_FILENAME):
            with self.subTest(filename=filename):
                linked = self._template(f"linked-{filename.replace('.', '-')}")
                contract = linked / filename
                outside = self.root / f"outside-{filename}"
                outside.write_bytes(contract.read_bytes())
                contract.unlink()
                os.link(outside, contract)
                with self.assertRaisesRegex(
                    AudioReplacementPackError,
                    "private regular file",
                ):
                    load_audio_replacement_pack(
                        linked,
                        expected_source_sha256=SOURCE_SHA256,
                        live_rows=self.rows,
                    )

    def test_tampered_project_baseline_digest_is_rejected(self) -> None:
        destination = self._template("tampered-baseline")
        manifest = _read_manifest(destination)
        manifest["project_baseline"]["sha256"] = "f" * 64
        _write_manifest(destination, manifest)
        with self.assertRaisesRegex(
            AudioReplacementPackError,
            "project baseline was changed",
        ):
            load_audio_replacement_pack(
                destination,
                expected_source_sha256=SOURCE_SHA256,
                live_rows=self.rows,
            )

    def test_empty_unknown_and_wrong_source_packs_are_rejected(self) -> None:
        empty = self._template("empty")
        with self.assertRaisesRegex(AudioReplacementPackError, "No pre-encoded"):
            load_audio_replacement_pack(
                empty,
                expected_source_sha256=SOURCE_SHA256,
                live_rows=self.rows,
            )

        unknown = self._template("unknown")
        (unknown / "xma1" / "not-listed.xma").write_bytes(b"unknown")
        with self.assertRaisesRegex(AudioReplacementPackError, "Unknown or unsafe"):
            load_audio_replacement_pack(
                unknown,
                expected_source_sha256=SOURCE_SHA256,
                live_rows=self.rows,
            )

        unknown_root = self._template("unknown-root")
        (unknown_root / "notes.txt").write_text("not part of the contract")
        manifest = _read_manifest(unknown_root)
        (unknown_root / manifest["entries"][0]["replacement_file"]).write_bytes(b"x")
        with self.assertRaisesRegex(AudioReplacementPackError, "Unknown file"):
            load_audio_replacement_pack(
                unknown_root,
                expected_source_sha256=SOURCE_SHA256,
                live_rows=self.rows,
            )

        different = self._template("different")
        manifest = _read_manifest(different)
        (different / manifest["entries"][0]["replacement_file"]).write_bytes(b"x")
        with self.assertRaisesRegex(AudioReplacementPackError, "different game source"):
            load_audio_replacement_pack(
                different,
                expected_source_sha256="2" * 64,
                live_rows=self.rows,
            )

    def test_duplicate_unknown_traversal_and_shape_tampering_fail_closed(self) -> None:
        cases: list[tuple[str, object, str]] = []

        def duplicate(document: dict[str, object]) -> None:
            document["entries"].append(copy.deepcopy(document["entries"][0]))
            document["entry_count"] = len(document["entries"])

        cases.append(("duplicate", duplicate, "repeats one audio identity"))

        def unknown(document: dict[str, object]) -> None:
            document["entries"][0]["asset_id"] = "apf:audio:audo:4:999"

        cases.append(("unknown", unknown, "coordinates do not match"))

        def traversal(document: dict[str, object]) -> None:
            document["entries"][0]["replacement_file"] = "../escape.xma"

        cases.append(("traversal", traversal, "generated xma1"))

        def shape(document: dict[str, object]) -> None:
            document["entries"][0]["target"]["sample_rate"] = 44_100

        cases.append(("shape", shape, "target shape or alias ownership changed"))

        for name, mutate, expected in cases:
            with self.subTest(name=name):
                destination = self._template(name)
                manifest = _read_manifest(destination)
                mutate(manifest)
                _write_manifest(destination, manifest)
                listed = manifest["entries"][0].get("replacement_file")
                if isinstance(listed, str) and listed.startswith("xma1/"):
                    (destination / listed).write_bytes(b"x")
                with self.assertRaisesRegex(AudioReplacementPackError, expected):
                    load_audio_replacement_pack(
                        destination,
                        expected_source_sha256=SOURCE_SHA256,
                        live_rows=self.rows,
                    )

    def test_alias_owner_metadata_is_source_bound(self) -> None:
        first = "apf:audio:ausb:8:2:1"
        second = "apf:audio:ausb:9:3:2"
        rows = (
            _ausb_row(8, 2, 1, owners=(first, second)),
            _ausb_row(9, 3, 2, owners=(first, second)),
        )
        destination = self.root / "aliases"
        create_audio_replacement_template(
            rows,
            destination,
            source_sha256=SOURCE_SHA256,
            active_modifications=(),
        )
        manifest = _read_manifest(destination)
        manifest["entries"][0]["target"]["shared_owner_asset_ids"] = [first]
        manifest["entries"][0]["target"]["owner_fingerprint"] = hashlib.sha256(
            first.encode("ascii")
        ).hexdigest()
        _write_manifest(destination, manifest)
        (destination / manifest["entries"][0]["replacement_file"]).write_bytes(b"x")
        with self.assertRaisesRegex(
            AudioReplacementPackError, "baseline ownership changed"
        ):
            load_audio_replacement_pack(
                destination,
                expected_source_sha256=SOURCE_SHA256,
                live_rows=rows,
            )


class PcmAudioReplacementTemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="apf-pcm-pack-")
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _write_listed_wav(pack: Path, entry: dict[str, object]) -> Path:
        target = entry["target"]
        assert isinstance(target, dict)
        destination = pack / str(entry["replacement_file"])
        export_pcm16_template(
            destination,
            Pcm16Target(
                int(target["channel_count"]),
                int(target["sample_rate"]),
                int(target["declared_sample_count"]),
                int(target["encoded_size"]),
            ),
        )
        return destination

    def test_v2_templates_are_metadata_only_and_may_list_more_than_256_targets(
        self,
    ) -> None:
        self.assertEqual(MAX_PCM_PACK_SUPPLIED, 256)
        rows = tuple(_audo_row(100 + index, index) for index in range(257))
        folder = self.root / "pcm-many"
        receipt = create_audio_replacement_template(
            rows,
            folder,
            source_sha256=SOURCE_SHA256,
            active_modifications=(),
            input_kind="pcm16",
        )
        manifest = _read_manifest(folder)
        self.assertEqual(receipt.entry_count, 257)
        self.assertEqual(receipt.input_kind, "pcm16")
        self.assertEqual(manifest["schema"], PCM_MANIFEST_SCHEMA)
        self.assertFalse(manifest["payloads_included"])
        self.assertEqual(manifest["entry_count"], 257)
        self.assertTrue(
            all(
                str(entry["replacement_file"]).startswith("pcm16/")
                and str(entry["replacement_file"]).endswith(".wav")
                for entry in manifest["entries"]
            )
        )
        self.assertEqual(tuple((folder / PCM_PAYLOAD_DIRECTORY).iterdir()), ())
        with self.assertRaisesRegex(AudioReplacementPackError, "No exact PCM16"):
            load_audio_replacement_pack(
                folder,
                expected_source_sha256=SOURCE_SHA256,
                live_rows=rows,
            )

        first = self.root / "pcm-a.zip"
        second = self.root / "pcm-b.zip"
        for destination in (first, second):
            create_audio_replacement_template(
                rows[:2],
                destination,
                source_sha256=SOURCE_SHA256,
                active_modifications=(),
                container="zip",
                input_kind="pcm16",
            )
        self.assertEqual(first.read_bytes(), second.read_bytes())
        with zipfile.ZipFile(first) as archive:
            self.assertEqual(
                archive.namelist(),
                [MANIFEST_FILENAME, README_FILENAME, "pcm16/"],
            )
            self.assertFalse(any(name.endswith(".wav") for name in archive.namelist()))

    def test_v2_folder_and_zip_auto_detect_supplied_wav_and_pin_private_copy(
        self,
    ) -> None:
        rows = (_audo_row(4, 1), _ausb_row(8, 2, 1))
        folder = self.root / "pcm-folder"
        create_audio_replacement_template(
            rows,
            folder,
            source_sha256=SOURCE_SHA256,
            active_modifications=(),
            input_kind="pcm16",
        )
        manifest = _read_manifest(folder)
        authored = self._write_listed_wav(folder, manifest["entries"][0])
        plan = load_audio_replacement_pack(
            folder,
            expected_source_sha256=SOURCE_SHA256,
            live_rows=rows,
        )
        self.assertEqual(plan.input_kind, "pcm16")
        self.assertEqual(len(plan.supplied), 1)
        self.assertEqual(plan.missing_count, 1)
        with materialize_audio_replacement_pcm(plan, plan.supplied[0]) as copied:
            self.assertNotEqual(copied, authored)
            self.assertEqual(copied.read_bytes(), authored.read_bytes())
            copied_root = copied.parent
        self.assertFalse(copied_root.exists())

        archive_path = self.root / "pcm.zip"
        create_audio_replacement_template(
            rows,
            archive_path,
            source_sha256=SOURCE_SHA256,
            active_modifications=(),
            container="zip",
            input_kind="pcm16",
        )
        with zipfile.ZipFile(archive_path, "a") as archive:
            archive.write(authored, str(manifest["entries"][0]["replacement_file"]))
        extracted: Path | None = None
        with open_audio_replacement_pack(
            archive_path,
            expected_source_sha256=SOURCE_SHA256,
            live_rows=rows,
        ) as zip_plan:
            extracted = zip_plan.root
            self.assertEqual(zip_plan.input_kind, "pcm16")
            self.assertEqual(zip_plan.reported_root, archive_path)
            self.assertEqual(len(zip_plan.supplied), 1)
        assert extracted is not None
        self.assertFalse(extracted.exists())

    def test_v2_folder_cap_fails_before_any_wav_stream_or_hash(self) -> None:
        rows = tuple(_audo_row(100 + index, index) for index in range(257))
        folder = self.root / "pcm-fail-fast-cap"
        create_audio_replacement_template(
            rows,
            folder,
            source_sha256=SOURCE_SHA256,
            active_modifications=(),
            input_kind="pcm16",
        )
        manifest = _read_manifest(folder)
        for entry in manifest["entries"]:
            destination = folder / str(entry["replacement_file"])
            destination.write_bytes(b"RIFF" + bytes(40))

        with (
            patch.object(
                audio_replacement_pack,
                "_stream_regular_bounded_at",
                side_effect=AssertionError(
                    "the 257-file cap must run before WAV stream/hash I/O"
                ),
            ) as stream_reader,
            self.assertRaisesRegex(AudioReplacementPackError, "at most 256"),
        ):
            load_audio_replacement_pack(
                folder,
                expected_source_sha256=SOURCE_SHA256,
                live_rows=rows,
            )
        stream_reader.assert_not_called()

    def test_v2_rejects_more_than_256_present_wavs_and_post_load_mutation(self) -> None:
        rows = (_audo_row(4, 1), _audo_row(5, 2))
        folder = self.root / "pcm-cap"
        create_audio_replacement_template(
            rows,
            folder,
            source_sha256=SOURCE_SHA256,
            active_modifications=(),
            input_kind="pcm16",
        )
        manifest = _read_manifest(folder)
        authored = tuple(
            self._write_listed_wav(folder, entry) for entry in manifest["entries"]
        )
        with (
            patch.object(audio_replacement_pack, "MAX_PCM_PACK_SUPPLIED", 1),
            self.assertRaisesRegex(AudioReplacementPackError, "at most 256"),
        ):
            load_audio_replacement_pack(
                folder,
                expected_source_sha256=SOURCE_SHA256,
                live_rows=rows,
            )

        plan = load_audio_replacement_pack(
            folder,
            expected_source_sha256=SOURCE_SHA256,
            live_rows=rows,
        )
        authored[0].write_bytes(authored[0].read_bytes()[:-2] + b"\x01\x00")
        with self.assertRaisesRegex(AudioReplacementPackError, "changed"):
            with materialize_audio_replacement_pcm(plan, plan.supplied[0]):
                pass


def _entry(row: InspectorRow) -> AudioReplacementEntry:
    identity = row.export_identity
    assert identity is not None
    asset_id = row.row_id
    if identity.kind == "audo":
        target = {
            "outer_table_index": identity.outer_table_index,
            "inner_file_index": identity.inner_file_index,
            "encoded_size": 0x1800,
            "sample_rate": 22_050,
            "channel_count": 1,
            "declared_sample_count": 21_604,
            "packet_count": 3,
            "writer_schema": AUDO_EXACT_SLOT_WRITER_SCHEMA,
        }
        filename = Path(f"xma1/audo-{identity.outer_table_index}.xma")
    else:
        owners = list(row.fields["shared_owner_asset_ids"])
        target = {
            "outer_table_index": identity.outer_table_index,
            "inner_file_index": identity.inner_file_index,
            "substream_index": identity.substream_index,
            "encoded_size": 0x1000,
            "sample_rate": 48_000,
            "channel_count": 2,
            "declared_sample_count": 96_000,
            "packet_count": 2,
            "shared_owner_asset_ids": owners,
            "owner_fingerprint": hashlib.sha256(
                "\n".join(owners).encode("ascii")
            ).hexdigest(),
            "writer_schema": AUSB_EXACT_SLOT_WRITER_SCHEMA,
        }
        filename = Path(
            f"xma1/ausb-{identity.outer_table_index}-{identity.substream_index}.xma"
        )
    entry = AudioReplacementEntry(
        asset_id=asset_id,
        kind=identity.kind,
        identity=identity,
        replacement_file=filename,
        target=target,
    )
    return replace(entry, baseline=current_audio_target_baseline(entry, {}))


def _modification(entry: AudioReplacementEntry, digest: str) -> Modification:
    kind = (
        AUDO_EXACT_SLOT_KIND
        if entry.kind == "audo"
        else AUSB_EXACT_SLOT_KIND
    )
    return Modification(
        asset_id=entry.asset_id,
        kind=kind,
        replacement_path=Path("/private") / f"{digest}.packets",
        replacement_sha256=digest,
        metadata=dict(entry.target),
    )


def _plan(
    entries: tuple[AudioReplacementEntry, ...],
    *,
    active_modifications: tuple[Modification, ...] = (),
    input_kind: str = "xma1",
) -> AudioReplacementPackPlan:
    modifications = {
        modification.asset_id: modification
        for modification in active_modifications
    }
    bound_entries = tuple(
        replace(
            entry,
            baseline=current_audio_target_baseline(entry, modifications),
        )
        for entry in entries
    )
    return AudioReplacementPackPlan(
        root=Path("/user/pack"),
        source_sha256=SOURCE_SHA256,
        template_entry_count=len(bound_entries),
        supplied=tuple(
            SuppliedAudioReplacement(
                entry,
                Path("/user")
                / f"{index}.{'wav' if input_kind == 'pcm16' else 'xma'}",
            )
            for index, entry in enumerate(bound_entries)
        ),
        missing_count=0,
        manifest_sha256="3" * 64,
        baseline_sha256="4" * 64,
        input_kind=input_kind,
    )


def _bare_session() -> ApfSession:
    session = ApfSession.__new__(ApfSession)
    session.source = SimpleNamespace(source_sha256=SOURCE_SHA256)
    session._modifications = {}
    session._audio_annotations = {}
    session._undo = []
    return session


class AudioReplacementAtomicSessionTests(unittest.TestCase):
    def test_preview_reports_exact_counts_and_discards_preview_only_payload(self) -> None:
        session = _bare_session()
        current_entry = _entry(_audo_row(4, 1))
        new_entry = _entry(_audo_row(5, 2))
        current = _modification(current_entry, "a" * 64)
        session._modifications = {current.asset_id: current}
        with tempfile.TemporaryDirectory(prefix="apf-audio-pack-preview-") as name:
            session.replacements_root = Path(name)
            preview_payload = session.replacements_root / (
                "b" * 64 + ".xma1-packets"
            )
            preview_payload.write_bytes(b"preview-only validated packets")
            candidate = Modification(
                new_entry.asset_id,
                AUDO_EXACT_SLOT_KIND,
                preview_payload,
                "b" * 64,
                dict(new_entry.target),
            )
            session._prepare_audo_exact_slot = Mock(
                side_effect=[current, candidate]
            )
            before = dict(session._modifications)
            receipt = session.preview_audio_replacement_pack(
                _plan(
                    (current_entry, new_entry),
                    active_modifications=(current,),
                )
            )
            self.assertFalse(preview_payload.exists())

        self.assertEqual(receipt.supplied_count, 2)
        self.assertEqual(receipt.would_change_count, 1)
        self.assertEqual(receipt.already_current_count, 1)
        self.assertEqual(receipt.current_modified_audio_count, 1)
        self.assertEqual(receipt.resulting_modified_audio_count, 2)
        self.assertEqual(receipt.validated_count, 2)
        self.assertEqual(len(receipt.confirmation_token), 64)
        self.assertEqual(session._modifications, before)
        self.assertEqual(session._undo, [])

    def test_unchanged_only_preview_succeeds_without_creating_undo(self) -> None:
        session = _bare_session()
        entry = _entry(_audo_row())
        current = _modification(entry, "a" * 64)
        session._modifications = {entry.asset_id: current}
        session._prepare_audo_exact_slot = Mock(return_value=current)

        receipt = session.preview_audio_replacement_pack(
            _plan((entry,), active_modifications=(current,))
        )

        self.assertEqual(receipt.would_change_count, 0)
        self.assertEqual(receipt.already_current_count, 1)
        self.assertEqual(receipt.current_modified_audio_count, 1)
        self.assertEqual(receipt.resulting_modified_audio_count, 1)
        self.assertEqual(session._modifications, {entry.asset_id: current})
        self.assertEqual(session._undo, [])

    def test_preview_token_allows_same_validated_pack_to_apply(self) -> None:
        session = _bare_session()
        entry = _entry(_audo_row())
        candidate = _modification(entry, "a" * 64)
        session._prepare_audo_exact_slot = Mock(return_value=candidate)
        plan = _plan((entry,))

        preview = session.preview_audio_replacement_pack(plan)
        receipt = session.apply_audio_replacement_pack(
            plan,
            confirmation_token=preview.confirmation_token,
        )

        self.assertEqual(receipt.staged_count, 1)
        self.assertEqual(session._modifications, {entry.asset_id: candidate})
        self.assertEqual(len(session._undo), 1)

    def test_preview_token_rejects_a_swapped_authored_pack_member(self) -> None:
        session = _bare_session()
        entry = _entry(_audo_row())
        candidate = _modification(entry, "c" * 64)
        base = _plan((entry,))
        root_identity = AudioReplacementDirectoryIdentity(1, 2, 3, 4, 1)
        payload_identity = AudioReplacementDirectoryIdentity(1, 3, 3, 4, 1)

        def pinned_plan(member_digest: str) -> AudioReplacementPackPlan:
            supplied = replace(
                base.supplied[0],
                file_identity=AudioReplacementFileIdentity(
                    1, 4, 123, 5, 6, member_digest
                ),
            )
            return replace(
                base,
                supplied=(supplied,),
                root_identity=root_identity,
                payload_directory_identity=payload_identity,
            )

        session._resolve_audo_identity = Mock(return_value=object())
        session._prepare_audo_exact_slot_data = Mock(return_value=candidate)
        with patch(
            "mod_editor.apf_studio.session.read_audio_replacement_payload",
            return_value=b"validated fixture XMA",
        ):
            preview = session.preview_audio_replacement_pack(pinned_plan("a" * 64))
            with self.assertRaisesRegex(SessionError, "changed after preview"):
                session.apply_audio_replacement_pack(
                    pinned_plan("b" * 64),
                    confirmation_token=preview.confirmation_token,
                )

        self.assertEqual(session._modifications, {})
        self.assertEqual(session._undo, [])

    def test_preview_token_rejects_a_changed_project_audio_revision(self) -> None:
        session = _bare_session()
        entry = _entry(_audo_row(4, 1))
        candidate = _modification(entry, "a" * 64)
        session._prepare_audo_exact_slot = Mock(return_value=candidate)
        plan = _plan((entry,))
        preview = session.preview_audio_replacement_pack(plan)
        other_entry = _entry(_audo_row(5, 2))
        other = _modification(other_entry, "b" * 64)
        session._modifications = {other.asset_id: other}

        with self.assertRaisesRegex(SessionError, "changed after preview"):
            session.apply_audio_replacement_pack(
                plan,
                confirmation_token=preview.confirmation_token,
            )

        self.assertEqual(session._modifications, {other.asset_id: other})
        self.assertEqual(session._undo, [])

    def test_two_valid_sounds_are_one_undo_action(self) -> None:
        session = _bare_session()
        prior = Modification(
            "unrelated", "uniform", Path("/private/prior"), "9" * 64, {}
        )
        session._modifications = {prior.asset_id: prior}
        audo = _entry(_audo_row())
        ausb = _entry(_ausb_row())
        audo_mod = _modification(audo, "a" * 64)
        ausb_mod = _modification(ausb, "b" * 64)
        session._prepare_audo_exact_slot = Mock(return_value=audo_mod)
        session._prepare_ausb_exact_slot = Mock(return_value=ausb_mod)

        receipt = session.apply_audio_replacement_pack(_plan((audo, ausb)))
        self.assertEqual(receipt.staged_count, 2)
        self.assertEqual(receipt.undo_action_count, 1)
        self.assertEqual(receipt.validated_count, 2)
        self.assertFalse(receipt.was_cancelled)
        self.assertEqual(len(session._undo), 1)
        self.assertEqual(session.modified_count, 3)
        self.assertTrue(session.undo())
        self.assertEqual(session._modifications, {prior.asset_id: prior})

    def test_progress_is_reported_per_complete_file(self) -> None:
        session = _bare_session()
        first = _entry(_audo_row(4, 1))
        second = _entry(_audo_row(5, 2))
        session._prepare_audo_exact_slot = Mock(
            side_effect=[
                _modification(first, "a" * 64),
                _modification(second, "b" * 64),
            ]
        )
        events: list[AudioReplacementApplyProgress] = []
        receipt = session.apply_audio_replacement_pack(
            _plan((first, second)),
            progress=events.append,
        )
        self.assertEqual(
            [(event.stage, event.completed, event.total) for event in events],
            [
                ("validating", 0, 2),
                ("validated", 1, 2),
                ("validating", 1, 2),
                ("validated", 2, 2),
                ("complete", 2, 2),
            ],
        )
        self.assertEqual(
            [event.asset_id for event in events[1:4:2]],
            [first.asset_id, second.asset_id],
        )
        self.assertEqual(receipt.validated_count, 2)

    def test_cancel_between_files_discards_private_payload_and_changes_nothing(self) -> None:
        session = _bare_session()
        prior = Modification(
            "unrelated", "uniform", Path("/private/prior"), "9" * 64, {}
        )
        session._modifications = {prior.asset_id: prior}
        first = _entry(_audo_row(4, 1))
        second = _entry(_audo_row(5, 2))
        cancel = False
        events: list[AudioReplacementApplyProgress] = []
        with tempfile.TemporaryDirectory(prefix="apf-audio-pack-cancel-") as name:
            session.replacements_root = Path(name)
            private_payload = session.replacements_root / (
                "a" * 64 + ".xma1-packets"
            )
            private_payload.write_bytes(b"new private packets")
            prepared = Modification(
                first.asset_id,
                AUDO_EXACT_SLOT_KIND,
                private_payload,
                "a" * 64,
                dict(first.target),
            )
            session._prepare_audo_exact_slot = Mock(return_value=prepared)

            def on_progress(event: AudioReplacementApplyProgress) -> None:
                nonlocal cancel
                events.append(event)
                if event.stage == "validated":
                    cancel = True

            receipt = session.apply_audio_replacement_pack(
                _plan((first, second)),
                progress=on_progress,
                cancel_requested=lambda: cancel,
            )
            self.assertFalse(private_payload.exists())
        self.assertTrue(receipt.was_cancelled)
        self.assertEqual(receipt.validated_count, 1)
        self.assertEqual(receipt.staged_count, 0)
        self.assertEqual(receipt.undo_action_count, 0)
        self.assertEqual(session._modifications, {prior.asset_id: prior})
        self.assertEqual(session._undo, [])
        session._prepare_audo_exact_slot.assert_called_once()
        self.assertEqual(events[-1].stage, "cancelled")

    def test_cancel_requested_by_last_file_progress_is_honored_before_commit(self) -> None:
        session = _bare_session()
        entry = _entry(_audo_row())
        session._prepare_audo_exact_slot = Mock(
            return_value=_modification(entry, "a" * 64)
        )
        cancel = False

        def on_progress(event: AudioReplacementApplyProgress) -> None:
            nonlocal cancel
            if event.stage == "validated":
                cancel = True

        receipt = session.apply_audio_replacement_pack(
            _plan((entry,)),
            progress=on_progress,
            cancel_requested=lambda: cancel,
        )
        self.assertTrue(receipt.was_cancelled)
        self.assertEqual(receipt.validated_count, 1)
        self.assertEqual(session._modifications, {})
        self.assertEqual(session._undo, [])

    def test_late_invalid_sound_leaves_active_map_and_undo_untouched(self) -> None:
        session = _bare_session()
        prior = Modification(
            "unrelated", "uniform", Path("/private/prior"), "9" * 64, {}
        )
        session._modifications = {prior.asset_id: prior}
        a = _entry(_audo_row(4, 1))
        b = _entry(_audo_row(5, 2))
        a_mod = _modification(a, "a" * 64)
        session._prepare_audo_exact_slot = Mock(
            side_effect=[a_mod, SessionError("second file is invalid")]
        )

        with self.assertRaisesRegex(SessionError, "second file is invalid"):
            session.apply_audio_replacement_pack(_plan((a, b)))
        self.assertEqual(session._modifications, {prior.asset_id: prior})
        self.assertEqual(session._undo, [])

    def test_failed_batch_discards_only_new_private_packet_files(self) -> None:
        session = _bare_session()
        a = _entry(_audo_row(4, 1))
        b = _entry(_audo_row(5, 2))
        with tempfile.TemporaryDirectory(prefix="apf-audio-pack-cache-") as name:
            session.replacements_root = Path(name)
            staged_path = session.replacements_root / ("a" * 64 + ".xma1-packets")
            staged_path.write_bytes(b"new private cache payload")
            first = Modification(
                a.asset_id,
                AUDO_EXACT_SLOT_KIND,
                staged_path,
                "a" * 64,
                dict(a.target),
            )
            session._prepare_audo_exact_slot = Mock(
                side_effect=[first, SessionError("late invalid file")]
            )
            with self.assertRaisesRegex(SessionError, "late invalid file"):
                session.apply_audio_replacement_pack(_plan((a, b)))
            self.assertFalse(staged_path.exists())
        self.assertEqual(session._modifications, {})
        self.assertEqual(session._undo, [])

    def test_failed_batch_preserves_packet_file_referenced_only_by_undo(self) -> None:
        session = _bare_session()
        first = _entry(_audo_row(4, 1))
        second = _entry(_audo_row(5, 2))
        with tempfile.TemporaryDirectory(prefix="apf-audio-pack-undo-") as name:
            session.replacements_root = Path(name)
            packet_path = session.replacements_root / (
                "a" * 64 + ".xma1-packets"
            )
            packet_path.write_bytes(b"packet bytes still needed by Undo")
            original = Modification(
                first.asset_id,
                AUDO_EXACT_SLOT_KIND,
                packet_path,
                "a" * 64,
                dict(first.target),
            )
            session._modifications = {first.asset_id: original}
            self.assertTrue(session.revert(first.asset_id))
            self.assertEqual(session._modifications, {})
            session._prepare_audo_exact_slot = Mock(
                side_effect=[original, SessionError("late invalid file")]
            )

            with self.assertRaisesRegex(SessionError, "late invalid file"):
                session.apply_audio_replacement_pack(_plan((first, second)))

            self.assertTrue(packet_path.exists())
            self.assertEqual(session._modifications, {})
            self.assertEqual(len(session._undo), 1)
            self.assertTrue(session.undo())
            restored = session.modification(first.asset_id)
            self.assertEqual(restored, original)
            self.assertEqual(
                restored.replacement_path.read_bytes(),
                b"packet bytes still needed by Undo",
            )

    def test_original_baseline_rejects_a_stale_active_target_before_validation(self) -> None:
        session = _bare_session()
        entry = _entry(_audo_row())
        plan = _plan((entry,))
        active = _modification(entry, "a" * 64)
        session._modifications = {entry.asset_id: active}
        session._prepare_audo_exact_slot = Mock()

        with self.assertRaisesRegex(SessionError, "changed after this template"):
            session.apply_audio_replacement_pack(plan)

        session._prepare_audo_exact_slot.assert_not_called()
        self.assertEqual(session._modifications, {entry.asset_id: active})
        self.assertEqual(session._undo, [])

    def test_pcm_stale_baseline_guidance_names_the_exact_wav(self) -> None:
        session = _bare_session()
        entry = _entry(_audo_row())
        plan = _plan((entry,), input_kind="pcm16")
        active = _modification(entry, "a" * 64)
        session._modifications = {entry.asset_id: active}
        encoder = ExternalXma1Encoder(Path("/not-run"))

        with self.assertRaises(SessionError) as raised:
            session.apply_audio_replacement_pack(plan, encoder=encoder)

        message = str(raised.exception)
        self.assertIn("add your exact PCM16 WAV again", message)
        self.assertNotIn("add your XMA1 file again", message)
        self.assertEqual(session._modifications, {entry.asset_id: active})
        self.assertEqual(session._undo, [])

    def test_modified_baseline_rejects_a_different_active_payload(self) -> None:
        session = _bare_session()
        entry = _entry(_audo_row())
        original_baseline = _modification(entry, "a" * 64)
        plan = _plan(
            (entry,),
            active_modifications=(original_baseline,),
        )
        changed = _modification(entry, "b" * 64)
        session._modifications = {entry.asset_id: changed}
        session._prepare_audo_exact_slot = Mock()

        with self.assertRaisesRegex(SessionError, "changed after this template"):
            session.apply_audio_replacement_pack(plan)

        session._prepare_audo_exact_slot.assert_not_called()
        self.assertEqual(session._modifications, {entry.asset_id: changed})
        self.assertEqual(session._undo, [])

    def test_alias_owner_not_selected_for_payload_still_participates_in_baseline(self) -> None:
        session = _bare_session()
        first_id = "apf:audio:ausb:8:2:1"
        second_id = "apf:audio:ausb:9:3:2"
        owners = (first_id, second_id)
        selected = _entry(_ausb_row(8, 2, 1, owners=owners))
        alias = _entry(_ausb_row(9, 3, 2, owners=owners))
        alias_edit = _modification(alias, "a" * 64)
        session._modifications = {alias.asset_id: alias_edit}
        session._prepare_ausb_exact_slot = Mock()

        with self.assertRaisesRegex(SessionError, "changed after this template"):
            session.apply_audio_replacement_pack(_plan((selected,)))

        session._prepare_ausb_exact_slot.assert_not_called()
        self.assertEqual(session._modifications, {alias.asset_id: alias_edit})
        self.assertEqual(session._undo, [])

    def test_baseline_is_rechecked_immediately_before_commit(self) -> None:
        session = _bare_session()
        entry = _entry(_audo_row())
        concurrent = _modification(entry, "a" * 64)
        candidate = _modification(entry, "b" * 64)

        def prepare(_identity: ExportIdentity, _path: Path) -> Modification:
            session._modifications[entry.asset_id] = concurrent
            return candidate

        session._prepare_audo_exact_slot = prepare
        with self.assertRaisesRegex(SessionError, "changed after this template"):
            session.apply_audio_replacement_pack(_plan((entry,)))
        self.assertEqual(session._modifications, {entry.asset_id: concurrent})
        self.assertEqual(session._undo, [])

    def test_complete_progress_failure_cannot_escape_after_commit(self) -> None:
        session = _bare_session()
        entry = _entry(_audo_row())
        candidate = _modification(entry, "a" * 64)
        session._prepare_audo_exact_slot = Mock(return_value=candidate)

        def progress(event: AudioReplacementApplyProgress) -> None:
            if event.stage == "complete":
                raise RuntimeError("injected UI callback failure")

        receipt = session.apply_audio_replacement_pack(
            _plan((entry,)),
            progress=progress,
        )
        self.assertEqual(receipt.staged_count, 1)
        self.assertEqual(session._modifications, {entry.asset_id: candidate})
        self.assertEqual(len(session._undo), 1)

    def test_divergent_alias_payloads_are_rejected_atomically(self) -> None:
        session = _bare_session()
        first_id = "apf:audio:ausb:8:2:1"
        second_id = "apf:audio:ausb:9:3:2"
        owners = (first_id, second_id)
        first = _entry(_ausb_row(8, 2, 1, owners=owners))
        second = _entry(_ausb_row(9, 3, 2, owners=owners))
        session._prepare_ausb_exact_slot = Mock(
            side_effect=[
                _modification(first, "a" * 64),
                _modification(second, "b" * 64),
            ]
        )

        with self.assertRaisesRegex(SessionError, "Conflicting AUSB alias"):
            session.apply_audio_replacement_pack(_plan((first, second)))
        self.assertEqual(session._modifications, {})
        self.assertEqual(session._undo, [])

    def test_identical_alias_payloads_are_accepted_for_build_deduplication(self) -> None:
        session = _bare_session()
        first_id = "apf:audio:ausb:8:2:1"
        second_id = "apf:audio:ausb:9:3:2"
        owners = (first_id, second_id)
        first = _entry(_ausb_row(8, 2, 1, owners=owners))
        second = _entry(_ausb_row(9, 3, 2, owners=owners))
        session._prepare_ausb_exact_slot = Mock(
            side_effect=[
                _modification(first, "a" * 64),
                _modification(second, "a" * 64),
            ]
        )

        receipt = session.apply_audio_replacement_pack(_plan((first, second)))
        self.assertEqual(receipt.staged_count, 2)
        self.assertEqual(session.modified_count, 2)
        self.assertEqual(
            {
                modification.replacement_sha256
                for modification in session.modifications
            },
            {"a" * 64},
        )
        self.assertTrue(session.undo())
        self.assertEqual(session.modified_count, 0)

    def test_cross_family_source_packet_is_rejected_before_batch_mutation(self) -> None:
        session = _bare_session()
        candidate = b"C" * 0x800
        safe = b"S" * 0x800
        session._audo_source_fingerprints = apf_audo_exact_slot.SourceAudioFingerprints(
            domain=apf_audo_exact_slot.SOURCE_AUDIO_DOMAIN,
            payload_sha256s=frozenset({hashlib.sha256(safe).hexdigest()}),
            packet_sha256s=frozenset({hashlib.sha256(safe).digest()}),
            payload_occurrence_count=apf_audo_exact_slot.EXPECTED_STANDALONE_AUDO_COUNT,
            packet_occurrence_count=1,
        )
        session._ausb_source_fingerprints = apf_audo_exact_slot.SourceAudioFingerprints(
            domain=apf_ausb_exact_slot.SOURCE_AUDIO_DOMAIN,
            payload_sha256s=frozenset({hashlib.sha256(candidate).hexdigest()}),
            packet_sha256s=frozenset({hashlib.sha256(candidate).digest()}),
            payload_occurrence_count=apf_ausb_exact_slot.EXPECTED_CANONICAL_RANGE_COUNT,
            packet_occurrence_count=1,
        )
        entry = _entry(_audo_row())

        def protected_prepare(
            _identity: ExportIdentity, _path: Path
        ) -> Modification:
            session._reject_any_source_audio_reuse(candidate)
            return _modification(entry, "a" * 64)

        session._prepare_audo_exact_slot = protected_prepare
        with (
            patch.object(
                apf_ausb_exact_slot,
                "EXPECTED_UNIQUE_SOURCE_PAYLOAD_HASH_COUNT",
                1,
            ),
            self.assertRaisesRegex(SessionError, "complete audio payload"),
        ):
            session.apply_audio_replacement_pack(_plan((entry,)))
        self.assertEqual(session._modifications, {})
        self.assertEqual(session._undo, [])


class PcmAudioReplacementAtomicSessionTests(unittest.TestCase):
    @staticmethod
    def _encoder() -> ExternalXma1Encoder:
        # Batch transaction tests mock the private encoder/validator boundary;
        # the executable must therefore never be inspected or launched.
        return ExternalXma1Encoder(Path("/not-run"))

    @staticmethod
    def _cached_modification(
        session: ApfSession,
        entry: AudioReplacementEntry,
        digest: str,
    ) -> Modification:
        path = session.replacements_root / f"{digest}.xma1-packets"
        path.write_bytes(f"private-{entry.asset_id}".encode("ascii"))
        kind = (
            AUDO_EXACT_SLOT_KIND
            if entry.kind == "audo"
            else AUSB_EXACT_SLOT_KIND
        )
        return Modification(
            entry.asset_id,
            kind,
            path,
            digest,
            dict(entry.target),
        )

    def test_mixed_pcm_pack_encodes_every_sound_and_commits_one_undo(self) -> None:
        session = _bare_session()
        prior = Modification(
            "unrelated", "uniform", Path("/private/prior"), "9" * 64, {}
        )
        session._modifications = {prior.asset_id: prior}
        audo = _entry(_audo_row())
        ausb = _entry(_ausb_row())
        session._prepare_audio_from_pcm = Mock(
            side_effect=[
                _modification(audo, "a" * 64),
                _modification(ausb, "b" * 64),
            ]
        )
        encoder = self._encoder()

        receipt = session.apply_audio_replacement_pack(
            _plan((audo, ausb), input_kind="pcm16"),
            encoder=encoder,
        )

        self.assertEqual(receipt.input_kind, "pcm16")
        self.assertEqual(receipt.validated_count, 2)
        self.assertEqual(receipt.staged_count, 2)
        self.assertEqual(receipt.undo_action_count, 1)
        self.assertEqual(session._prepare_audio_from_pcm.call_count, 2)
        self.assertEqual(
            [call.args[0] for call in session._prepare_audio_from_pcm.call_args_list],
            [audo.identity, ausb.identity],
        )
        self.assertTrue(
            all(
                call.args[2] is encoder
                for call in session._prepare_audio_from_pcm.call_args_list
            )
        )
        self.assertEqual(len(session._undo), 1)
        self.assertTrue(session.undo())
        self.assertEqual(session._modifications, {prior.asset_id: prior})

    def test_second_pcm_encoder_failure_removes_cache_and_changes_nothing(
        self,
    ) -> None:
        session = _bare_session()
        prior = Modification(
            "unrelated", "uniform", Path("/private/prior"), "9" * 64, {}
        )
        session._modifications = {prior.asset_id: prior}
        first = _entry(_audo_row(4, 1))
        second = _entry(_audo_row(5, 2))
        with tempfile.TemporaryDirectory(prefix="apf-pcm-pack-failure-") as name:
            session.replacements_root = Path(name)
            cached = self._cached_modification(session, first, "a" * 64)
            session._prepare_audio_from_pcm = Mock(
                side_effect=[cached, SessionError("second encoder failed")]
            )

            with self.assertRaisesRegex(SessionError, "second encoder failed"):
                session.apply_audio_replacement_pack(
                    _plan((first, second), input_kind="pcm16"),
                    encoder=self._encoder(),
                )

            self.assertFalse(cached.replacement_path.exists())
        self.assertEqual(session._modifications, {prior.asset_id: prior})
        self.assertEqual(session._undo, [])

    def test_pcm_cancellation_after_one_sound_removes_cache_and_changes_nothing(
        self,
    ) -> None:
        session = _bare_session()
        first = _entry(_audo_row(4, 1))
        second = _entry(_audo_row(5, 2))
        cancel = False
        events: list[AudioReplacementApplyProgress] = []
        with tempfile.TemporaryDirectory(prefix="apf-pcm-pack-cancel-") as name:
            session.replacements_root = Path(name)
            cached = self._cached_modification(session, first, "a" * 64)
            session._prepare_audio_from_pcm = Mock(return_value=cached)

            def on_progress(event: AudioReplacementApplyProgress) -> None:
                nonlocal cancel
                events.append(event)
                if event.stage == "validated":
                    cancel = True

            receipt = session.apply_audio_replacement_pack(
                _plan((first, second), input_kind="pcm16"),
                encoder=self._encoder(),
                progress=on_progress,
                cancel_requested=lambda: cancel,
            )

            self.assertFalse(cached.replacement_path.exists())
        self.assertTrue(receipt.was_cancelled)
        self.assertEqual(receipt.input_kind, "pcm16")
        self.assertEqual(receipt.validated_count, 1)
        self.assertEqual(receipt.staged_count, 0)
        self.assertEqual(session._prepare_audio_from_pcm.call_count, 1)
        self.assertEqual(session._modifications, {})
        self.assertEqual(session._undo, [])
        self.assertEqual(events[-1].stage, "cancelled")

    def test_divergent_pcm_aliases_remove_both_caches_and_change_nothing(
        self,
    ) -> None:
        session = _bare_session()
        first_id = "apf:audio:ausb:8:2:1"
        second_id = "apf:audio:ausb:9:3:2"
        owners = (first_id, second_id)
        first = _entry(_ausb_row(8, 2, 1, owners=owners))
        second = _entry(_ausb_row(9, 3, 2, owners=owners))
        with tempfile.TemporaryDirectory(prefix="apf-pcm-pack-alias-") as name:
            session.replacements_root = Path(name)
            first_cached = self._cached_modification(session, first, "a" * 64)
            second_cached = self._cached_modification(session, second, "b" * 64)
            session._prepare_audio_from_pcm = Mock(
                side_effect=[first_cached, second_cached]
            )

            with self.assertRaisesRegex(SessionError, "Conflicting AUSB alias"):
                session.apply_audio_replacement_pack(
                    _plan((first, second), input_kind="pcm16"),
                    encoder=self._encoder(),
                )

            self.assertFalse(first_cached.replacement_path.exists())
            self.assertFalse(second_cached.replacement_path.exists())
        self.assertEqual(session._modifications, {})
        self.assertEqual(session._undo, [])


class AudioReplacementFacadeTests(unittest.TestCase):
    def test_export_forwards_selected_rows_and_exact_source_binding(self) -> None:
        facade = ApfStudioFacade()
        facade.source = SimpleNamespace(source_sha256=SOURCE_SHA256)
        facade.session = SimpleNamespace(modifications=())
        rows = (_audo_row(), _ausb_row())
        destination = Path("/user/new-pack")
        expected = AudioReplacementTemplateReceipt(
            destination, 2, "4" * 64
        )
        progress: list[tuple[str, int, int]] = []
        with patch(
            "mod_editor.apf_studio.facade.create_audio_replacement_template",
            return_value=expected,
        ) as create:
            receipt = facade.export_audio_replacement_template(
                rows,
                destination,
                lambda stage, completed, total: progress.append(
                    (stage, completed, total)
                ),
            )
        self.assertIs(receipt, expected)
        create.assert_called_once_with(
            rows,
            destination,
            source_sha256=SOURCE_SHA256,
            active_modifications=(),
        )
        self.assertEqual(progress[0][1:], (0, 2))
        self.assertEqual(progress[-1][1:], (2, 2))

    def test_pcm_export_forwards_metadata_mode_without_changing_v1_defaults(
        self,
    ) -> None:
        facade = ApfStudioFacade()
        facade.source = SimpleNamespace(source_sha256=SOURCE_SHA256)
        facade.session = SimpleNamespace(modifications=())
        rows = (_audo_row(),)
        destination = Path("/user/new-pcm-pack.zip")
        expected = AudioReplacementTemplateReceipt(
            destination,
            1,
            "4" * 64,
            container="zip",
            input_kind="pcm16",
        )
        with patch(
            "mod_editor.apf_studio.facade.create_audio_replacement_template",
            return_value=expected,
        ) as create:
            receipt = facade.export_audio_replacement_template(
                rows,
                destination,
                container="zip",
                input_kind="pcm16",
            )
        self.assertIs(receipt, expected)
        create.assert_called_once_with(
            rows,
            destination,
            source_sha256=SOURCE_SHA256,
            active_modifications=(),
            input_kind="pcm16",
            container="zip",
        )

    def test_preview_uses_live_audio_surface_and_preserves_project_and_build(self) -> None:
        facade = ApfStudioFacade()
        facade.source = SimpleNamespace(source_sha256=SOURCE_SHA256)
        rows = (_audo_row(), _ausb_row())
        facade.inspectors = SimpleNamespace(
            audio=Mock(
                return_value=SimpleNamespace(
                    audo=SimpleNamespace(rows=(rows[0],)),
                    ausb_substreams=SimpleNamespace(rows=(rows[1],)),
                )
            )
        )
        plan = _plan((_entry(rows[0]),))
        expected = AudioReplacementPreviewReceipt(
            root=Path("/user/pack"),
            template_entry_count=2,
            supplied_count=1,
            would_change_count=1,
            already_current_count=0,
            missing_count=1,
            current_modified_audio_count=2,
            resulting_modified_audio_count=3,
            validated_count=1,
            confirmation_token="e" * 64,
        )
        cancel_hook = Mock(return_value=False)

        def preview(
            selected_plan: AudioReplacementPackPlan,
            *,
            progress: object,
            cancel_requested: object,
        ) -> AudioReplacementPreviewReceipt:
            self.assertIs(selected_plan, plan)
            self.assertIs(cancel_requested, cancel_hook)
            progress(  # type: ignore[operator]
                AudioReplacementApplyProgress("validated", 1, 1, rows[0].row_id)
            )
            return expected

        session = SimpleNamespace(
            preview_audio_replacement_pack=Mock(side_effect=preview)
        )
        facade.session = session
        prior_build = object()
        facade.last_build = prior_build
        events: list[tuple[str, int, int]] = []
        with patch(
            "mod_editor.apf_studio.facade.load_audio_replacement_pack",
            return_value=plan,
        ) as load:
            receipt = facade.preview_audio_replacement_pack(
                Path("/user/pack"),
                lambda stage, completed, total: events.append(
                    (stage, completed, total)
                ),
                cancel_requested=cancel_hook,
            )

        self.assertIs(receipt, expected)
        load.assert_called_once_with(
            Path("/user/pack"),
            expected_source_sha256=SOURCE_SHA256,
            live_rows=rows,
        )
        session.preview_audio_replacement_pack.assert_called_once()
        self.assertIs(facade.last_build, prior_build)
        self.assertTrue(any("would change" in event[0] for event in events))

    def test_apply_facade_requires_a_preview_confirmation_token(self) -> None:
        facade = ApfStudioFacade()
        facade.source = SimpleNamespace(source_sha256=SOURCE_SHA256)
        facade.session = SimpleNamespace()

        with self.assertRaisesRegex(FacadeError, "Review and fully validate"):
            facade.import_audio_replacement_pack(Path("/user/pack"))

    def test_import_uses_complete_live_audio_surface_and_invalidates_build(self) -> None:
        facade = ApfStudioFacade()
        facade.source = SimpleNamespace(source_sha256=SOURCE_SHA256)
        rows = (_audo_row(), _ausb_row())
        snapshot = SimpleNamespace(
            audo=SimpleNamespace(rows=(rows[0],)),
            ausb_substreams=SimpleNamespace(rows=(rows[1],)),
        )
        facade.inspectors = SimpleNamespace(audio=Mock(return_value=snapshot))
        plan = _plan((_entry(rows[0]),))
        expected = AudioReplacementApplyReceipt(
            Path("/user/pack"), 1, 1, 1, 0, 0, 1
        )
        def apply(
            selected_plan: AudioReplacementPackPlan,
            *,
            progress: object,
            cancel_requested: object,
            confirmation_token: str,
        ) -> AudioReplacementApplyReceipt:
            self.assertIs(selected_plan, plan)
            self.assertIs(cancel_requested, cancel_hook)
            self.assertEqual(confirmation_token, "f" * 64)
            progress(  # type: ignore[operator]
                AudioReplacementApplyProgress("validated", 1, 1, rows[0].row_id)
            )
            return expected

        session = SimpleNamespace(apply_audio_replacement_pack=Mock(side_effect=apply))
        facade.session = session
        facade.last_build = object()
        progress: list[tuple[str, int, int]] = []
        cancel_hook = Mock(return_value=False)
        with patch(
            "mod_editor.apf_studio.facade.load_audio_replacement_pack",
            return_value=plan,
        ) as load:
            receipt = facade.import_audio_replacement_pack(
                Path("/user/pack"),
                lambda stage, completed, total: progress.append(
                    (stage, completed, total)
                ),
                cancel_requested=cancel_hook,
                confirmation_token="f" * 64,
            )
        self.assertIs(receipt, expected)
        load.assert_called_once_with(
            Path("/user/pack"),
            expected_source_sha256=SOURCE_SHA256,
            live_rows=rows,
        )
        session.apply_audio_replacement_pack.assert_called_once()
        self.assertEqual(
            session.apply_audio_replacement_pack.call_args.kwargs[
                "confirmation_token"
            ],
            "f" * 64,
        )
        self.assertIsNone(facade.last_build)
        self.assertEqual(progress[0][1:], (0, 0))
        self.assertEqual(progress[-1][1:], (1, 1))
        self.assertTrue(any("Validated 1" in row[0] for row in progress))

    def test_cancelled_facade_import_preserves_last_build(self) -> None:
        facade = ApfStudioFacade()
        facade.source = SimpleNamespace(source_sha256=SOURCE_SHA256)
        row = _audo_row()
        snapshot = SimpleNamespace(
            audo=SimpleNamespace(rows=(row,)),
            ausb_substreams=SimpleNamespace(rows=()),
        )
        facade.inspectors = SimpleNamespace(audio=Mock(return_value=snapshot))
        plan = _plan((_entry(row),))
        expected = AudioReplacementApplyReceipt(
            Path("/user/pack"),
            1,
            1,
            0,
            0,
            0,
            0,
            validated_count=1,
            was_cancelled=True,
        )
        cancel_hook = Mock(return_value=True)

        def apply(
            selected_plan: AudioReplacementPackPlan,
            *,
            progress: object,
            cancel_requested: object,
            confirmation_token: str,
        ) -> AudioReplacementApplyReceipt:
            self.assertIs(selected_plan, plan)
            self.assertIs(cancel_requested, cancel_hook)
            self.assertEqual(confirmation_token, "f" * 64)
            progress(  # type: ignore[operator]
                AudioReplacementApplyProgress("cancelled", 1, 1)
            )
            return expected

        facade.session = SimpleNamespace(
            apply_audio_replacement_pack=Mock(side_effect=apply)
        )
        prior_build = object()
        facade.last_build = prior_build
        events: list[tuple[str, int, int]] = []
        with patch(
            "mod_editor.apf_studio.facade.load_audio_replacement_pack",
            return_value=plan,
        ):
            receipt = facade.import_audio_replacement_pack(
                Path("/user/pack"),
                lambda stage, completed, total: events.append(
                    (stage, completed, total)
                ),
                cancel_requested=cancel_hook,
                confirmation_token="f" * 64,
            )
        self.assertIs(receipt, expected)
        self.assertIs(facade.last_build, prior_build)
        self.assertIn("no project edits changed", events[-1][0])

    def test_pcm_import_requires_and_forwards_configured_encoder(self) -> None:
        facade = ApfStudioFacade()
        facade.source = SimpleNamespace(source_sha256=SOURCE_SHA256)
        row = _audo_row()
        snapshot = SimpleNamespace(
            audo=SimpleNamespace(rows=(row,)),
            ausb_substreams=SimpleNamespace(rows=()),
        )
        facade.inspectors = SimpleNamespace(audio=Mock(return_value=snapshot))
        plan = _plan((_entry(row),), input_kind="pcm16")
        expected = AudioReplacementApplyReceipt(
            Path("/user/pack"),
            1,
            1,
            1,
            0,
            0,
            1,
            validated_count=1,
            input_kind="pcm16",
        )
        session = SimpleNamespace(
            apply_audio_replacement_pack=Mock(return_value=expected)
        )
        facade.session = session
        prior_build = object()
        facade.last_build = prior_build
        with patch(
            "mod_editor.apf_studio.facade.load_audio_replacement_pack",
            return_value=plan,
        ):
            with self.assertRaisesRegex(
                FacadeError,
                "Choose Configure XMA1 encoder first",
            ) as raised:
                facade.import_audio_replacement_pack(
                    Path("/user/pack"), confirmation_token="f" * 64
                )
        self.assertNotIn("ExternalXma1Encoder", str(raised.exception))
        session.apply_audio_replacement_pack.assert_not_called()
        self.assertIs(facade.last_build, prior_build)

        encoder = ExternalXma1Encoder(Path("/not-run"))
        events: list[tuple[str, int, int]] = []
        with patch(
            "mod_editor.apf_studio.facade.load_audio_replacement_pack",
            return_value=plan,
        ):
            receipt = facade.import_audio_replacement_pack(
                Path("/user/pack"),
                lambda stage, completed, total: events.append(
                    (stage, completed, total)
                ),
                encoder=encoder,
                confirmation_token="f" * 64,
            )
        self.assertIs(receipt, expected)
        session.apply_audio_replacement_pack.assert_called_once()
        self.assertIs(
            session.apply_audio_replacement_pack.call_args.kwargs["encoder"],
            encoder,
        )
        self.assertIsNone(facade.last_build)
        self.assertTrue(any("PCM16 WAV" in event[0] for event in events))

    def test_facade_requires_loaded_source_for_all_pack_actions(self) -> None:
        facade = ApfStudioFacade()
        with self.assertRaisesRegex(FacadeError, "Load your APF 2K8 game first"):
            facade.export_audio_replacement_template(
                (_audo_row(),), Path("/user/new-pack")
            )
        with self.assertRaisesRegex(FacadeError, "Load your APF 2K8 game first"):
            facade.import_audio_replacement_pack(Path("/user/pack"))
        with self.assertRaisesRegex(FacadeError, "Load your APF 2K8 game first"):
            facade.preview_audio_replacement_pack(Path("/user/pack"))


class AudioReplacementAtomicContinuationTests(unittest.TestCase):
    def test_unchanged_only_is_rejected_but_mixed_pack_stages_real_changes(self) -> None:
        session = _bare_session()
        first = _entry(_audo_row(4, 1))
        first_mod = _modification(first, "a" * 64)
        session._modifications = {first.asset_id: first_mod}
        session._prepare_audo_exact_slot = Mock(return_value=first_mod)
        with self.assertRaisesRegex(SessionError, "already staged"):
            session.apply_audio_replacement_pack(
                _plan((first,), active_modifications=(first_mod,))
            )
        self.assertEqual(session._undo, [])

        second = _entry(_audo_row(5, 2))
        second_mod = _modification(second, "b" * 64)
        session._prepare_audo_exact_slot = Mock(
            side_effect=[first_mod, second_mod]
        )
        receipt = session.apply_audio_replacement_pack(
            _plan(
                (first, second),
                active_modifications=(first_mod,),
            )
        )
        self.assertEqual(receipt.staged_count, 1)
        self.assertEqual(receipt.unchanged_count, 1)
        self.assertEqual(len(session._undo), 1)

    def test_target_shape_is_rechecked_after_exact_writer_validation(self) -> None:
        session = _bare_session()
        entry = _entry(_audo_row())
        changed_target = dict(entry.target)
        changed_target["sample_rate"] = 44_100
        bad = Modification(
            entry.asset_id,
            AUDO_EXACT_SLOT_KIND,
            Path("/private/bad"),
            "a" * 64,
            changed_target,
        )
        session._prepare_audo_exact_slot = Mock(return_value=bad)
        with self.assertRaisesRegex(SessionError, "slot shape changed"):
            session.apply_audio_replacement_pack(_plan((entry,)))
        self.assertEqual(session._modifications, {})
        self.assertEqual(session._undo, [])


if __name__ == "__main__":
    unittest.main()
