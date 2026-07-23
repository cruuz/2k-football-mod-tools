from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from mod_editor.apf_studio.models import Modification
from mod_editor.apf_studio import project


def _replacement(path: Path, *, fill: int = 0x41) -> bytes:
    data = b"\x89PNG\r\n\x1a\n" + bytes([fill]) * 4096
    path.write_bytes(data)
    return data


def _uniform_modification(path: Path, asset_index: int) -> Modification:
    data = path.read_bytes()
    return Modification(
        asset_id=f"apf:uniform:jersey:{asset_index:02d}",
        kind="uniform",
        replacement_path=path,
        replacement_sha256=hashlib.sha256(data).hexdigest(),
        metadata={
            "family": "jersey",
            "asset_index": asset_index,
            "outer_index": 1,
            "inner_index": 1,
        },
    )


class ProjectStreamingSaveTests(unittest.TestCase):
    def test_save_streams_payload_members_without_path_read_bytes_or_writestr(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            replacement = root / "replacement.png"
            data = _replacement(replacement)
            modification = _uniform_modification(replacement, 0)
            destination = root / "streamed.apf2k8mod"
            writestr_names: list[str] = []
            streamed_members: list[tuple[str, bool]] = []
            original_writestr = zipfile.ZipFile.writestr
            original_open = zipfile.ZipFile.open

            def tracked_writestr(
                archive: zipfile.ZipFile,
                name: object,
                payload: object,
                *args: object,
                **kwargs: object,
            ) -> None:
                member = name.filename if isinstance(name, zipfile.ZipInfo) else str(name)
                writestr_names.append(member)
                original_writestr(archive, name, payload, *args, **kwargs)

            def tracked_open(
                archive: zipfile.ZipFile,
                name: object,
                mode: str = "r",
                pwd: bytes | None = None,
                *,
                force_zip64: bool = False,
            ) -> object:
                member = name.filename if isinstance(name, zipfile.ZipInfo) else str(name)
                if mode == "w" and member.startswith("replacements/"):
                    streamed_members.append((member, force_zip64))
                return original_open(
                    archive,
                    name,
                    mode,
                    pwd,
                    force_zip64=force_zip64,
                )

            with patch.object(
                Path,
                "read_bytes",
                side_effect=AssertionError("save must not retain payloads via read_bytes"),
            ), patch.object(
                zipfile.ZipFile,
                "writestr",
                new=tracked_writestr,
            ), patch.object(
                zipfile.ZipFile,
                "open",
                new=tracked_open,
            ):
                project.save_project(
                    destination,
                    source_sha256="d" * 64,
                    modifications=(modification,),
                )

            self.assertEqual(writestr_names, ["project.json"])
            self.assertEqual(len(streamed_members), 1)
            self.assertTrue(streamed_members[0][1])
            with zipfile.ZipFile(destination, "r") as archive:
                self.assertEqual(archive.read(streamed_members[0][0]), data)

    def test_second_hash_rejects_same_size_change_and_preserves_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            replacement = root / "replacement.png"
            original = _replacement(replacement)
            modification = _uniform_modification(replacement, 0)
            destination = root / "existing.apf2k8mod"
            destination.write_bytes(b"existing project")
            original_writestr = zipfile.ZipFile.writestr

            def mutate_after_manifest(
                archive: zipfile.ZipFile,
                name: object,
                payload: object,
                *args: object,
                **kwargs: object,
            ) -> None:
                original_writestr(archive, name, payload, *args, **kwargs)
                member = name.filename if isinstance(name, zipfile.ZipInfo) else str(name)
                if member == "project.json":
                    replacement.write_bytes(original[:-1] + b"B")

            with patch.object(
                zipfile.ZipFile,
                "writestr",
                new=mutate_after_manifest,
            ), self.assertRaisesRegex(project.ProjectError, "changed after import"):
                project.save_project(
                    destination,
                    source_sha256="d" * 64,
                    modifications=(modification,),
                    replace=True,
                )

            self.assertEqual(destination.read_bytes(), b"existing project")
            self.assertEqual(list(root.glob(".existing.apf2k8mod.*.tmp")), [])

    def test_save_accepts_exact_member_limit_and_rejects_one_more(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            replacement = root / "replacement.png"
            _replacement(replacement)
            modifications = tuple(
                _uniform_modification(replacement, index) for index in range(3)
            )

            with patch.object(project, "MAX_PROJECT_FILES", 3):
                accepted = project.save_project(
                    root / "accepted.apf2k8mod",
                    source_sha256="d" * 64,
                    modifications=modifications[:2],
                )
                with zipfile.ZipFile(accepted, "r") as archive:
                    self.assertEqual(len(archive.infolist()), 3)
                with self.assertRaisesRegex(project.ProjectError, "file count"):
                    project.save_project(
                        root / "rejected.apf2k8mod",
                        source_sha256="d" * 64,
                        modifications=modifications,
                    )
            self.assertFalse((root / "rejected.apf2k8mod").exists())


class ProjectStructuralLimitTests(unittest.TestCase):
    def test_product_limits_cover_ratings_plus_future_audio_scale(self) -> None:
        self.assertEqual(project.MAX_PROJECT_FILES, 131_072)
        self.assertEqual(project.MAX_PROJECT_MANIFEST_BYTES, 128 * 1024 * 1024)
        self.assertEqual(project.MAX_REPLACEMENT_BYTES, 24 * 1024 * 1024)
        self.assertEqual(project.MAX_PROJECT_ARCHIVE_BYTES, 2 * 1024 * 1024 * 1024)
        self.assertEqual(project.MAX_PROJECT_EXPANDED_BYTES, 2 * 1024 * 1024 * 1024)
        self.assertGreaterEqual(project.MAX_PROJECT_FILES, 120_000)
        self.assertGreaterEqual(project.MAX_PROJECT_EXPANDED_BYTES, 1_300_000_000)

    def test_loader_accepts_exact_limits_and_rejects_each_overrun(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            replacement = root / "replacement.png"
            _replacement(replacement)
            saved = project.save_project(
                root / "limits.apf2k8mod",
                source_sha256="d" * 64,
                modifications=(_uniform_modification(replacement, 0),),
            )
            with zipfile.ZipFile(saved, "r") as archive:
                members = archive.infolist()
                manifest_size = archive.getinfo("project.json").file_size
                expanded_size = sum(item.file_size for item in members)
            archive_size = saved.stat().st_size

            with patch.object(
                project, "MAX_PROJECT_FILES", len(members)
            ), patch.object(
                project, "MAX_PROJECT_MANIFEST_BYTES", manifest_size
            ), patch.object(
                project, "MAX_PROJECT_ARCHIVE_BYTES", archive_size
            ), patch.object(
                project, "MAX_PROJECT_EXPANDED_BYTES", expanded_size
            ):
                _manifest, modifications, _annotations = project.load_project(
                    saved,
                    expected_source_sha256="d" * 64,
                    destination_dir=root / "accepted",
                )
            self.assertEqual(len(modifications), 1)

            cases = (
                ("MAX_PROJECT_FILES", len(members) - 1, "file count"),
                (
                    "MAX_PROJECT_MANIFEST_BYTES",
                    manifest_size - 1,
                    "manifest",
                ),
                (
                    "MAX_PROJECT_ARCHIVE_BYTES",
                    archive_size - 1,
                    "archive",
                ),
                (
                    "MAX_PROJECT_EXPANDED_BYTES",
                    expanded_size - 1,
                    "expands",
                ),
            )
            for constant, limit, message in cases:
                with self.subTest(constant=constant), patch.object(
                    project, constant, limit
                ), self.assertRaisesRegex(project.ProjectError, message):
                    project.load_project(
                        saved,
                        expected_source_sha256="d" * 64,
                        destination_dir=root / f"rejected-{constant}",
                    )

    def test_save_rejects_expanded_or_archive_limit_without_publishing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            replacement = root / "replacement.png"
            _replacement(replacement)
            modification = _uniform_modification(replacement, 0)

            expanded = root / "expanded.apf2k8mod"
            with patch.object(
                project, "MAX_PROJECT_EXPANDED_BYTES", 1
            ), self.assertRaisesRegex(project.ProjectError, "expands"):
                project.save_project(
                    expanded,
                    source_sha256="d" * 64,
                    modifications=(modification,),
                )
            self.assertFalse(expanded.exists())

            archived = root / "archive.apf2k8mod"
            with patch.object(
                project, "MAX_PROJECT_ARCHIVE_BYTES", 1
            ), self.assertRaisesRegex(project.ProjectError, "archive"):
                project.save_project(
                    archived,
                    source_sha256="d" * 64,
                    modifications=(modification,),
                )
            self.assertFalse(archived.exists())
            self.assertEqual(list(root.glob(".*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
