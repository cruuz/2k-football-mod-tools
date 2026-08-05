"""Focused coverage for the private, source-bound APF ratings CSV importer."""

from __future__ import annotations

import csv
from io import StringIO
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from mod_editor.apf_studio.backend import ensure_tools_importable
from mod_editor.apf_studio.inspectors import PagedModel, _row, export_player_rating_sheet
from mod_editor.apf_studio.player_rating_sheet import (
    PLAYER_RATING_SHEET_FIELDS,
    PlayerRatingSheetError,
    apply_player_rating_sheet,
    preview_player_rating_sheet,
)
from mod_editor.apf_studio.player_ratings import load_player_rating_schema
from mod_editor.apf_studio.session import ApfSession


ensure_tools_importable()
import apf_player_rating_patch as rating_writer  # type: ignore  # noqa: E402
import apf_roster  # type: ignore  # noqa: E402


SCHEMA = load_player_rating_schema()
SOURCE_SHA256 = "a" * 64


def _source_body() -> bytes:
    body = bytearray(apf_roster.EXPECTED_LENGTH)
    for player_index in range(rating_writer.EXPECTED_PLAYER_COUNT):
        start = apf_roster.ROOT_SIZE + player_index * apf_roster.PLAYER_STRIDE
        for item in SCHEMA.fields:
            body[start + item.relative_offset] = 50
    # The one byte that carries a native 100.  Looked up by id rather than by
    # position so a change to display order cannot silently move it.
    native_100 = next(
        item for item in SCHEMA.fields if item.field_id == "unknown_rating_d4"
    )
    body[apf_roster.ROOT_SIZE + native_100.relative_offset] = 100
    return bytes(body)


SOURCE_BODY = _source_body()


def _tables() -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            offset=apf_roster.ROOT_SIZE,
            count=rating_writer.EXPECTED_PLAYER_COUNT,
            stride=apf_roster.PLAYER_STRIDE,
        )
    ]


def _model() -> PagedModel:
    regular = {item.field_id: 50 for item in SCHEMA.fields}
    rows = []
    for player_index in range(rating_writer.EXPECTED_PLAYER_COUNT):
        values = dict(regular)
        if player_index == 0:
            values["unknown_rating_d4"] = 100
        rows.append(
            _row(
                f"apf:roster:player:{player_index}",
                "player",
                f"PLAYER {player_index}",
                f"#{player_index:04d} · QB",
                {
                    "player_index": player_index,
                    "first_name": "PLAYER",
                    "last_name": str(player_index),
                    "position_code": 0,
                    "position_abbreviation": "QB",
                    "position_name": "Quarterback",
                    "team_names": ("Americans",) if player_index < 42 else (),
                    "base_ratings": SCHEMA.field_rows(values),
                },
            )
        )
    return PagedModel(tuple(rows))


MODEL = _model()


def _rewrite_sheet(
    source: Path,
    destination: Path,
    mutate,
) -> None:
    rows = list(csv.DictReader(StringIO(source.read_text(encoding="utf-8"))))
    mutate(rows)
    with destination.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=PLAYER_RATING_SHEET_FIELDS, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


