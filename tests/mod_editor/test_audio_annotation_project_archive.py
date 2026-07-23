"""Retail-free project persistence for user-authored 2K5 audio annotations."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

from mod_editor.core.errors import ValidationError
from mod_editor.studio.audio_annotations import (
    AUDIO_ANNOTATIONS_SCHEMA,
    AudioCueAnnotation,
)
from mod_editor.studio import project_archive as project_archive_module
from mod_editor.studio.project_archive import (
    load_project_archive,
    save_project_archive,
)


class _UnusedCatalog:
    def get_asset(self, _asset_id: str) -> object:
        raise AssertionError("Annotation metadata must not resolve retail assets")


def _annotation_document(*rows: dict[str, object]) -> dict[str, object]:
    return {
        "annotations": list(rows),
        "schema": AUDIO_ANNOTATIONS_SCHEMA,
    }


class AudioAnnotationProjectArchiveTests(unittest.TestCase):
    @staticmethod
    def _save(
        destination: Path,
        annotations: object,
    ) -> Path:
        return save_project_archive(
            catalog=_UnusedCatalog(),
            asset_io=object(),
            edits=(),
            destination=destination,
            audio_annotations=annotations,  # type: ignore[arg-type]
        )

    @staticmethod
    def _load(source: Path, private_root: Path):
        return load_project_archive(
            source=source,
            catalog=_UnusedCatalog(),
            asset_io=object(),
            private_root=private_root,
        )

    @staticmethod
    def _write_raw_archive(
        destination: Path,
        annotation_document: object,
        *,
        metadata_updates: dict[str, object] | None = None,
        include_annotation_member: bool = True,
        extra_members: tuple[tuple[str, bytes], ...] = (),
    ) -> Path:
        payload = (
            json.dumps(
                annotation_document,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
            + "\n"
        ).encode("utf-8")
        metadata: dict[str, object] = {
            "count": len(annotation_document.get("annotations", []))
            if isinstance(annotation_document, dict)
            else 1,
            "file": "audio-annotations.json",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size": len(payload),
        }
        if metadata_updates:
            metadata.update(metadata_updates)
        manifest = {
            "audio_annotations": metadata,
            "edits": [],
            "game": project_archive_module.PROJECT_GAME,
            "payload_policy": "user-replacements-only",
            "schema": project_archive_module.PROJECT_SCHEMA,
        }
        with zipfile.ZipFile(
            destination, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            archive.writestr(
                "project.json",
                (json.dumps(manifest, sort_keys=True) + "\n").encode("utf-8"),
            )
            if include_annotation_member:
                archive.writestr("audio-annotations.json", payload)
            for name, member_payload in extra_members:
                archive.writestr(name, member_payload)
        return destination

    def test_annotation_only_project_round_trips_without_retail_payloads(self) -> None:
        with tempfile.TemporaryDirectory(prefix="2k5-audio-annotations-") as temporary:
            root = Path(temporary)
            destination = root / "Cue Research.2k5mod"
            supplied = (
                AudioCueAnnotation(
                    "nfl2k5.audio.stream.z", "Crowd swell", "Third-down test",
                ),
                AudioCueAnnotation(
                    "nfl2k5.audio.audo.a", "Menu back — custom", "My cue note",
                ),
            )

            saved = self._save(destination, supplied)
            with zipfile.ZipFile(saved) as archive:
                self.assertEqual(
                    archive.namelist(),
                    ["project.json", "audio-annotations.json"],
                )
                manifest_payload = archive.read("project.json")
                annotation_payload = archive.read("audio-annotations.json")
            manifest = json.loads(manifest_payload)
            document = json.loads(annotation_payload)
            self.assertEqual(
                manifest["audio_annotations"],
                {
                    "count": 2,
                    "file": "audio-annotations.json",
                    "sha256": hashlib.sha256(annotation_payload).hexdigest(),
                    "size": len(annotation_payload),
                },
            )
            self.assertEqual(
                [row["cue_id"] for row in document["annotations"]],
                ["nfl2k5.audio.audo.a", "nfl2k5.audio.stream.z"],
            )
            self.assertNotIn("source", manifest)
            self.assertNotIn("original", manifest)
            self.assertNotIn("xiso", manifest)

            loaded = self._load(saved, root / "private")
            staging_root = loaded.staging_root
            try:
                self.assertEqual(loaded.edits, ())
                self.assertIsNone(loaded.text_replacements)
                self.assertEqual(loaded.audio_edits, ())
                self.assertEqual(loaded.audio_annotations, tuple(sorted(
                    supplied, key=lambda annotation: annotation.cue_id
                )))
            finally:
                loaded.cleanup()
            self.assertFalse(staging_root.exists())

    def test_recovery_document_is_normalized_and_save_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory(prefix="2k5-audio-recovery-") as temporary:
            root = Path(temporary)
            recovery_document = _annotation_document({
                "cue_id": "nfl2k5.audio.audo.o0003.c0001",
                "note": "  reviewed against a user recording  ",
                "title": "  Menu Back  ",
            })
            first = self._save(root / "first.2k5mod", recovery_document)
            second = self._save(root / "second.2k5mod", recovery_document)
            self.assertEqual(first.read_bytes(), second.read_bytes())

            loaded = self._load(first, root / "private")
            try:
                self.assertEqual(
                    loaded.audio_annotations,
                    (AudioCueAnnotation(
                        "nfl2k5.audio.audo.o0003.c0001",
                        "Menu Back",
                        "reviewed against a user recording",
                    ),),
                )
            finally:
                loaded.cleanup()

    def test_projects_without_annotation_member_remain_backward_compatible(self) -> None:
        with tempfile.TemporaryDirectory(prefix="2k5-audio-legacy-") as temporary:
            root = Path(temporary)
            legacy = save_project_archive(
                catalog=_UnusedCatalog(),
                asset_io=object(),
                edits=(),
                destination=root / "legacy.2k5mod",
                text_replacements={"schema": "synthetic-user-text/v1"},
            )
            loaded = self._load(legacy, root / "private")
            try:
                self.assertEqual(loaded.audio_annotations, ())
                self.assertEqual(
                    loaded.text_replacements,
                    {"schema": "synthetic-user-text/v1"},
                )
            finally:
                loaded.cleanup()

    def test_duplicate_json_object_keys_are_rejected_at_nested_depth(self) -> None:
        with tempfile.TemporaryDirectory(prefix="2k5-duplicate-json-") as temporary:
            root = Path(temporary)
            payload = (
                '{"annotations":[{"cue_id":"cue.one","note":"",'
                '"title":"First","title":"Second"}],'
                f'"schema":"{AUDIO_ANNOTATIONS_SCHEMA}"}}\n'
            ).encode("utf-8")
            manifest = {
                "audio_annotations": {
                    "count": 1,
                    "file": "audio-annotations.json",
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size": len(payload),
                },
                "edits": [],
                "game": project_archive_module.PROJECT_GAME,
                "payload_policy": "user-replacements-only",
                "schema": project_archive_module.PROJECT_SCHEMA,
            }
            project = root / "duplicate.2k5mod"
            with zipfile.ZipFile(project, "w") as archive:
                archive.writestr("project.json", json.dumps(manifest))
                archive.writestr("audio-annotations.json", payload)

            with self.assertRaisesRegex(ValidationError, "duplicate object key"):
                self._load(project, root / "private")
            self.assertFalse(any(root.glob("private/project-import-*")))

    def test_load_rejects_malformed_or_inconsistent_annotation_members(self) -> None:
        valid = _annotation_document({
            "cue_id": "nfl2k5.audio.audo.o0003.c0001",
            "note": "fixture note",
            "title": "Fixture title",
        })
        duplicate = _annotation_document(
            valid["annotations"][0],  # type: ignore[index]
            valid["annotations"][0],  # type: ignore[index]
        )
        control = _annotation_document({
            "cue_id": "nfl2k5.audio.audo.o0003.c0001",
            "note": "fixture\tnote",
            "title": "Fixture title",
        })
        unknown_row = _annotation_document({
            "cue_id": "nfl2k5.audio.audo.o0003.c0001",
            "note": "fixture note",
            "retail_offset": 1234,
            "title": "Fixture title",
        })
        wrong_schema = dict(valid)
        wrong_schema["schema"] = "unsupported-audio-annotations/v99"
        cases = (
            ("wrong-count", valid, {"count": 2}, True, ()),
            ("boolean-count", valid, {"count": True}, True, ()),
            ("wrong-size", valid, {"size": 1}, True, ()),
            ("wrong-checksum", valid, {"sha256": "0" * 64}, True, ()),
            ("unknown-metadata", valid, {"retail_offset": 1234}, True, ()),
            ("missing-member", valid, None, False, ()),
            ("duplicate", duplicate, None, True, ()),
            ("control", control, None, True, ()),
            ("wrong-schema", wrong_schema, None, True, ()),
            ("unknown-row-field", unknown_row, None, True, ()),
            ("undeclared", valid, None, True, (("retail.bin", b"no"),)),
        )
        with tempfile.TemporaryDirectory(prefix="2k5-audio-invalid-") as temporary:
            root = Path(temporary)
            for name, document, metadata, include, extras in cases:
                with self.subTest(name=name):
                    source = self._write_raw_archive(
                        root / f"{name}.2k5mod",
                        document,
                        metadata_updates=metadata,
                        include_annotation_member=include,
                        extra_members=extras,
                    )
                    private = root / f"private-{name}"
                    with self.assertRaises(ValidationError):
                        self._load(source, private)
                    self.assertTrue(private.is_dir())
                    self.assertEqual(tuple(private.iterdir()), ())

    def test_save_rejects_invalid_or_oversized_annotation_metadata_atomically(self) -> None:
        with tempfile.TemporaryDirectory(prefix="2k5-audio-save-bound-") as temporary:
            root = Path(temporary)
            invalid = root / "invalid.2k5mod"
            with self.assertRaisesRegex(ValidationError, "title or note"):
                self._save(invalid, _annotation_document({
                    "cue_id": "nfl2k5.audio.audo.o0003.c0001",
                    "note": "",
                    "title": "",
                }))
            self.assertFalse(invalid.exists())

            annotation = AudioCueAnnotation(
                "nfl2k5.audio.audo.o0003.c0001", "Fixture title", "Fixture note"
            )
            oversized = root / "oversized.2k5mod"
            with mock.patch.object(
                project_archive_module, "MAX_AUDIO_ANNOTATIONS_BYTES", 1
            ):
                with self.assertRaisesRegex(ValidationError, "32 MiB"):
                    self._save(oversized, (annotation,))
            self.assertFalse(oversized.exists())


if __name__ == "__main__":
    unittest.main()
