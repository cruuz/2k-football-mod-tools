from __future__ import annotations

from dataclasses import replace
import csv
import hashlib
from io import StringIO
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from mod_editor.apf_studio.models import ApfSource
from mod_editor.apf_studio.gui import _load_text_inspector
from mod_editor.apf_studio.inspectors import LocalizationSnapshot, PagedModel, _row
from mod_editor.apf_studio.project import (
    decode_text_payload,
    load_project,
)
from mod_editor.apf_studio.session import ApfSession, SessionError
from mod_editor.apf_studio.text_sheet import (
    TEXT_SHEET_FIELDS,
    TextSheetError,
    export_text_sheet,
    import_text_sheet,
)

import apf_txt_loc_patch as writer


def _source(root: Path) -> ApfSource:
    root.mkdir(parents=True, exist_ok=True)
    index = root / "0A"
    index.write_bytes(b"unused-test-source")
    return ApfSource(
        selected_path=root,
        game_root=root,
        index_0a=index,
        source_sha256="d" * 64,
        source_size=index.stat().st_size,
        xex_sha256="e" * 64,
        display_name="Test APF",
    )


def _allocations() -> tuple[writer.TextAllocation, ...]:
    return (
        writer.TextAllocation(
            asset_id="apf:text-pool:1127:0:10",
            outer_index=1127,
            inner_index=0,
            table_name="English",
            pool_index=10,
            text="HOME",
            allocation_bytes=10,
            maximum_utf16_units=4,
            reference_count=6,
            editable=True,
            note="Shared by 6 localization records.",
        ),
        writer.TextAllocation(
            asset_id="apf:text-pool:526:0:1",
            outer_index=526,
            inner_index=0,
            table_name="credits_English",
            pool_index=1,
            text="Quinn Kaneko",
            allocation_bytes=26,
            maximum_utf16_units=12,
            reference_count=1,
            editable=True,
            note="One fixed UTF-16BE pool allocation.",
        ),
        writer.TextAllocation(
            asset_id="apf:text-pool:810:87:0",
            outer_index=810,
            inner_index=87,
            table_name="strings",
            pool_index=0,
            text="SOURCE",
            allocation_bytes=14,
            maximum_utf16_units=6,
            reference_count=2,
            editable=True,
            note="Shared by 2 STRG records.",
        ),
    )


