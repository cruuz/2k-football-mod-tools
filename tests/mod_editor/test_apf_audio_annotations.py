"""Headless core tests for retail-free APF audio cue annotations."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock
import zipfile

from mod_editor.apf_studio.audio_annotations import (
    AUDIO_ANNOTATIONS_SCHEMA,
    AudioAnnotationError,
    AudioCueAnnotation,
    MAX_AUDIO_ANNOTATIONS,
    MAX_NOTE_CHARS,
    MAX_TITLE_CHARS,
    annotation_document,
    parse_audio_annotation_document,
    validate_audio_cue_annotations,
)
from mod_editor.apf_studio.models import Modification
from mod_editor.apf_studio.project import (
    AUDIO_ANNOTATIONS_MEMBER,
    PROJECT_SCHEMA,
    ProjectError,
    load_project,
    save_project,
)
from mod_editor.apf_studio.session import ApfSession


SOURCE_SHA256 = "d" * 64
AUDO_ID = "apf:audio:audo:5:0"
AUSB_ID = "apf:audio:ausb:137:8:0"


class AudioAnnotationModelTests(unittest.TestCase):
    def test_record_is_immutable_bounded_and_normalizes_notes(self) -> None:
        record = AudioCueAnnotation(
            AUSB_ID,
            "  Opening commentary  ",
            "  First line\r\nSecond line\rThird line  ",
        )
        self.assertEqual(record.title, "Opening commentary")
        self.assertEqual(record.note, "First line\nSecond line\nThird line")
        with self.assertRaises(FrozenInstanceError):
            record.title = "changed"  # type: ignore[misc]
        with self.assertRaisesRegex(AudioAnnotationError, "title is too long"):
            AudioCueAnnotation(AUDO_ID, "x" * (MAX_TITLE_CHARS + 1))
        with self.assertRaisesRegex(AudioAnnotationError, "note is too long"):
            AudioCueAnnotation(AUDO_ID, note="x" * (MAX_NOTE_CHARS + 1))

    def test_only_individual_playable_coordinate_ids_are_accepted(self) -> None:
        for invalid in (
            "",
            "apf:audio:ausb:137:8",
            "apf:audio:external:99",
            "apf:outer:5:inner:0",
            "apf:audio:audo:-1:0",
            " apf:audio:audo:5:0",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(
                AudioAnnotationError
            ):
                AudioCueAnnotation(invalid, "Label")
        self.assertEqual(AudioCueAnnotation(AUDO_ID, "Label").cue_id, AUDO_ID)
        self.assertEqual(AudioCueAnnotation(AUSB_ID, note="Note").cue_id, AUSB_ID)

    def test_document_is_sorted_unique_strict_and_bounded(self) -> None:
        rows = validate_audio_cue_annotations(
            (
                AudioCueAnnotation(AUSB_ID, "Zulu"),
                AudioCueAnnotation(AUDO_ID, "Alpha"),
            )
        )
        self.assertEqual(tuple(row.cue_id for row in rows), (AUDO_ID, AUSB_ID))
        document = annotation_document(reversed(rows))
        self.assertEqual(document["schema"], AUDIO_ANNOTATIONS_SCHEMA)
        self.assertEqual(parse_audio_annotation_document(document), rows)
        with self.assertRaisesRegex(AudioAnnotationError, "more than once"):
            validate_audio_cue_annotations((rows[0], rows[0]))
        with mock.patch(
            "mod_editor.apf_studio.audio_annotations.MAX_AUDIO_ANNOTATIONS", 1
        ), self.assertRaisesRegex(AudioAnnotationError, "at most"):
            validate_audio_cue_annotations(rows)
        self.assertEqual(MAX_AUDIO_ANNOTATIONS, 47_775)
        for invalid in (
            {"schema": AUDIO_ANNOTATIONS_SCHEMA, "annotations": [], "extra": 1},
            {"schema": AUDIO_ANNOTATIONS_SCHEMA, "annotations": {}},
            {
                "schema": AUDIO_ANNOTATIONS_SCHEMA,
                "annotations": [{"cue_id": AUDO_ID, "title": "Missing note"}],
            },
        ):
            with self.subTest(invalid=invalid), self.assertRaises(
                AudioAnnotationError
            ):
                parse_audio_annotation_document(invalid)

    def test_controls_and_empty_annotations_are_rejected(self) -> None:
        for values in (
            (AUDO_ID, "", ""),
            (AUDO_ID, "Bad\tTitle", ""),
            (AUDO_ID, "Title", "Bad\x00note"),
            (AUDO_ID, "Title\u202e", ""),
        ):
            with self.subTest(values=values), self.assertRaises(
                AudioAnnotationError
            ):
                AudioCueAnnotation(*values)


class AudioAnnotationProjectTests(unittest.TestCase):
    @staticmethod
    def _load(path: Path, root: Path):
        return load_project(
            path,
            expected_source_sha256=SOURCE_SHA256,
            destination_dir=root / "incoming",
        )

    def test_annotation_only_project_round_trips_without_retail_payloads(self) -> None:
        with tempfile.TemporaryDirectory(prefix="apf-label-project-") as temporary:
            root = Path(temporary)
            annotations = (
                AudioCueAnnotation(AUSB_ID, "Commentary intro", "User note"),
                AudioCueAnnotation(AUDO_ID, "Menu return"),
            )
            project = save_project(
                root / "labels.apf2k8mod",
                source_sha256=SOURCE_SHA256,
                modifications=(),
                audio_annotations=annotations,
            )
            with zipfile.ZipFile(project) as archive:
                self.assertEqual(
                    archive.namelist(),
                    ["project.json", AUDIO_ANNOTATIONS_MEMBER],
                )
                manifest_payload = archive.read("project.json")
                annotation_payload = archive.read(AUDIO_ANNOTATIONS_MEMBER)
            manifest = json.loads(manifest_payload)
            self.assertEqual(manifest["replacement_count"], 0)
            self.assertEqual(
                manifest["audio_annotations"],
                {
                    "count": 2,
                    "file": AUDIO_ANNOTATIONS_MEMBER,
                    "sha256": hashlib.sha256(annotation_payload).hexdigest(),
                    "size": len(annotation_payload),
                },
            )
            self.assertNotIn(b"RIFF", annotation_payload)
            self.assertNotIn(b"XMA", annotation_payload)
            loaded_manifest, modifications, loaded_annotations = self._load(
                project, root
            )
            self.assertEqual(loaded_manifest["schema"], PROJECT_SCHEMA)
            self.assertEqual(modifications, ())
            self.assertEqual(
                loaded_annotations,
                tuple(sorted(annotations, key=lambda row: row.cue_id)),
            )

    def test_legacy_empty_project_loads_with_no_annotations(self) -> None:
        with tempfile.TemporaryDirectory(prefix="apf-legacy-project-") as temporary:
            root = Path(temporary)
            project = save_project(
                root / "legacy.apf2k8mod",
                source_sha256=SOURCE_SHA256,
                modifications=(),
            )
            _manifest, modifications, annotations = self._load(project, root)
            self.assertEqual(modifications, ())
            self.assertEqual(annotations, ())

    @staticmethod
    def _write_raw(
        destination: Path,
        manifest_payload: bytes,
        annotation_payload: bytes | None = None,
    ) -> Path:
        with zipfile.ZipFile(destination, "w") as archive:
            archive.writestr("project.json", manifest_payload)
            if annotation_payload is not None:
                archive.writestr(AUDIO_ANNOTATIONS_MEMBER, annotation_payload)
        return destination

    def test_duplicate_keys_are_rejected_at_manifest_and_annotation_depth(self) -> None:
        with tempfile.TemporaryDirectory(prefix="apf-duplicate-json-") as temporary:
            root = Path(temporary)
            duplicate_manifest = (
                '{"schema":"apf2k8_mod_project/v1",'
                '"schema":"apf2k8_mod_project/v1"}'
            ).encode()
            with self.assertRaisesRegex(ProjectError, "duplicate object key"):
                self._load(
                    self._write_raw(root / "manifest.apf2k8mod", duplicate_manifest),
                    root,
                )

            nested_duplicate = (
                '{"schema":"apf2k8_mod_project/v1",'
                '"game":"apf2k8_xbox360",'
                '"source":{"sha256":"' + SOURCE_SHA256 + '",'
                '"sha256":"' + SOURCE_SHA256 + '"},'
                '"replacement_count":0,"replacements":[],'
                '"distribution":{"contains_original_game_bytes":false,'
                '"contains_original_preimages":false}}'
            ).encode()
            with self.assertRaisesRegex(ProjectError, "duplicate object key"):
                self._load(
                    self._write_raw(
                        root / "nested-manifest.apf2k8mod", nested_duplicate
                    ),
                    root,
                )

            annotation_payload = (
                '{"annotations":[{"cue_id":"apf:audio:audo:5:0",'
                '"title":"First","title":"Second","note":""}],'
                '"schema":"apf2k8_audio_annotations/v1"}\n'
            ).encode()
            manifest = {
                "schema": PROJECT_SCHEMA,
                "game": "apf2k8_xbox360",
                "source": {"sha256": SOURCE_SHA256},
                "replacement_count": 0,
                "replacements": [],
                "distribution": {
                    "contains_original_game_bytes": False,
                    "contains_original_preimages": False,
                },
                "audio_annotations": {
                    "count": 1,
                    "file": AUDIO_ANNOTATIONS_MEMBER,
                    "sha256": hashlib.sha256(annotation_payload).hexdigest(),
                    "size": len(annotation_payload),
                },
            }
            with self.assertRaisesRegex(ProjectError, "duplicate object key"):
                self._load(
                    self._write_raw(
                        root / "annotations.apf2k8mod",
                        json.dumps(manifest).encode(),
                        annotation_payload,
                    ),
                    root,
                )

    def test_unknown_manifest_fields_and_annotation_tampering_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="apf-hostile-label-project-") as temporary:
            root = Path(temporary)
            project = save_project(
                root / "valid.apf2k8mod",
                source_sha256=SOURCE_SHA256,
                modifications=(),
                audio_annotations=(AudioCueAnnotation(AUDO_ID, "Label"),),
            )
            with zipfile.ZipFile(project) as archive:
                manifest = json.loads(archive.read("project.json"))
                payload = archive.read(AUDIO_ANNOTATIONS_MEMBER)
            manifest["retail_preimage"] = "forbidden"
            with self.assertRaisesRegex(ProjectError, "not an APF"):
                self._load(
                    self._write_raw(
                        root / "unknown.apf2k8mod",
                        json.dumps(manifest).encode(),
                        payload,
                    ),
                    root,
                )
            manifest.pop("retail_preimage")
            for parent, key in (
                (manifest["source"], "source_offset"),
                (manifest["distribution"], "original_payload"),
            ):
                parent[key] = "forbidden"
                with self.subTest(key=key), self.assertRaises(ProjectError):
                    self._load(
                        self._write_raw(
                            root / f"unknown-{key}.apf2k8mod",
                            json.dumps(manifest).encode(),
                            payload,
                        ),
                        root,
                    )
                del parent[key]
            manifest["audio_annotations"]["sha256"] = "0" * 64
            with self.assertRaisesRegex(ProjectError, "checksum"):
                self._load(
                    self._write_raw(
                        root / "tampered.apf2k8mod",
                        json.dumps(manifest).encode(),
                        payload,
                    ),
                    root,
                )


class AudioAnnotationSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="apf-label-session-")
        self.root = Path(self.temporary.name)
        self.source = SimpleNamespace(source_sha256=SOURCE_SHA256)
        self.session = ApfSession(
            self.source,  # type: ignore[arg-type]
            SimpleNamespace(),  # type: ignore[arg-type]
            cache_root=self.root / "cache",
        )

    def tearDown(self) -> None:
        self.session.close()
        self.temporary.cleanup()

    def test_crud_is_undoable_metadata_and_not_a_build_edit(self) -> None:
        self.assertTrue(
            self.session.set_audio_annotation(AUDO_ID, "Menu return", "User note")
        )
        self.assertEqual(self.session.annotation_count, 1)
        self.assertEqual(self.session.project_metadata_count, 1)
        self.assertEqual(self.session.project_change_count, 1)
        self.assertTrue(self.session.has_project_metadata)
        self.assertEqual(self.session.modified_count, 0)
        self.assertEqual(self.session.modified_asset_ids, frozenset())
        self.assertFalse(
            self.session.set_audio_annotation(AUDO_ID, "Menu return", "User note")
        )
        self.assertTrue(self.session.clear_audio_annotation(AUDO_ID))
        self.assertIsNone(self.session.audio_annotation(AUDO_ID))
        self.assertTrue(self.session.undo())
        self.assertEqual(self.session.audio_annotation(AUDO_ID).title, "Menu return")  # type: ignore[union-attr]

    def test_revert_all_and_undo_restore_edits_and_annotations_together(self) -> None:
        payload = self.root / "replacement.png"
        payload.write_bytes(b"user replacement")
        modification = Modification(
            asset_id="apf:uniform:jersey:00",
            kind="uniform",
            replacement_path=payload,
            replacement_sha256=hashlib.sha256(payload.read_bytes()).hexdigest(),
            metadata={},
        )
        self.session._modifications[modification.asset_id] = modification
        self.session._audio_annotations[AUDO_ID] = AudioCueAnnotation(
            AUDO_ID, "Menu return"
        )
        self.session._undo.clear()
        self.assertEqual(self.session.revert_all(), 2)
        self.assertEqual(self.session.project_change_count, 0)
        self.assertTrue(self.session.undo())
        self.assertEqual(self.session.modified_asset_ids, {modification.asset_id})
        self.assertEqual(self.session.labeled_audio_asset_ids, {AUDO_ID})

    def test_annotation_only_project_persists_and_load_is_undoable(self) -> None:
        self.session.set_audio_annotation(AUSB_ID, "Opening call", "User note")
        project = self.session.save_project(self.root / "labels.apf2k8mod")
        loaded = ApfSession(
            self.source,  # type: ignore[arg-type]
            SimpleNamespace(),  # type: ignore[arg-type]
            cache_root=self.root / "loaded-cache",
        )
        try:
            loaded.set_audio_annotation(AUDO_ID, "Prior label")
            self.assertEqual(loaded.load_project(project), 0)
            self.assertEqual(loaded.labeled_audio_asset_ids, {AUSB_ID})
            self.assertEqual(loaded.modified_count, 0)
            self.assertTrue(loaded.undo())
            self.assertEqual(loaded.labeled_audio_asset_ids, {AUDO_ID})
        finally:
            loaded.close()


if __name__ == "__main__":
    unittest.main()
