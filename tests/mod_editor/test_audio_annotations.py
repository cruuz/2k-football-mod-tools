"""Headless tests for retail-free 2K5 audio cue labels and notes."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock
import zipfile

from mod_editor.core.errors import ValidationError
from mod_editor.studio.audio_annotations import (
    AUDIO_ANNOTATIONS_SCHEMA,
    AudioCueAnnotation,
    MAX_AUDIO_ANNOTATIONS,
    MAX_NOTE_CHARS,
    MAX_TITLE_CHARS,
    MAX_TOTAL_UTF8_BYTES,
    annotation_document,
    parse_audio_annotation_document,
    validate_audio_cue_annotations,
)
from mod_editor.studio.session import StudioSession


@dataclass(frozen=True)
class _Asset:
    asset_id: str = "nfl2k5.uniform.synthetic"
    label: str = "Synthetic visual"


class _Catalog:
    def get_asset(self, _asset_id: str) -> _Asset:
        return _Asset()


class _AssetIO:
    def __init__(self, cache: object) -> None:
        root = Path(cache.root)  # type: ignore[attr-defined]
        root.mkdir(parents=True, exist_ok=True)
        self.original = root / "synthetic-original.png"
        self.original.write_bytes(b"ORIGINAL-VISUAL")

    def ensure_original(self, _asset: _Asset) -> Path:
        return self.original

    def validate_replacement(
        self, _asset: _Asset, path: Path
    ) -> tuple[bytes, bytes]:
        payload = path.read_bytes()
        return payload, payload + b"-RGBA"


class AudioAnnotationModelTests(unittest.TestCase):
    def test_record_is_immutable_bounded_and_normalizes_multiline_notes(self) -> None:
        record = AudioCueAnnotation(
            "nfl2k5.audio.ausb.o0001.c0000.r00042",
            "  Two-minute warning  ",
            "  First line\r\nSecond line\rThird line  ",
        )
        self.assertEqual(record.title, "Two-minute warning")
        self.assertEqual(record.note, "First line\nSecond line\nThird line")
        with self.assertRaises(FrozenInstanceError):
            record.title = "changed"  # type: ignore[misc]
        with self.assertRaisesRegex(ValidationError, "title is too long"):
            AudioCueAnnotation("cue", "x" * (MAX_TITLE_CHARS + 1))
        with self.assertRaisesRegex(ValidationError, "note is too long"):
            AudioCueAnnotation("cue", note="x" * (MAX_NOTE_CHARS + 1))

    def test_empty_and_control_text_is_rejected_but_note_lf_is_allowed(self) -> None:
        for values in (
            ("cue", "", ""),
            (" cue", "Title", ""),
            ("cue\n", "Title", ""),
            ("cue", "Bad\tTitle", ""),
            ("cue", "Title", "Bad\x00note"),
            ("cue", "Title", "Bad\tnote"),
            ("cue", "Direction\u061cmark", ""),
            ("cue", "Direction\u200emark", ""),
            ("cue", "Zero\ufeffwidth", ""),
        ):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                AudioCueAnnotation(*values)
        self.assertEqual(AudioCueAnnotation("cue", note="A\nB").note, "A\nB")

    def test_bidirectional_format_controls_are_rejected_in_all_text_fields(self) -> None:
        controls = tuple(
            chr(codepoint)
            for codepoint in (
                *range(0x202A, 0x202F),
                *range(0x2066, 0x206A),
            )
        )
        for control in controls:
            with self.subTest(field="title", codepoint=f"U+{ord(control):04X}"), \
                    self.assertRaisesRegex(ValidationError, "bidirectional"):
                AudioCueAnnotation("cue", f"Before{control}After")
            with self.subTest(field="note", codepoint=f"U+{ord(control):04X}"), \
                    self.assertRaisesRegex(ValidationError, "bidirectional"):
                AudioCueAnnotation("cue", "Title", f"Before{control}After")
            with self.subTest(field="cue_id", codepoint=f"U+{ord(control):04X}"), \
                    self.assertRaisesRegex(ValidationError, "bidirectional"):
                AudioCueAnnotation(f"cue{control}id", "Title")

    def test_collection_is_sorted_unique_and_has_count_and_utf8_size_caps(self) -> None:
        rows = validate_audio_cue_annotations((
            AudioCueAnnotation("cue.z", "Zulu"),
            AudioCueAnnotation("cue.a", "Alpha"),
        ))
        self.assertEqual([row.cue_id for row in rows], ["cue.a", "cue.z"])
        with self.assertRaisesRegex(ValidationError, "more than once"):
            validate_audio_cue_annotations((rows[0], rows[0]))
        with mock.patch(
            "mod_editor.studio.audio_annotations.MAX_AUDIO_ANNOTATIONS", 1
        ), self.assertRaisesRegex(ValidationError, "at most"):
            validate_audio_cue_annotations(rows)
        with mock.patch(
            "mod_editor.studio.audio_annotations.MAX_TOTAL_UTF8_BYTES", 5
        ), self.assertRaisesRegex(ValidationError, "16 MiB"):
            validate_audio_cue_annotations((AudioCueAnnotation("cue", "abc"),))
        self.assertEqual(MAX_AUDIO_ANNOTATIONS, 54_421)
        self.assertEqual(MAX_TOTAL_UTF8_BYTES, 16 * 1024 * 1024)

    def test_document_roundtrip_is_strict_canonical_and_retail_free(self) -> None:
        source = (
            AudioCueAnnotation("cue.2", note="Useful discovery"),
            AudioCueAnnotation("cue.1", "Touchdown sting"),
        )
        document = annotation_document(source)
        self.assertEqual(document["schema"], AUDIO_ANNOTATIONS_SCHEMA)
        self.assertEqual(
            [row["cue_id"] for row in document["annotations"]],  # type: ignore[index]
            ["cue.1", "cue.2"],
        )
        self.assertEqual(parse_audio_annotation_document(document), tuple(reversed(source)))
        payload = json.dumps(document, ensure_ascii=False).encode("utf-8")
        self.assertNotIn(b"RIFF", payload)
        self.assertNotIn(b"XMA", payload)

        invalid = (
            {},
            {"schema": AUDIO_ANNOTATIONS_SCHEMA, "annotations": [], "extra": True},
            {"schema": "wrong", "annotations": []},
            {"schema": AUDIO_ANNOTATIONS_SCHEMA, "annotations": {}},
            {
                "schema": AUDIO_ANNOTATIONS_SCHEMA,
                "annotations": [{"cue_id": "cue", "title": "Title"}],
            },
            {
                "schema": AUDIO_ANNOTATIONS_SCHEMA,
                "annotations": [
                    {"cue_id": "cue", "title": "One", "note": ""},
                    {"cue_id": "cue", "title": "Two", "note": ""},
                ],
            },
        )
        for document in invalid:
            with self.subTest(document=document), self.assertRaises(ValidationError):
                parse_audio_annotation_document(document)


class AudioAnnotationSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="2k5-audio-labels-")
        self.root = Path(self.temporary.name)
        cache = SimpleNamespace(
            source=SimpleNamespace(sha256="a" * 64),
            root=self.root / "private-cache",
        )
        self.patcher = mock.patch(
            "mod_editor.studio.session.Nfl2k5ProductVisualIO", _AssetIO
        )
        self.patcher.start()
        self.session = StudioSession(
            cache, _Catalog(), root=self.root / "sessions", session_id="labels"
        )

    def tearDown(self) -> None:
        self.patcher.stop()
        self.temporary.cleanup()

    def test_crud_is_undoable_metadata_and_never_becomes_a_build_edit(self) -> None:
        cue_id = "nfl2k5.audio.audo.o0003.c0042"
        self.assertTrue(self.session.set_audio_annotation(
            cue_id, "Menu swoosh", "Confirmed in the frontend."
        ))
        expected = AudioCueAnnotation(
            cue_id, "Menu swoosh", "Confirmed in the frontend."
        )
        self.assertEqual(self.session.audio_annotation(cue_id), expected)
        self.assertEqual(self.session.audio_annotations, (expected,))
        self.assertEqual(self.session.labeled_audio_asset_ids, {cue_id})
        self.assertEqual(self.session.annotation_count, 1)
        self.assertEqual(self.session.project_metadata_count, 1)
        self.assertTrue(self.session.has_project_metadata)
        self.assertEqual(self.session.modified_count, 0)
        self.assertEqual(self.session.modified_asset_ids, frozenset())
        with self.assertRaisesRegex(ValidationError, "Replace at least one asset"):
            self.session.canonical_document()

        manifest = json.loads((self.session.root / "session.json").read_bytes())
        self.assertEqual(manifest["audio_annotations"], annotation_document((expected,)))
        self.assertNotIn("wav", json.dumps(manifest).casefold())

        revision = self.session.mutation_revision
        self.assertFalse(self.session.set_audio_annotation(
            cue_id, "Menu swoosh", "Confirmed in the frontend."
        ))
        self.assertEqual(self.session.mutation_revision, revision)
        self.assertTrue(self.session.set_audio_annotation(cue_id, "Menu return", ""))
        self.assertEqual(self.session.audio_annotation(cue_id).title, "Menu return")  # type: ignore[union-attr]
        self.assertEqual(self.session.undo(), "Edit audio label: Menu return")
        self.assertEqual(self.session.audio_annotation(cue_id), expected)

        self.assertTrue(self.session.clear_audio_annotation(cue_id))
        self.assertIsNone(self.session.audio_annotation(cue_id))
        self.assertEqual(self.session.modified_count, 0)
        self.assertEqual(self.session.undo(), "Clear audio label: Menu swoosh")
        self.assertEqual(self.session.audio_annotation(cue_id), expected)

    def test_revert_all_and_undo_restore_annotation_only_project(self) -> None:
        self.session.set_audio_annotation("cue.b", "B")
        self.session.set_audio_annotation("cue.a", note="A note")
        self.assertEqual(self.session.revert_all(), 2)
        self.assertEqual(self.session.annotation_count, 0)
        self.assertEqual(self.session.modified_count, 0)
        self.assertEqual(self.session.undo(), "Revert all assets")
        self.assertEqual(
            [row.cue_id for row in self.session.audio_annotations],
            ["cue.a", "cue.b"],
        )
        self.assertEqual(self.session.modified_count, 0)

    def test_failed_annotation_only_revert_all_restores_memory_and_ledger(self) -> None:
        cue_id = "cue.transaction.revert"
        self.session.set_audio_annotation(cue_id, "Keep me")
        before_manifest = (self.session.root / "session.json").read_bytes()
        before_undo_count = len(self.session._undo_order)

        with mock.patch.object(
            self.session, "_write_manifest", side_effect=OSError("disk full")
        ), self.assertRaisesRegex(OSError, "disk full"):
            self.session.revert_all()

        self.assertEqual(
            self.session.audio_annotation(cue_id),
            AudioCueAnnotation(cue_id, "Keep me"),
        )
        self.assertEqual(len(self.session._undo_order), before_undo_count)
        self.assertEqual(
            (self.session.root / "session.json").read_bytes(), before_manifest
        )

    def test_failed_annotation_only_revert_all_undo_is_retryable(self) -> None:
        cue_id = "cue.transaction.undo"
        self.session.set_audio_annotation(cue_id, "Restore me")
        self.assertEqual(self.session.revert_all(), 1)
        empty_manifest = (self.session.root / "session.json").read_bytes()
        before_undo_count = len(self.session._undo_order)

        with mock.patch.object(
            self.session, "_write_manifest", side_effect=OSError("disk full")
        ), self.assertRaisesRegex(OSError, "disk full"):
            self.session.undo()

        self.assertEqual(self.session.annotation_count, 0)
        self.assertEqual(len(self.session._undo_order), before_undo_count)
        self.assertEqual(
            (self.session.root / "session.json").read_bytes(), empty_manifest
        )
        self.assertEqual(self.session.undo(), "Revert all assets")
        self.assertEqual(
            self.session.audio_annotation(cue_id),
            AudioCueAnnotation(cue_id, "Restore me"),
        )

    def test_failed_mixed_revert_all_restores_files_memory_and_ledgers(self) -> None:
        supplied = self.root / "user-visual.png"
        supplied.write_bytes(b"USER-VISUAL")
        self.session.replace(_Asset(), supplied)
        self.session.set_audio_annotation("cue.mixed", "Keep both")
        replacement = self.session.current_path(_Asset())
        before_manifest = (self.session.root / "session.json").read_bytes()
        before_undo = tuple(self.session._undo)
        before_order = tuple(self.session._undo_order)
        before_history = tuple(self.session.history.iterdir())

        with mock.patch.object(
            self.session, "_write_manifest", side_effect=OSError("disk full")
        ), self.assertRaisesRegex(OSError, "disk full"):
            self.session.revert_all()

        self.assertEqual(self.session.modified_count, 1)
        self.assertEqual(self.session.annotation_count, 1)
        self.assertEqual(replacement.read_bytes(), b"USER-VISUAL")
        self.assertEqual(tuple(self.session._undo), before_undo)
        self.assertEqual(tuple(self.session._undo_order), before_order)
        self.assertEqual(tuple(self.session.history.iterdir()), before_history)
        self.assertEqual(
            (self.session.root / "session.json").read_bytes(), before_manifest
        )

    def test_failed_mixed_revert_all_undo_is_retryable_without_partial_files(
        self,
    ) -> None:
        supplied = self.root / "user-visual.png"
        supplied.write_bytes(b"USER-VISUAL")
        self.session.replace(_Asset(), supplied)
        self.session.set_audio_annotation("cue.mixed.undo", "Restore both")
        self.assertEqual(self.session.revert_all(), 2)
        empty_manifest = (self.session.root / "session.json").read_bytes()
        before_undo = tuple(self.session._undo)
        before_order = tuple(self.session._undo_order)
        before_history = tuple(self.session.history.iterdir())
        self.assertFalse(any(self.session.replacements.iterdir()))

        with mock.patch.object(
            self.session, "_write_manifest", side_effect=OSError("disk full")
        ), self.assertRaisesRegex(OSError, "disk full"):
            self.session.undo()

        self.assertEqual(self.session.modified_count, 0)
        self.assertEqual(self.session.annotation_count, 0)
        self.assertFalse(any(self.session.replacements.iterdir()))
        self.assertEqual(tuple(self.session._undo), before_undo)
        self.assertEqual(tuple(self.session._undo_order), before_order)
        self.assertEqual(tuple(self.session.history.iterdir()), before_history)
        self.assertEqual(
            (self.session.root / "session.json").read_bytes(), empty_manifest
        )

        self.assertEqual(self.session.undo(), "Revert all assets")
        self.assertEqual(self.session.modified_count, 1)
        self.assertEqual(self.session.annotation_count, 1)
        self.assertEqual(
            self.session.current_path(_Asset()).read_bytes(), b"USER-VISUAL"
        )

    def test_failed_mixed_project_import_is_atomic_clean_and_retryable(self) -> None:
        supplied = self.root / "project-visual.png"
        supplied.write_bytes(b"PROJECT-VISUAL")
        self.session.replace(_Asset(), supplied)
        self.session.set_audio_annotation("cue.project", "Project label")
        project = self.root / "mixed.2k5mod"
        self.session.save_shareable_project(project)

        cache = SimpleNamespace(
            source=SimpleNamespace(sha256="a" * 64),
            root=self.root / "private-cache",
        )
        target = StudioSession(
            cache, _Catalog(), root=self.root / "sessions", session_id="import"
        )
        before_manifest = (target.root / "session.json").read_bytes()
        before_ledgers = (
            tuple(target._undo), tuple(target._crib_undo),
            tuple(target._stadium_undo), tuple(target._audio_undo),
            tuple(target._undo_order),
        )
        with mock.patch.object(
            target, "_write_manifest", side_effect=OSError("disk full")
        ), self.assertRaisesRegex(ValidationError, "disk full"):
            target.load_shareable_project(project)

        self.assertEqual(target.modified_count, 0)
        self.assertEqual(target.annotation_count, 0)
        self.assertFalse(any(target.replacements.iterdir()))
        self.assertFalse(any(target.root.glob("project-import-*")))
        self.assertEqual(
            (target.root / "session.json").read_bytes(), before_manifest
        )
        self.assertEqual(
            (
                tuple(target._undo), tuple(target._crib_undo),
                tuple(target._stadium_undo), tuple(target._audio_undo),
                tuple(target._undo_order),
            ),
            before_ledgers,
        )

        self.assertEqual(target.load_shareable_project(project), 2)
        self.assertEqual(target.modified_count, 1)
        self.assertEqual(target.annotation_count, 1)
        self.assertEqual(
            target.current_path(_Asset()).read_bytes(), b"PROJECT-VISUAL"
        )

    def test_disposable_uuid_session_removes_only_its_exact_private_root(self) -> None:
        cache = SimpleNamespace(
            source=SimpleNamespace(sha256="a" * 64),
            root=self.root / "private-cache",
        )
        candidate = StudioSession(
            cache, _Catalog(), root=self.root / "disposable-sessions"
        )
        candidate_root = candidate.root
        parent = candidate_root.parent
        sibling = parent / "keep-me"
        sibling.write_bytes(b"unrelated")

        candidate.discard_private_workspace()

        self.assertFalse(candidate_root.exists())
        self.assertEqual(sibling.read_bytes(), b"unrelated")
        self.assertTrue(parent.is_dir())

    def test_late_audio_attachment_revalidates_annotation_ids_before_binding(
        self,
    ) -> None:
        self.session.set_audio_annotation("cue.foreign", "Foreign cue")
        bad_service = SimpleNamespace(
            cache=SimpleNamespace(root=self.session.cache.root),
            resolve_playable_audio=mock.Mock(
                side_effect=ValidationError("unknown playable cue")
            ),
        )
        with self.assertRaisesRegex(ValidationError, "unknown playable cue"):
            self.session.attach_audio_service(bad_service)  # type: ignore[arg-type]
        self.assertIsNone(self.session.audio_service)

        self.session.clear_audio_annotation("cue.foreign")
        self.session.set_audio_annotation("cue.valid", "Valid cue")
        good_service = SimpleNamespace(
            cache=SimpleNamespace(root=self.session.cache.root),
            resolve_playable_audio=mock.Mock(return_value=object()),
        )
        self.session.attach_audio_service(good_service)  # type: ignore[arg-type]
        self.assertIs(self.session.audio_service, good_service)
        good_service.resolve_playable_audio.assert_called_once_with("cue.valid")

    def test_annotation_only_project_roundtrip_is_retail_free_and_not_buildable(self) -> None:
        cue_id = "nfl2k5.audio.ausb.o0001.c0000.r00042"
        expected = AudioCueAnnotation(cue_id, "Crowd swell", "Useful at kickoff")
        self.session.set_audio_annotation(cue_id, expected.title, expected.note)
        project = self.root / "labels-only.2k5mod"
        self.session.save_shareable_project(project)
        with zipfile.ZipFile(project) as archive:
            self.assertEqual(
                sorted(archive.namelist()),
                ["audio-annotations.json", "project.json"],
            )
            self.assertEqual(
                parse_audio_annotation_document(
                    json.loads(archive.read("audio-annotations.json"))
                ),
                (expected,),
            )
        self.assertNotIn(b"RIFF", project.read_bytes())

        cache = SimpleNamespace(
            source=SimpleNamespace(sha256="a" * 64),
            root=self.root / "private-cache",
        )
        loaded = StudioSession(
            cache, _Catalog(), root=self.root / "sessions", session_id="loaded"
        )
        self.assertEqual(loaded.load_shareable_project(project), 1)
        self.assertEqual(loaded.audio_annotations, (expected,))
        self.assertEqual(loaded.modified_count, 0)
        self.assertFalse(loaded.can_undo)
        with self.assertRaisesRegex(ValidationError, "Replace at least one asset"):
            loaded.canonical_document()
        with self.assertRaisesRegex(ValidationError, "fresh working session"):
            loaded.load_shareable_project(project)

    def test_failed_manifest_commit_rolls_annotation_and_undo_state_back(self) -> None:
        with mock.patch.object(
            self.session, "_write_manifest", side_effect=OSError("disk full")
        ), self.assertRaisesRegex(OSError, "disk full"):
            self.session.set_audio_annotation("cue.failure", "Never committed")
        self.assertEqual(self.session.audio_annotations, ())
        self.assertFalse(self.session.can_undo)
        self.assertEqual(self.session.modified_count, 0)


if __name__ == "__main__":
    unittest.main()