class ApfTextSessionProjectTests(unittest.TestCase):
    @staticmethod
    def _edited_sheet(source: Path, destination: Path, edits: dict[str, dict[str, str]]) -> None:
        rows = list(csv.DictReader(StringIO(source.read_text(encoding="utf-8"))))
        for row in rows:
            row.update(edits.get(row["asset_id"], {}))
        with destination.open("w", encoding="utf-8", newline="") as stream:
            writer_csv = csv.DictWriter(
                stream, fieldnames=TEXT_SHEET_FIELDS, lineterminator="\n"
            )
            writer_csv.writeheader()
            writer_csv.writerows(rows)

    def test_private_text_sheet_import_is_atomic_and_one_undo_action(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session = ApfSession(
                _source(root / "game"),
                SimpleNamespace(),
                cache_root=root / "cache",
            )
            try:
                with patch.object(writer, "inventory", return_value=_allocations()):
                    exported = export_text_sheet(session, root / "private-text.csv")
                    self.assertEqual(exported.allocation_count, 3)
                    self.assertEqual(exported.editable_count, 3)
                    self.assertEqual(exported.active_replacement_count, 0)
                    rows = list(
                        csv.DictReader(
                            StringIO(exported.destination.read_text(encoding="utf-8"))
                        )
                    )
                    self.assertEqual(tuple(rows[0]), TEXT_SHEET_FIELDS)
                    self.assertTrue(all(row["original_text"].startswith("'") for row in rows))
                    self.assertTrue(all(row["replacement_text"].startswith("'") for row in rows))

                    edited = root / "edited.csv"
                    self._edited_sheet(
                        exported.destination,
                        edited,
                        {
                            "apf:text-pool:1127:0:10": {
                                "replacement_text": "'MOD",
                            },
                            "apf:text-pool:526:0:1": {
                                "action": "replace",
                                "replacement_text": "'MOD CREDITS",
                            },
                        },
                    )
                    receipt = import_text_sheet(session, edited)
                self.assertEqual(receipt.row_count, 3)
                self.assertEqual(receipt.replacement_count, 2)
                self.assertEqual(receipt.revert_count, 0)
                self.assertEqual(receipt.changed_count, 2)
                self.assertEqual(session.modified_count, 2)
                self.assertEqual(
                    session.localization_text_value("apf:text-pool:1127:0:10"),
                    "MOD",
                )
                self.assertTrue(session.undo())
                self.assertEqual(session.modified_count, 0)
                self.assertFalse(session.can_undo)
            finally:
                session.close()

    def test_text_sheet_rejects_late_invalid_row_without_staging_early_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session = ApfSession(
                _source(root / "game"),
                SimpleNamespace(),
                cache_root=root / "cache",
            )
            try:
                with patch.object(writer, "inventory", return_value=_allocations()):
                    exported = export_text_sheet(session, root / "private-text.csv")
                    edited = root / "invalid.csv"
                    self._edited_sheet(
                        exported.destination,
                        edited,
                        {
                            "apf:text-pool:1127:0:10": {
                                "replacement_text": "'MOD",
                            },
                            "apf:text-pool:526:0:1": {
                                "replacement_text": "'THIS VALUE IS MUCH TOO LONG",
                            },
                        },
                    )
                    with self.assertRaisesRegex(TextSheetError, "leading apostrophe"):
                        formula_sheet = root / "formula.csv"
                        self._edited_sheet(
                            exported.destination,
                            formula_sheet,
                            {
                                "apf:text-pool:1127:0:10": {
                                    "replacement_text": "=HYPERLINK(\"bad\")",
                                }
                            },
                        )
                        import_text_sheet(session, formula_sheet)
                    with self.assertRaisesRegex(SessionError, "at most 12"):
                        import_text_sheet(session, edited)
                self.assertEqual(session.modified_count, 0)
                self.assertFalse(session.can_undo)
            finally:
                session.close()

    def test_text_sheet_can_replace_and_revert_together_then_undo_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session = ApfSession(
                _source(root / "game"),
                SimpleNamespace(),
                cache_root=root / "cache",
            )
            try:
                with patch.object(writer, "inventory", return_value=_allocations()):
                    session.apply_localization_text_batch(
                        {
                            "apf:text-pool:1127:0:10": "OLD",
                            "apf:text-pool:526:0:1": "OLD CREDITS",
                        }
                    )
                    exported = export_text_sheet(session, root / "active.csv")
                    edited = root / "mixed.csv"
                    self._edited_sheet(
                        exported.destination,
                        edited,
                        {
                            "apf:text-pool:1127:0:10": {"action": "revert"},
                            "apf:text-pool:526:0:1": {
                                "action": "replace",
                                "replacement_text": "'NEW CREDITS",
                            },
                        },
                    )
                    receipt = import_text_sheet(session, edited)
                self.assertEqual(receipt.replacement_count, 1)
                self.assertEqual(receipt.revert_count, 1)
                self.assertEqual(session.modified_count, 1)
                self.assertTrue(session.undo())
                self.assertEqual(session.modified_count, 2)
                self.assertEqual(
                    session.localization_text_value("apf:text-pool:1127:0:10"),
                    "OLD",
                )
                self.assertEqual(
                    session.localization_text_value("apf:text-pool:526:0:1"),
                    "OLD CREDITS",
                )
            finally:
                session.close()

    def test_text_inspector_merges_every_txt_and_strg_allocation_once(self) -> None:
        allocations = (
            *_allocations(),
            writer.TextAllocation(
                asset_id="apf:text-pool:185:20:99",
                outer_index=185,
                inner_index=20,
                table_name="artist_bio_english",
                pool_index=99,
                text="",
                allocation_bytes=2,
                maximum_utf16_units=0,
                reference_count=0,
                editable=False,
                note="Zero-capacity empty STRG allocation; kept read-only.",
            ),
        )
        old_txt_pool_rows = PagedModel(
            (
                _row(
                    "apf:text-pool:1127:0:10",
                    "localization_pool_string",
                    "stale duplicate",
                    "English pool 10",
                    {"pool_index": 10},
                ),
                _row(
                    "apf:text-pool:526:0:1",
                    "localization_pool_string",
                    "stale duplicate",
                    "credits_English pool 1",
                    {"pool_index": 1},
                ),
            )
        )
        references = PagedModel(
            (
                _row(
                    "apf:text:1127:0:77",
                    "localization_record",
                    "HOME",
                    "English · 0x12345678",
                    {"pool_index": 10, "text_id": "0x12345678"},
                ),
            )
        )
        snapshot = LocalizationSnapshot(
            summary={"records": 1},
            records=references,
            pool=old_txt_pool_rows,
        )
        service = SimpleNamespace(localization=lambda: snapshot)

        summary, model = _load_text_inspector(service, allocations)

        self.assertEqual(len(model.rows), 5)
        self.assertEqual(len({row.row_id for row in model.rows}), 5)
        self.assertEqual(model.rows[-1].kind, "localization_record")
        self.assertEqual(
            model.get("apf:text-pool:1127:0:10").title,
            "HOME",
        )
        self.assertEqual(
            model.get("apf:text-pool:1127:0:10").fields["bank_type"],
            "TXT loc system",
        )
        self.assertEqual(
            model.get("apf:text-pool:810:87:0").fields["bank_type"],
            "STRG",
        )
        self.assertEqual(model.kind_counts["string_bank_pool_string"], 2)
        self.assertEqual(model.page(search="artist_bio_english").total, 1)
        self.assertIn("Pool Allocations: 4", summary)
        self.assertIn("Editable Allocations: 3", summary)
        self.assertIn("Read Only Allocations: 1", summary)

    def test_strg_pool_zero_is_a_retail_free_project_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session = ApfSession(
                _source(root / "game"),
                SimpleNamespace(),
                cache_root=root / "cache",
            )
            try:
                with patch.object(writer, "inventory", return_value=_allocations()):
                    modification = session.replace_localization_text(
                        "apf:text-pool:810:87:0", "MOD"
                    )
                project = session.save_project(root / "strg.apf2k8mod")
                manifest, loaded, _annotations = load_project(
                    project,
                    expected_source_sha256="d" * 64,
                    destination_dir=root / "loaded",
                )
                self.assertEqual(manifest["replacement_count"], 1)
                self.assertEqual(len(loaded), 1)
                self.assertEqual(loaded[0].asset_id, modification.asset_id)
                self.assertEqual(
                    decode_text_payload(
                        loaded[0].replacement_path.read_bytes(),
                        loaded[0].asset_id,
                    ),
                    "MOD",
                )
            finally:
                session.close()

    def test_individual_replace_revert_and_retail_free_project_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session = ApfSession(
                _source(root / "game"),
                SimpleNamespace(),
                cache_root=root / "cache",
            )
            try:
                with patch.object(writer, "inventory", return_value=_allocations()):
                    first = session.replace_localization_text(
                        "apf:text-pool:1127:0:10", "MOD"
                    )
                    second = session.replace_localization_text(
                        "apf:text-pool:526:0:1", "MOD CREDITS"
                    )
                self.assertEqual(first.kind, "localization_text")
                self.assertEqual(first.replacement_path.suffix, ".json")
                self.assertEqual(
                    decode_text_payload(first.replacement_path.read_bytes(), first.asset_id),
                    "MOD",
                )
                self.assertEqual(session.modified_count, 2)
                self.assertTrue(session.revert(first.asset_id))
                self.assertEqual(session.modified_asset_ids, {second.asset_id})
                self.assertTrue(session.undo())
                self.assertEqual(session.modified_count, 2)

                project = session.save_project(root / "text.apf2k8mod")
                with zipfile.ZipFile(project) as archive:
                    manifest = json.loads(archive.read("project.json"))
                    self.assertEqual(manifest["replacement_count"], 2)
                    self.assertNotIn("MOD CREDITS", archive.read("project.json").decode())
                    payload_names = {
                        row["payload"] for row in manifest["replacements"]
                    }
                    self.assertTrue(all(name.endswith(".json") for name in payload_names))
                    self.assertEqual(set(archive.namelist()), {"project.json", *payload_names})
                    self.assertFalse(
                        manifest["distribution"]["contains_original_game_bytes"]
                    )

                _manifest, loaded, _annotations = load_project(
                    project,
                    expected_source_sha256="d" * 64,
                    destination_dir=root / "loaded",
                )
                self.assertEqual(len(loaded), 2)
                self.assertTrue(all(item.replacement_path.suffix == ".json" for item in loaded))

                imported = ApfSession(
                    _source(root / "other-game"),
                    SimpleNamespace(),
                    cache_root=root / "import-cache",
                )
                try:
                    with patch.object(writer, "inventory", return_value=_allocations()):
                        self.assertEqual(imported.load_project(project), 2)
                    self.assertEqual(
                        imported.localization_text_value(first.asset_id), "MOD"
                    )
                    self.assertEqual(
                        imported.localization_text_value(second.asset_id), "MOD CREDITS"
                    )
                finally:
                    imported.close()
            finally:
                session.close()

    def test_limit_nul_and_live_allocation_metadata_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session = ApfSession(
                _source(root / "game"),
                SimpleNamespace(),
                cache_root=root / "cache",
            )
            try:
                with patch.object(writer, "inventory", return_value=_allocations()):
                    with self.assertRaisesRegex(SessionError, "at most 4"):
                        session.replace_localization_text(
                            "apf:text-pool:1127:0:10", "TOO LONG"
                        )
                    with self.assertRaisesRegex(SessionError, "NUL"):
                        session.replace_localization_text(
                            "apf:text-pool:1127:0:10", "A\0B"
                        )
            finally:
                session.close()


if __name__ == "__main__":
    unittest.main()