class PlayerRatingSheetImportTests(unittest.TestCase):
    def _session(self, root: Path) -> ApfSession:
        return ApfSession(
            SimpleNamespace(index_0a=root / "0A", source_sha256=SOURCE_SHA256),
            SimpleNamespace(),
            cache_root=root / "cache",
        )

    def _export(self, session: ApfSession, destination: Path) -> Path:
        return export_player_rating_sheet(
            MODEL,
            destination,
            source_sha256=SOURCE_SHA256,
            value_resolver=session.player_base_rating_value,
        )

    def test_one_change_previews_and_applies_as_one_undo_and_private_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session = self._session(root)
            try:
                with (
                    patch.object(apf_roster, "load_roster", return_value=(SOURCE_BODY, {})),
                    patch.object(apf_roster, "parse_root", return_value=(_tables(), {})),
                ):
                    exported = self._export(session, root / "source.csv")
                    edited = root / "edited.csv"
                    _rewrite_sheet(
                        exported,
                        edited,
                        lambda rows: rows[7].__setitem__("rating.speed", "99"),
                    )
                    preview = preview_player_rating_sheet(session, MODEL, edited)
                    self.assertEqual(preview.row_count, 2_254)
                    self.assertEqual(preview.cell_count, 2_254 * len(SCHEMA.fields))
                    self.assertEqual(preview.changed_count, 1)
                    self.assertEqual(preview.replacement_count, 1)
                    self.assertEqual(preview.revert_count, 0)
                    self.assertEqual(preview.unchanged_count, 2_254 * len(SCHEMA.fields) - 1)
                    self.assertEqual(preview.conflict_count, 0)
                    self.assertEqual(preview.error_count, 0)
                    self.assertTrue(preview.private_data)
                    receipt = apply_player_rating_sheet(session, MODEL, preview)
                    self.assertEqual(receipt.applied_count, 1)
                    self.assertEqual(receipt.undo_action_count, 1)
                    self.assertEqual(session.player_base_rating_value(7, "speed"), 99)
                    self.assertTrue(session.can_undo)

                    project = session.save_project(root / "ratings.apf2k8mod")
                    with zipfile.ZipFile(project) as archive:
                        manifest = json.loads(archive.read("project.json"))
                        self.assertEqual(manifest["replacement_count"], 1)
                        row = manifest["replacements"][0]
                        self.assertEqual(row["kind"], "player_base_rating")
                        self.assertNotIn("source_value", row["metadata"])
                        self.assertNotIn("source.csv", archive.namelist())
                        self.assertNotIn("edited.csv", archive.namelist())
                    self.assertTrue(session.undo())
                    self.assertFalse(session.can_undo)
                    self.assertEqual(session.player_base_rating_value(7, "speed"), 50)
            finally:
                session.close()

    def test_zero_change_is_a_true_no_op(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session = self._session(root)
            try:
                with (
                    patch.object(apf_roster, "load_roster", return_value=(SOURCE_BODY, {})),
                    patch.object(apf_roster, "parse_root", return_value=(_tables(), {})),
                ):
                    sheet = self._export(session, root / "source.csv")
                    preview = preview_player_rating_sheet(session, MODEL, sheet)
                    self.assertEqual(preview.changed_count, 0)
                    receipt = apply_player_rating_sheet(session, MODEL, preview)
                    self.assertEqual(receipt.applied_count, 0)
                    self.assertEqual(receipt.undo_action_count, 0)
                    self.assertFalse(session.can_undo)
            finally:
                session.close()

    def test_batch_prepares_every_cell_before_atomic_state_swap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session = self._session(root)
            try:
                with (
                    patch.object(apf_roster, "load_roster", return_value=(SOURCE_BODY, {})),
                    patch.object(apf_roster, "parse_root", return_value=(_tables(), {})),
                ):
                    with self.assertRaisesRegex(ValueError, "0 to 99"):
                        session.apply_player_base_rating_batch(
                            {(7, "speed"): 99, (8, "catch"): True}  # type: ignore[dict-item]
                        )
                    self.assertEqual(session.modified_count, 0)
                    self.assertFalse(session.can_undo)
            finally:
                session.close()

    def test_duplicate_missing_malformed_and_source_mismatch_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session = self._session(root)
            try:
                with (
                    patch.object(apf_roster, "load_roster", return_value=(SOURCE_BODY, {})),
                    patch.object(apf_roster, "parse_root", return_value=(_tables(), {})),
                ):
                    exported = self._export(session, root / "source.csv")
                    edited = root / "bad.csv"

                    def mutate(rows):
                        rows[-1]["player_index"] = "0"
                        rows[2]["rating.speed"] = "50.0"
                        rows[3]["rating.speed"] = "TRUE"
                        rows[4]["source_sha256"] = "b" * 64

                    _rewrite_sheet(exported, edited, mutate)
                    preview = preview_player_rating_sheet(session, MODEL, edited)
                    self.assertGreaterEqual(preview.error_count, 4)
                    self.assertEqual(preview.source_conflict_count, 1)
                    messages = "\n".join(item.message for item in preview.errors)
                    self.assertIn("listed more than once", messages)
                    self.assertIn("missing", messages)
                    self.assertIn("plain whole number", messages)
                    with self.assertRaises(PlayerRatingSheetError):
                        apply_player_rating_sheet(session, MODEL, preview)
                    self.assertEqual(session.modified_count, 0)
                    self.assertFalse(session.can_undo)
            finally:
                session.close()

    def test_native_100_is_only_unchanged_or_revert_to_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session = self._session(root)
            try:
                with (
                    patch.object(apf_roster, "load_roster", return_value=(SOURCE_BODY, {})),
                    patch.object(apf_roster, "parse_root", return_value=(_tables(), {})),
                ):
                    source_sheet = self._export(session, root / "source.csv")
                    invalid = root / "invalid100.csv"
                    _rewrite_sheet(
                        source_sheet,
                        invalid,
                        lambda rows: rows[1].__setitem__("rating.speed", "100"),
                    )
                    bad = preview_player_rating_sheet(session, MODEL, invalid)
                    self.assertEqual(bad.error_count, 1)
                    self.assertIn("source 100", bad.errors[0].message)

                    session.replace_player_base_rating(0, "unknown_rating_d4", 99)
                    active_sheet = self._export(session, root / "active.csv")
                    revert_sheet = root / "revert.csv"
                    _rewrite_sheet(
                        active_sheet,
                        revert_sheet,
                        lambda rows: rows[0].__setitem__(
                            "rating.unknown_rating_d4", "100"
                        ),
                    )
                    preview = preview_player_rating_sheet(session, MODEL, revert_sheet)
                    self.assertEqual(preview.revert_count, 1)
                    self.assertEqual(preview.project_conflict_count, 1)
                    with self.assertRaisesRegex(PlayerRatingSheetError, "Confirm"):
                        apply_player_rating_sheet(session, MODEL, preview)
                    applied = apply_player_rating_sheet(
                        session, MODEL, preview, allow_conflicts=True
                    )
                    self.assertEqual(applied.applied_count, 1)
                    self.assertEqual(
                        session.player_base_rating_value(0, "unknown_rating_d4"), 100
                    )
                    self.assertIsNone(
                        session.modification(
                            "apf:player-rating:0:unknown_rating_d4"
                        )
                    )
            finally:
                session.close()

    def test_active_project_conflict_needs_confirmation_and_undo_restores_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session = self._session(root)
            try:
                with (
                    patch.object(apf_roster, "load_roster", return_value=(SOURCE_BODY, {})),
                    patch.object(apf_roster, "parse_root", return_value=(_tables(), {})),
                ):
                    session.replace_player_base_rating(7, "speed", 88)
                    active = self._export(session, root / "active.csv")
                    edited = root / "edited.csv"
                    _rewrite_sheet(
                        active,
                        edited,
                        lambda rows: rows[7].__setitem__("rating.speed", "77"),
                    )
                    preview = preview_player_rating_sheet(session, MODEL, edited)
                    self.assertEqual(preview.project_conflict_count, 1)
                    self.assertEqual(preview.conflicts[0].current_value, 88)
                    self.assertEqual(preview.conflicts[0].desired_value, 77)
                    with self.assertRaisesRegex(PlayerRatingSheetError, "conflicts"):
                        apply_player_rating_sheet(session, MODEL, preview)
                    receipt = apply_player_rating_sheet(
                        session, MODEL, preview, allow_conflicts=True
                    )
                    self.assertEqual(receipt.applied_count, 1)
                    self.assertEqual(session.player_base_rating_value(7, "speed"), 77)
                    self.assertTrue(session.undo())
                    self.assertEqual(session.player_base_rating_value(7, "speed"), 88)
            finally:
                session.close()

    def test_file_or_project_change_after_preview_is_rejected_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session = self._session(root)
            try:
                with (
                    patch.object(apf_roster, "load_roster", return_value=(SOURCE_BODY, {})),
                    patch.object(apf_roster, "parse_root", return_value=(_tables(), {})),
                ):
                    exported = self._export(session, root / "source.csv")
                    edited = root / "edited.csv"
                    _rewrite_sheet(
                        exported,
                        edited,
                        lambda rows: rows[7].__setitem__("rating.speed", "99"),
                    )
                    preview = preview_player_rating_sheet(session, MODEL, edited)
                    data = edited.read_text(encoding="utf-8")
                    edited.write_text(data.replace(",99,", ",98,", 1), encoding="utf-8")
                    with self.assertRaisesRegex(PlayerRatingSheetError, "changed after preview"):
                        apply_player_rating_sheet(session, MODEL, preview)
                    self.assertEqual(session.modified_count, 0)
                    self.assertFalse(session.can_undo)

                    # A concurrently changed active project also invalidates the
                    # immutable plan without rolling back that newer edit.
                    edited.write_text(data, encoding="utf-8")
                    project_preview = preview_player_rating_sheet(session, MODEL, edited)
                    session.replace_player_base_rating(8, "catch", 77)
                    with self.assertRaisesRegex(
                        PlayerRatingSheetError, "active rating edits changed"
                    ):
                        apply_player_rating_sheet(session, MODEL, project_preview)
                    self.assertEqual(session.modified_count, 1)
                    self.assertEqual(session.player_base_rating_value(8, "catch"), 77)
                    self.assertTrue(session.undo())
                    self.assertEqual(session.modified_count, 0)
            finally:
                session.close()


if __name__ == "__main__":
    unittest.main()
