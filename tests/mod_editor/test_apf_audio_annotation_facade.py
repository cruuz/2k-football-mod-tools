"""Headless APF facade and export tests for user cue metadata."""

from __future__ import annotations

import csv
from io import StringIO
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock
import zipfile

from mod_editor.apf_studio.asset_io import ApfAssetIO
from mod_editor.apf_studio.audio_annotations import AudioCueAnnotation
from mod_editor.apf_studio.facade import ApfStudioFacade, FacadeError
from mod_editor.apf_studio.inspectors import (
    AudioSnapshot,
    ExportIdentity,
    PagedModel,
    _row,
)
from mod_editor.apf_studio.project import ProjectError, save_project
from mod_editor.apf_studio.session import ApfSession


SOURCE_SHA256 = "d" * 64
CUE_ID = "apf:audio:audo:5:0"


class _ExportIO:
    def export_audio_identity(
        self, _identity: ExportIdentity, destination: Path
    ) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"user-private-xma-export")
        return destination

    def export_audio_bundle(self, *args: object, **kwargs: object) -> Path:
        return ApfAssetIO.export_audio_bundle(self, *args, **kwargs)  # type: ignore[arg-type]


class _Inspectors:
    def __init__(self, snapshot: AudioSnapshot) -> None:
        self.snapshot = snapshot

    def audio(self) -> AudioSnapshot:
        return self.snapshot


def _audio_row():
    identity = ExportIdentity("audo", 5, 0, None, "menu-return")
    return _row(
        CUE_ID,
        "audo",
        "menu_return",
        "AUDIO · outer 5 / inner 0",
        {
            "audio_source_id": "audo:standalone",
            "audio_source_label": "Standalone AUDO",
            "role_id": "ui_menu_sfx",
            "role_label": "UI & Menu SFX",
            "role_basis": "Name heuristic only",
            "audio_format": "XMA1",
            "sample_rate": 44_100,
            "derived_channel_count": 1,
            "duration_seconds": 1.25,
            "packet_count": 2,
            "encoded_size": 4_096,
            "outer_table_index": 5,
            "inner_file_index": 0,
        },
        export_identity=identity,
    )


class AudioAnnotationFacadeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="apf-label-facade-")
        self.root = Path(self.temporary.name)
        self.row = _audio_row()
        snapshot = AudioSnapshot(
            summary={
                "audo": 1,
                "ausb_banks": 0,
                "ausb_substreams": 0,
                "external_bins": 0,
            },
            audo=PagedModel((self.row,)),
            ausb_banks=PagedModel(()),
            ausb_substreams=PagedModel(()),
            external_banks=PagedModel(()),
        )
        self.source = SimpleNamespace(source_sha256=SOURCE_SHA256)
        self.facade = ApfStudioFacade(cache_root=self.root / "cache")
        self.facade.source = self.source  # type: ignore[assignment]
        self.facade.catalog = SimpleNamespace()  # type: ignore[assignment]
        self.facade.inspectors = _Inspectors(snapshot)  # type: ignore[assignment]
        self.facade.session = ApfSession(
            self.source,  # type: ignore[arg-type]
            self.facade.catalog,  # type: ignore[arg-type]
            cache_root=self.root / "cache",
        )
        self.facade.session.asset_io = _ExportIO()  # type: ignore[assignment]
        self.count_patch = mock.patch(
            "mod_editor.apf_studio.facade.MAX_AUDIO_ANNOTATIONS", 1
        )
        self.count_patch.start()

    def tearDown(self) -> None:
        self.count_patch.stop()
        self.facade.close()
        self.temporary.cleanup()

    def test_live_validation_crud_and_overlay_preserve_identity(self) -> None:
        self.assertTrue(
            self.facade.set_audio_annotation(
                CUE_ID, "My menu return", "Use after frontend cancel"
            )
        )
        self.assertEqual(self.facade.annotation_count, 1)
        self.assertEqual(self.facade.project_metadata_count, 1)
        self.assertEqual(self.facade.modified_count, 0)
        annotation = self.facade.audio_annotation(CUE_ID)
        self.assertEqual(annotation.title, "My menu return")  # type: ignore[union-attr]
        overlaid = self.facade.audio_row_with_annotation(self.row)
        self.assertEqual(overlaid.row_id, self.row.row_id)
        self.assertEqual(
            overlaid.export_identity.coordinates,
            self.row.export_identity.coordinates,  # type: ignore[union-attr]
        )
        self.assertEqual(overlaid.title, "My menu return")
        self.assertEqual(overlaid.fields["game_catalog_title"], "menu_return")
        self.assertEqual(overlaid.fields["custom_title"], "My menu return")
        self.assertEqual(
            overlaid.fields["annotation_note"], "Use after frontend cancel"
        )
        self.assertIn("frontend cancel", overlaid._search_text)
        for invalid in (
            "apf:audio:ausb:137:8",
            "apf:audio:external:99",
            "apf:audio:audo:999:999",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(FacadeError):
                self.facade.set_audio_annotation(invalid, "Rejected")

    def test_bundle_and_batch_carry_metadata_but_keep_coordinate_paths(self) -> None:
        self.facade.set_audio_annotation(
            CUE_ID, "Custom cue title", "Long-form user research note"
        )
        bundle = self.facade.export_audio_bundle(
            (self.row,),
            self.root / "bundle.zip",
            bundle_name="Annotated sounds",
        )
        with zipfile.ZipFile(bundle) as archive:
            bundle_manifest = json.loads(archive.read("manifest.json"))
            bundle_playlist = archive.read("playlist.m3u8").decode()
        bundle_record = bundle_manifest["records"][0]
        self.assertEqual(bundle_record["row_id"], CUE_ID)
        self.assertEqual(bundle_record["title"], "Custom cue title")
        self.assertEqual(bundle_record["game_catalog_title"], "menu_return")
        self.assertEqual(bundle_record["custom_title"], "Custom cue title")
        self.assertEqual(
            bundle_record["annotation_note"], "Long-form user research note"
        )
        self.assertIn("Custom cue title", bundle_playlist)

        batch = self.facade.export_audio_batch(
            (self.row,),
            self.root / "batch.zip",
            batch_name="Annotated batch",
        )
        with zipfile.ZipFile(batch.path) as archive:
            batch_manifest = json.loads(archive.read("manifest.json"))
            batch_catalog = archive.read("catalog.csv").decode()
            batch_playlist = archive.read("playlist.m3u8").decode()
            names = archive.namelist()
        record = batch_manifest["records"][0]
        self.assertEqual(record["row_id"], CUE_ID)
        self.assertEqual(record["title"], "Custom cue title")
        self.assertEqual(record["metadata"]["game_catalog_title"], "menu_return")
        self.assertEqual(record["metadata"]["custom_title"], "Custom cue title")
        self.assertEqual(
            record["metadata"]["annotation_note"],
            "Long-form user research note",
        )
        canonical = "audio/audo/o00005-i00000.xma"
        self.assertEqual(record["output_path"], canonical)
        self.assertIn(canonical, names)
        catalog_rows = tuple(csv.DictReader(StringIO(batch_catalog)))
        self.assertEqual(catalog_rows[0]["game_catalog_title"], "menu_return")
        self.assertEqual(catalog_rows[0]["custom_title"], "Custom cue title")
        self.assertEqual(
            catalog_rows[0]["annotation_note"], "Long-form user research note"
        )
        self.assertIn("Custom cue title", batch_playlist)
        self.assertIn(canonical, batch_playlist)

    def test_project_load_rejects_syntactically_valid_nonexistent_cue(self) -> None:
        project = save_project(
            self.root / "foreign.apf2k8mod",
            source_sha256=SOURCE_SHA256,
            modifications=(),
            audio_annotations=(
                # Valid coordinate grammar, absent from the live source model.
                AudioCueAnnotation("apf:audio:audo:999:999", "Foreign cue"),
            ),
        )
        active = self.facade.session
        with self.assertRaisesRegex(ProjectError, "not present"):
            self.facade.load_project(project)
        self.assertIs(self.facade.session, active)

    def test_annotated_audio_rows_labeled_only_filters_unlabeled(self) -> None:
        rows = (self.row,)
        # Unlabeled: the default overlays nothing; labeled_only drops the row.
        self.assertEqual(self.facade.annotated_audio_rows(rows), (self.row,))
        self.assertEqual(
            self.facade.annotated_audio_rows(rows, labeled_only=True), ()
        )
        # Label the cue: labeled_only now keeps the overlaid row.
        self.assertTrue(
            self.facade.set_audio_annotation(CUE_ID, "Labeled cue", "research note")
        )
        labeled = self.facade.annotated_audio_rows(rows, labeled_only=True)
        self.assertEqual(len(labeled), 1)
        self.assertEqual(labeled[0].row_id, CUE_ID)
        self.assertEqual(labeled[0].title, "Labeled cue")
        self.assertEqual(labeled[0].fields["game_catalog_title"], "menu_return")
        # labeled_only must be a bool.
        with self.assertRaises(FacadeError):
            self.facade.annotated_audio_rows(rows, labeled_only="yes")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
