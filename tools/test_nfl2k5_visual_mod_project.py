#!/usr/bin/env python3
"""Focused tests for the unified NFL 2K5 visual-mod project/orchestrator."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parent))
import nfl2k5_visual_mod_project as project


class VisualModProjectTests(unittest.TestCase):
    def write_project(self, root: Path, value: dict[str, object],
                      canonical: bool = True) -> Path:
        path = root / "project.json"
        payload = (project.canonical_json(value) if canonical else
                   json.dumps(value).encode("utf-8"))
        path.write_bytes(payload)
        return path

    def complete_value(self, png: str = "input.png") -> dict[str, object]:
        return {
            "schema": project.SCHEMA,
            "purpose": "unit-test schema coverage",
            "edits": [
                {"kind": "torso", "asset_code": "09", "side": "A",
                 "variant": 0, "clean_png": png, "mud_png": None,
                 "mud_mode": "darken_60"},
                {"kind": "sleeve", "asset_code": "09", "side": "A",
                 "variant": 0, "clean_png": png, "mud_png": None,
                 "mud_mode": "identity"},
                {"kind": "pants", "asset_code": "09", "side": "A",
                 "variant": 0, "clean_png": png, "mud_png": None,
                 "mud_mode": "identity"},
                {"kind": "live_helmet", "asset_code": "09", "side": "A",
                 "variant": 0, "family": "helmet00", "png": png},
                {"kind": "live_number_nameplate", "asset_code": "09",
                 "side": "A", "variant": 0, "family": "nameplate",
                 "digit": None, "png": png},
                {"kind": "team_select", "asset_code": "09", "side": "away",
                 "style": 0, "family": "helm", "resolution": 256, "png": png},
                {"kind": "live_face", "face_id": "0124", "family": "f",
                 "png": png},
                {"kind": "create_team_field_art", "logo_code": 67,
                 "weather": "D", "texture": "endzone_north_middle", "png": png},
                {"kind": "team_identity", "team_index": 18,
                 "city": "Codexia", "nickname": "Codex",
                 "abbreviation": "CDX", "city_abbreviation": "CDX"},
                {"kind": "player_roster", "primary_player_index": 512,
                 "first_name": "Noah", "last_name": "CodexProof",
                 "jersey_number": 42},
                {"kind": "player_portrait", "portrait_id": "4070", "png": png},
                {"kind": "crib_team_photo",
                 "selector": "crib_team_photo:00_photo_00", "png": png},
                {"kind": "crib_scene_texture",
                 "selector": "crib_scene_texture:room:22", "png": png},
                {"kind": "scorebug_texture", "target": "score_buga",
                 "png": png},
                {"kind": "stadium_texture",
                 "target": project.STADIUM_TEXTURE_TARGET, "png": png},
                {"kind": "universal_fixed_text",
                 "selector": "situ:moment:0:title", "text": "MOD"},
            ],
        }

    def test_all_edit_shapes_and_relative_png_pin(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "input.png").write_bytes(b"bounded fixture bytes")
            path = self.write_project(root, self.complete_value())
            result = project.validate_only(path)
            self.assertEqual(result["edit_count"], 16)
            self.assertEqual(result["unique_png_count"], 1)
            self.assertEqual(set(result["kind_counts"]), {
                "torso", "sleeve", "pants", "live_helmet",
                "live_number_nameplate", "team_select",
                "live_face", "create_team_field_art",
                "team_identity", "player_roster", "player_portrait",
                "crib_team_photo", "crib_scene_texture", "scorebug_texture",
                "stadium_texture", "universal_fixed_text",
            })
            self.assertFalse(result["target_compatibility_validated"])

    def test_noncanonical_project_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "input.png").write_bytes(b"fixture")
            path = self.write_project(root, self.complete_value(), canonical=False)
            with self.assertRaisesRegex(project.ProjectError, "canonical"):
                project.read_project(path)

    def test_symlink_png_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "real.png").write_bytes(b"fixture")
            (root / "input.png").symlink_to("real.png")
            path = self.write_project(root, self.complete_value())
            parsed = project.read_project(path)
            with self.assertRaisesRegex(project.ProjectError, "non-symlink"):
                project.pin_project_inputs(parsed)

    def test_bool_is_not_accepted_as_integer(self) -> None:
        value = self.complete_value()
        value["edits"][0]["variant"] = True  # type: ignore[index]
        with self.assertRaises(project.ProjectError):
            project.validate_edit_shape(value["edits"][0], 0)  # type: ignore[index]

    def test_unknown_edit_field_is_refused(self) -> None:
        value = self.complete_value()
        value["edits"][0]["surprise"] = 1  # type: ignore[index]
        with self.assertRaises(project.ProjectError):
            project.validate_edit_shape(value["edits"][0], 0)  # type: ignore[index]

    def test_live_face_shape_family_is_explicitly_read_only(self) -> None:
        value = {"kind": "live_face", "face_id": "0124", "family": "s",
                 "png": "face.png"}
        with self.assertRaisesRegex(project.ProjectError, "only f/h/n"):
            project.validate_edit_shape(value, 0)

    def test_field_art_bool_logo_and_unknown_texture_are_refused(self) -> None:
        base = {"kind": "create_team_field_art", "logo_code": True,
                "weather": "D", "texture": "endzone_north_middle",
                "png": "field.png"}
        with self.assertRaises(project.ProjectError):
            project.validate_edit_shape(base, 0)
        base["logo_code"] = 67
        base["texture"] = "scoreboard"
        with self.assertRaises(project.ProjectError):
            project.validate_edit_shape(base, 0)

    def test_crib_scene_texture_shape_is_exact_and_logical(self) -> None:
        valid = {
            "kind": "crib_scene_texture",
            "selector": "crib_scene_texture:room:22",
            "png": "screen.png",
        }
        self.assertEqual(project.validate_edit_shape(valid, 0), valid)
        for row in (
            {**valid, "selector": "crib_scene_texture:room:999"},
            {**valid, "offset": 123},
            {**valid, "png": ""},
        ):
            with self.subTest(row=row), self.assertRaisesRegex(
                project.ProjectError, "25 proved Crib electronics surfaces"
            ):
                project.validate_edit_shape(row, 0)

    def test_crib_scene_compression_errors_are_translated_for_modders(self) -> None:
        cases = (
            (
                "This PNG is too visually complex for the room SCNE's fixed "
                "compressed allocation. Encoder detail: internal noise.",
                "too much fine noise or dithering",
            ),
            (
                "This PNG compresses outside the conservative room-SCNE loader "
                "envelope (4000 scratch bytes required).",
                "too flat for the safe game slot",
            ),
        )
        for detail, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as raw:
                png = Path(raw) / "screen.png"
                png.write_bytes(b"user png")
                with (
                    mock.patch.object(
                        project.common,
                        "parse_xdvdfs",
                        return_value=({
                            f"vc_53450030/{project.CRIB_SCENE_PACK_NAME}".casefold():
                                mock.Mock(byte_offset=0),
                        }, {}),
                    ),
                    mock.patch.object(project.common, "read_exact", return_value=b"source"),
                    mock.patch.object(
                        project.crib_scene_import,
                        "read_png",
                        return_value=(png, b"user png", b"rgba"),
                    ),
                    mock.patch.object(
                        project.crib_scene_import,
                        "compile_replacement",
                        side_effect=project.crib_scene_import.BarMonitorError(detail),
                    ),
                ):
                    with self.assertRaisesRegex(project.ProjectError, expected):
                        project.build_crib_scene_texture_import(
                            1, png, {"preview_file": "preview.png"}
                        )

    def test_duplicate_crib_scene_selector_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "input.png").write_bytes(b"fixture")
            value = self.complete_value()
            value["edits"].append({  # type: ignore[union-attr]
                "kind": "crib_scene_texture",
                "selector": "crib_scene_texture:room:22",
                "png": "input.png",
            })
            path = self.write_project(root, value)
            with self.assertRaisesRegex(
                project.ProjectError, "repeats one crib_scene_texture"
            ):
                project.read_project(path)
    def test_universal_fixed_text_shape_is_logical_only_and_strict(self) -> None:
        valid = {
            "kind": "universal_fixed_text",
            "selector": "triv:question:12:answer_c",
            "text": "User-authored answer",
        }
        self.assertEqual(project.validate_edit_shape(valid, 0), valid)
        invalid = (
            {**valid, "selector": "situ:moment:0:away_team_asset_code"},
            {**valid, "selector": "situ:moment:0:title", "offset": 123},
            {**valid, "text": ""},
            {**valid, "text": "A\0B"},
        )
        for row in invalid:
            with self.subTest(row=row), self.assertRaises(project.ProjectError):
                project.validate_edit_shape(row, 0)

    def test_duplicate_universal_fixed_text_selector_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "input.png").write_bytes(b"fixture")
            value = self.complete_value()
            value["edits"].append({  # type: ignore[union-attr]
                "kind": "universal_fixed_text",
                "selector": "situ:moment:0:title",
                "text": "SECOND",
            })
            path = self.write_project(root, value)
            with self.assertRaisesRegex(
                project.ProjectError, "repeats one universal_fixed_text"
            ):
                project.read_project(path)

    def test_private_safe_text_selector_resolves_without_public_offsets(self) -> None:
        source_sha = (
            "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
        )
        cache = Path.home() / ".cache" / "2k5-mod-studio" / source_sha
        pack0 = cache / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
        inventory = cache / "indexes/nfl2k5_resource_chunks_v2.json"
        source = Path(
            "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"
        )
        if not pack0.is_file() or not inventory.is_file() or not source.is_file():
            self.skipTest("recognized private NFL 2K5 source/cache is absent")

        catalog = project.safe_text_adapter.SafeTextCatalog.from_paths(
            pack0, inventory
        )
        logical = {
            "kind": "universal_fixed_text",
            "selector": "situ:moment:0:title",
            "text": "MOD",
        }
        replacement = catalog.resolve_edits((logical,))[0]
        source_fd = os.open(source, os.O_RDONLY)
        try:
            entries, _directory = project.common.parse_xdvdfs(
                source_fd, source.stat().st_size
            )
        finally:
            os.close(source_fd)
        built = project.build_universal_fixed_text_import(
            logical, catalog, replacement, entries, {}
        )
        payload, previews, report, selector, target = built
        self.assertEqual(selector, logical["selector"])
        self.assertEqual(previews, [])
        self.assertEqual(len(payload), target["allocation_bytes"])
        self.assertTrue(payload.startswith(b"M\0O\0D\0\0\0"))
        self.assertEqual(report["claims"]["public_project_contains_raw_offsets"], False)
        self.assertNotIn(catalog.get_selector(selector).value, json.dumps(report))
        self.assertEqual(set(logical), {"kind", "selector", "text"})

    def team_identity_edit(self) -> dict[str, object]:
        return {"kind": "team_identity", "team_index": 18,
                "city": "Codexia", "nickname": "Codex",
                "abbreviation": "CDX", "city_abbreviation": "CDX"}

    def test_team_identity_expands_to_four_fixed_spans(self) -> None:
        results = project.build_team_identity_imports(
            self.team_identity_edit(), project.REPORTS["team_identity"])
        self.assertEqual(len(results), 4)
        self.assertEqual({item[3] for item in results}, {
            "team:18:nickname", "team:18:abbreviation",
            "team:18:city", "team:18:city_abbreviation",
        })
        self.assertEqual(sum(len(item[0]) for item in results), 44)
        self.assertTrue(all(item[4]["asset_code"] == "09" for item in results))

    def test_team_identity_overlength_is_refused(self) -> None:
        edit = self.team_identity_edit()
        edit["city"] = "FarTooLongForDetroit"
        with self.assertRaisesRegex(project.ProjectError, "allocation"):
            project.build_team_identity_imports(
                edit, project.REPORTS["team_identity"])

    def test_duplicate_team_identity_team_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "input.png").write_bytes(b"fixture")
            value = self.complete_value()
            value["edits"].append(dict(self.team_identity_edit()))  # type: ignore[union-attr]
            path = self.write_project(root, value)
            with self.assertRaisesRegex(project.ProjectError, "repeats one team_identity"):
                project.read_project(path)

    def test_forged_team_identity_report_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value = json.loads(project.REPORTS["team_identity"].read_bytes())
            value["summary"]["main_team_count"] = 51
            forged = root / "forged.json"
            forged.write_bytes(project.canonical_json(value))
            original = project.REPORTS["team_identity"]
            project.REPORTS["team_identity"] = forged
            try:
                with self.assertRaisesRegex(project.ProjectError, "SHA-256"):
                    project.pin_reports({"team_identity"})
            finally:
                project.REPORTS["team_identity"] = original

    def test_symlink_team_identity_report_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            link = root / "audit-link.json"
            link.symlink_to(project.REPORTS["team_identity"])
            original = project.REPORTS["team_identity"]
            project.REPORTS["team_identity"] = link
            try:
                with self.assertRaisesRegex(project.ProjectError, "non-symlink"):
                    project.pin_reports({"team_identity"})
            finally:
                project.REPORTS["team_identity"] = original

    def player_roster_edit(self) -> dict[str, object]:
        return {"kind": "player_roster", "primary_player_index": 512,
                "first_name": "Noah", "last_name": "CodexProof",
                "jersey_number": 42}

    def test_player_roster_expands_to_three_fixed_spans(self) -> None:
        results = project.build_player_roster_imports(
            self.player_roster_edit(), project.REPORTS["player_roster"])
        self.assertEqual(len(results), 3)
        self.assertEqual({item[3] for item in results}, {
            "primary-player:512:first_name",
            "primary-player:512:last_name",
            "primary-player:512:jersey_number",
        })
        self.assertEqual(sum(len(item[0]) for item in results), 36)
        self.assertEqual(results[-1][4]["replacement_jersey_word"], "0x00080950")

    def test_player_roster_overlength_is_refused(self) -> None:
        edit = self.player_roster_edit()
        edit["first_name"] = "FarTooLong"
        with self.assertRaisesRegex(project.ProjectError, "allocation"):
            project.build_player_roster_imports(
                edit, project.REPORTS["player_roster"])

    def test_duplicate_player_roster_selector_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "input.png").write_bytes(b"fixture")
            value = self.complete_value()
            value["edits"].append(dict(self.player_roster_edit()))  # type: ignore[union-attr]
            path = self.write_project(root, value)
            with self.assertRaisesRegex(project.ProjectError, "repeats one player_roster"):
                project.read_project(path)

    def test_duplicate_player_portrait_selector_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "input.png").write_bytes(b"fixture")
            value = self.complete_value()
            value["edits"].append(  # type: ignore[union-attr]
                {"kind": "player_portrait", "portrait_id": "4070",
                 "png": "input.png"})
            path = self.write_project(root, value)
            with self.assertRaisesRegex(project.ProjectError, "repeats one player_portrait"):
                project.read_project(path)

    def test_crib_team_photo_shape_and_duplicate_selector_are_bounded(self) -> None:
        valid = {
            "kind": "crib_team_photo",
            "selector": "crib_team_photo:31_photo_03",
            "png": "photo.png",
        }
        self.assertEqual(project.validate_edit_shape(valid, 0), valid)
        for selector in (
            "crib_team_photo:32_photo_00",
            "crib_team_photo:00_photo_04",
            "crib_team_photo:0_photo_00",
            "crib_team_photo:00_photo_0x",
        ):
            with self.subTest(selector=selector), self.assertRaises(
                project.ProjectError
            ):
                project.validate_edit_shape({**valid, "selector": selector}, 0)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "input.png").write_bytes(b"fixture")
            value = self.complete_value()
            value["edits"].append(  # type: ignore[union-attr]
                {"kind": "crib_team_photo",
                 "selector": "crib_team_photo:00_photo_00",
                 "png": "input.png"}
            )
            path = self.write_project(root, value)
            with self.assertRaisesRegex(
                project.ProjectError, "repeats one crib_team_photo"
            ):
                project.read_project(path)

    def test_crib_team_photo_compact_catalog_target_is_exact(self) -> None:
        _catalog, payload, target = project.crib_photo_targets.select_target(
            "crib_team_photo:00_photo_00",
            project.REPORTS["crib_team_photo"],
        )
        self.assertLess(len(payload), 8 * 1024 * 1024)
        self.assertEqual(target.span_size, 23_008)
        self.assertEqual(target.slot_size, 23_040)
        self.assertEqual(target.mip_dimensions, (128, 64, 32, 16, 8))
        self.assertEqual(target.mip_index_bytes,
                         (16_384, 4_096, 1_024, 256, 64))
        self.assertEqual(target.xiso_pack_path, "vc_53450030/C")
        self.assertEqual(
            target.xiso_absolute_span_offset,
            target.xiso_pack_sector * 2_048 + target.pack_offset,
        )

    def test_scorebug_texture_shape_and_duplicate_target_are_bounded(self) -> None:
        valid = {
            "kind": "scorebug_texture",
            "target": "score_buga",
            "png": "scorebug.png",
        }
        self.assertEqual(project.validate_edit_shape(valid, 0), valid)
        for target in ("scorebug", "field", "digital-font", ""):
            with self.subTest(target=target), self.assertRaises(
                project.ProjectError
            ):
                project.validate_edit_shape({**valid, "target": target}, 0)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "input.png").write_bytes(b"fixture")
            value = self.complete_value()
            value["edits"].append(  # type: ignore[union-attr]
                {"kind": "scorebug_texture", "target": "score_buga",
                 "png": "input.png"}
            )
            path = self.write_project(root, value)
            with self.assertRaisesRegex(
                project.ProjectError, "repeats one scorebug_texture"
            ):
                project.read_project(path)

    def test_scorebug_report_is_hash_pinned(self) -> None:
        pins = project.pin_reports({"scorebug_texture"})
        self.assertEqual(set(pins), {"scorebug_texture"})
        self.assertEqual(
            pins["scorebug_texture"].sha256,
            project.scorebug_adapter.SCOREBUG_REPORT_SHA256,
        )

    def test_portrait_and_crib_use_distinct_pinned_metadata(self) -> None:
        pins = project.pin_reports({"player_portrait", "crib_team_photo"})
        self.assertEqual(set(pins), {"player_portrait", "crib_team_photo"})
        self.assertNotEqual(pins["player_portrait"].path,
                            pins["crib_team_photo"].path)
        self.assertLess(pins["crib_team_photo"].size, 8 * 1024 * 1024)

    def test_crib_report_manifest_pin_is_stable_across_bundle_roots(self) -> None:
        left = project.InputPin(
            Path("/tmp/vc-provider-left/mod_editor/data/crib.json"),
            b"metadata", 8, "a" * 64, (1, 2),
        )
        right = project.InputPin(
            Path("/tmp/vc-provider-right/mod_editor/data/crib.json"),
            b"metadata", 8, "a" * 64, (3, 4),
        )
        expected = {
            "path": "$PINNED_REPORT/crib_team_photo",
            "size": 8,
            "sha256": "a" * 64,
        }

        self.assertEqual(
            project.stable_report_pin_record("crib_team_photo", left),
            expected,
        )
        self.assertEqual(
            project.stable_report_pin_record("crib_team_photo", right),
            expected,
        )
        self.assertNotEqual(
            project.stable_report_pin_record("player_portrait", left),
            project.stable_report_pin_record("player_portrait", right),
        )

    def test_forged_player_reports_are_refused(self) -> None:
        for kind in ("player_roster", "player_portrait"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                payload = bytearray(project.REPORTS[kind].read_bytes())
                payload[-2] ^= 1
                forged = root / "forged.json"
                forged.write_bytes(payload)
                original = project.REPORTS[kind]
                project.REPORTS[kind] = forged
                try:
                    with self.assertRaisesRegex(project.ProjectError, "SHA-256"):
                        project.pin_reports({kind})
                finally:
                    project.REPORTS[kind] = original

    def test_symlink_player_reports_are_refused(self) -> None:
        for kind in ("player_roster", "player_portrait"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                link = root / "report-link.json"
                link.symlink_to(project.REPORTS[kind])
                original = project.REPORTS[kind]
                project.REPORTS[kind] = link
                try:
                    with self.assertRaisesRegex(project.ProjectError, "non-symlink"):
                        project.pin_reports({kind})
                finally:
                    project.REPORTS[kind] = original

    def test_cross_pack_portrait_target_is_retained(self) -> None:
        _, _, target = project.portrait_targets.select_target(
            "4070", project.REPORTS["player_portrait"])
        self.assertEqual(len(target.span_segments), 2)
        self.assertEqual([item["pack_path"] for item in target.span_segments],
                         ["vc_53450030/3", "vc_53450030/4"])
        self.assertEqual(sum(item["size"] for item in target.span_segments), 17_568)

    def sparse_roster_view(self, shared_names: bool = False):
        body = bytearray(0x1000)

        def put(offset: int, value: str) -> None:
            payload = (value + "\0").encode("utf-16le")
            body[offset:offset + len(payload)] = payload

        put(0x20, "historic")
        team_offset = 0x100
        player_offset = 0x400
        values = {
            "nickname": (0x700, "Comets '80"),
            "abbreviation": (0x718, "COM80"),
            "asset_code": (0x724, "42"),
            "city": (0x72A, "Orbit City"),
            "city_abbreviation": (0x740, "ORB"),
            "first_name": (0x748, "Alex"),
            "last_name": (0x752, "Smith"),
        }
        if shared_names:
            values["last_name"] = values["first_name"]
        for offset, value in values.values():
            put(offset, value)
        for field, pointer in project.TEAM_IDENTITY_POINTERS.items():
            target = values[field][0]
            struct.pack_into("<i", body, team_offset + pointer,
                             target - (team_offset + pointer) + 1)
        asset_target = values["asset_code"][0]
        struct.pack_into("<i", body, team_offset + 0x10C,
                         asset_target - (team_offset + 0x10C) + 1)
        body[team_offset + project.ROST_TEAM_COUNT_FIELD] = 1
        for field, pointer in (("first_name", 0x10), ("last_name", 0x14)):
            target = values[field][0]
            struct.pack_into("<i", body, player_offset + pointer,
                             target - (player_offset + pointer) + 1)
        struct.pack_into("<H", body, player_offset + 0x06, 1234)
        struct.pack_into("<I", body, player_offset + 0x20,
                         (12 << 3) | 0x80000)
        body[player_offset + 0x35] = 3
        player_raw = bytes(body[player_offset:player_offset + 0x54])
        parsed = {
            "label": "historic",
            "teams": [{
                "index": 0, "offset": team_offset, "roster_size": 1,
                **{name: value for name, (_offset, value) in values.items()
                   if name in {"nickname", "abbreviation", "asset_code",
                               "city", "city_abbreviation"}},
                **{f"{name}_offset": offset for name, (offset, _value) in values.items()
                   if name in {"nickname", "abbreviation", "asset_code",
                               "city", "city_abbreviation"}},
            }],
            "players": [{
                "pool": "primary_players", "index": 0, "offset": player_offset,
                "first_name": values["first_name"][1],
                "first_name_offset": values["first_name"][0],
                "last_name": values["last_name"][1],
                "last_name_offset": values["last_name"][0],
                "raw_hex": player_raw.hex(), "team_refs": [0],
            }],
            "stadiums": [], "coaches": [], "colleges": [],
            "historic_descriptors": [], "team_labels": [], "generated_names": [],
        }
        return project.RosterResourceView(
            113, "0x12345678", len(body) + 0x20, 0x1800, bytes(body), parsed)

    def test_sparse_roster_shapes_need_no_retail_report_or_png(self) -> None:
        team = {"kind": "roster_team_text", "resource_outer_index": 113,
                "team_index": 0, "changes": {"nickname": "Comets"}}
        player = {"kind": "roster_player_text", "resource_outer_index": 113,
                  "primary_player_index": 0,
                  "changes": {"first_name": "Al", "jersey_number": 88}}
        self.assertEqual(project.validate_edit_shape(team, 0), team)
        self.assertEqual(project.validate_edit_shape(player, 1), player)
        self.assertEqual(project.pin_reports({"roster_team_text",
                                              "roster_player_text"}), {})
        with self.assertRaisesRegex(project.ProjectError, "invalid"):
            project.validate_edit_shape({**player, "changes": {"position": 4}}, 0)

    def test_sparse_historical_team_edit_is_single_zero_padded_span(self) -> None:
        edit = {"kind": "roster_team_text", "resource_outer_index": 113,
                "team_index": 0, "changes": {"nickname": "Comets"}}
        results = project.build_roster_team_text_imports(
            edit, self.sparse_roster_view())
        self.assertEqual(len(results), 1)
        replacement, _previews, report, selector, target = results[0]
        self.assertEqual(selector, "roster:113:team:0:nickname")
        self.assertEqual(len(replacement), len(("Comets '80\0").encode("utf-16le")))
        self.assertEqual(replacement[:14], "Comets\0".encode("utf-16le"))
        self.assertEqual(replacement[14:], bytes(len(replacement) - 14))
        self.assertEqual(target["resource_outer_index"], 113)
        self.assertTrue(report["claims"]["historical_resource"])

    def test_sparse_historical_player_name_and_number_preserve_contracts(self) -> None:
        edit = {"kind": "roster_player_text", "resource_outer_index": 113,
                "primary_player_index": 0,
                "changes": {"first_name": "Al", "jersey_number": 88}}
        results = project.build_roster_player_text_imports(
            edit, self.sparse_roster_view())
        self.assertEqual(len(results), 2)
        self.assertEqual([item[4]["field"] for item in results],
                         ["first_name", "jersey_number"])
        self.assertEqual(results[0][0], "Al\0".encode("utf-16le") + bytes(4))
        before = int(results[1][4]["retail_jersey_word"], 16)
        after = int(results[1][4]["replacement_jersey_word"], 16)
        self.assertEqual((after >> 3) & 0x7F, 88)
        self.assertEqual(before & ~0x3F8, after & ~0x3F8)

    def test_sparse_historical_shared_name_fails_closed(self) -> None:
        edit = {"kind": "roster_player_text", "resource_outer_index": 113,
                "primary_player_index": 0, "changes": {"first_name": "Al"}}
        with self.assertRaisesRegex(project.ProjectError, "shared"):
            project.build_roster_player_text_imports(
                edit, self.sparse_roster_view(shared_names=True))

    def test_legacy_identity_writer_now_accepts_shorter_bounded_values(self) -> None:
        edit = self.team_identity_edit()
        edit.update({"city": "D", "nickname": "L", "abbreviation": "D",
                     "city_abbreviation": "D"})
        results = project.build_team_identity_imports(
            edit, project.REPORTS["team_identity"])
        self.assertEqual(len(results), 4)
        self.assertTrue(all(len(item[0]) == item[4]["allocation_bytes"]
                            for item in results))
        self.assertTrue(all(item[0][2:] == bytes(len(item[0]) - 2)
                            for item in results))

    def prepared(self, root: Path, order: int, absolute: int,
                 before: bytes, after: bytes) -> project.PreparedEdit:
        replacement = root / f"replacement_{order}.bin"
        replacement.write_bytes(after)
        report = root / f"report_{order}.json"
        report.write_bytes(b"{}\n")
        return project.PreparedEdit(
            order=order, kind="test", selector=f"target{order}",
            project_edit={"kind": "test"}, input_sha256={}, target={},
            pack_path="pack", pack_sector=0, pack_size=1024,
            pack_sha256="0" * 64, pack_offset=absolute, absolute=absolute,
            retail_span_sha256=hashlib.sha256(before).hexdigest(),
            replacement_path=replacement, replacement_size=len(after),
            replacement_sha256=hashlib.sha256(after).hexdigest(),
            relative_runs=project.difference_runs(before, after),
            import_report_path=report,
            import_report_sha256=hashlib.sha256(b"{}\n").hexdigest(),
            preview_paths=[],
        )

    def test_union_verifier_proves_gaps_and_selected_spans(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_bytes = bytes(range(128))
            output_bytes = bytearray(source_bytes)
            output_bytes[12:16] = b"ABCD"
            output_bytes[80:83] = b"xyz"
            source = root / "source.bin"
            output = root / "output.bin"
            source.write_bytes(source_bytes)
            output.write_bytes(output_bytes)
            edits = [
                self.prepared(root, 0, 12, source_bytes[12:16], bytes(output_bytes[12:16])),
                self.prepared(root, 1, 80, source_bytes[80:83], bytes(output_bytes[80:83])),
            ]
            source_fd = os.open(source, os.O_RDONLY)
            output_fd = os.open(output, os.O_RDONLY)
            try:
                result = project.verify_union(source_fd, output_fd, len(source_bytes), edits)
            finally:
                os.close(source_fd)
                os.close(output_fd)
            expected_offsets = [
                index for index, pair in enumerate(zip(source_bytes, output_bytes))
                if pair[0] != pair[1]
            ]
            self.assertEqual(result["changed_byte_count"], len(expected_offsets))
            self.assertEqual(result["changed_offsets_u64le_sha256"],
                             project.offset_digest(expected_offsets, "<Q"))
            self.assertEqual(result["source_sha256"], hashlib.sha256(source_bytes).hexdigest())
            self.assertEqual(result["output_sha256"],
                             hashlib.sha256(output_bytes).hexdigest())
            self.assertTrue(result["all_bytes_outside_selected_spans_identical"])

    def test_virtual_union_matches_the_materialized_output_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_bytes = bytes(range(128))
            output_bytes = bytearray(source_bytes)
            output_bytes[12:16] = b"ABCD"
            output_bytes[80:83] = b"xyz"
            source = root / "source.bin"
            output = root / "output.bin"
            source.write_bytes(source_bytes)
            output.write_bytes(output_bytes)
            edits = [
                self.prepared(
                    root, 0, 12, source_bytes[12:16],
                    bytes(output_bytes[12:16]),
                ),
                self.prepared(
                    root, 1, 80, source_bytes[80:83],
                    bytes(output_bytes[80:83]),
                ),
            ]
            source_fd = os.open(source, os.O_RDONLY)
            output_fd = os.open(output, os.O_RDONLY)
            try:
                materialized = project.verify_union(
                    source_fd, output_fd, len(source_bytes), edits
                )
                virtual = project.verify_union_virtual(
                    source_fd, len(source_bytes), edits
                )
            finally:
                os.close(source_fd)
                os.close(output_fd)
            self.assertEqual(virtual, materialized)
            self.assertEqual(
                virtual["output_sha256"], hashlib.sha256(output_bytes).hexdigest()
            )

    def test_virtual_union_refuses_a_changed_replacement_after_preparation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_bytes = b"a" * 64
            source = root / "source.bin"
            source.write_bytes(source_bytes)
            edit = self.prepared(root, 0, 10, b"aa", b"bc")
            edit.replacement_path.write_bytes(b"bd")
            source_fd = os.open(source, os.O_RDONLY)
            try:
                with self.assertRaisesRegex(
                    project.ProjectError, "virtual selected span reconstruction"
                ):
                    project.verify_union_virtual(source_fd, 64, [edit])
            finally:
                os.close(source_fd)

    def test_virtual_union_refuses_overlapping_selected_spans(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_bytes = b"a" * 64
            source = root / "source.bin"
            source.write_bytes(source_bytes)
            edits = [
                self.prepared(root, 0, 10, b"aaaa", b"ABCD"),
                self.prepared(root, 1, 12, b"aaaa", b"EFGH"),
            ]
            source_fd = os.open(source, os.O_RDONLY)
            try:
                with self.assertRaisesRegex(project.ProjectError, "overlap"):
                    project.verify_union_virtual(source_fd, 64, edits)
            finally:
                os.close(source_fd)

    def test_virtual_output_requires_a_missing_non_symlink_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            absent = root / "proof.xiso.iso"
            self.assertEqual(project.absent_virtual_output_path(absent), absent)
            absent.write_bytes(b"not a historical output")
            with self.assertRaisesRegex(project.ProjectError, "requires an absent"):
                project.absent_virtual_output_path(absent)
            absent.unlink()
            real = root / "real"
            real.mkdir()
            linked = root / "linked"
            linked.symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(project.ProjectError, "symlink"):
                project.absent_virtual_output_path(linked / "proof.xiso.iso")

    def test_historical_receipt_replay_only_changes_catalog_provenance(self) -> None:
        current = {
            "schema": "fixture/v1",
            "compatibility_report": {
                "path": "$PINNED_REPORT/torso", "sha256": "b" * 64,
            },
            "target": {"selector": "09H0", "span_sha256": "c" * 64},
            "replacement": {"span_sha256": "d" * 64},
        }
        historical = json.loads(json.dumps(current))
        historical["compatibility_report"]["sha256"] = "a" * 64
        self.assertEqual(
            project.replay_historical_import_report(
                current, historical, "torso"
            ),
            historical,
        )

        forged = json.loads(json.dumps(historical))
        forged["target"]["span_sha256"] = "e" * 64
        with self.assertRaisesRegex(
            project.ProjectError, "beyond catalog provenance"
        ):
            project.replay_historical_import_report(current, forged, "torso")

    def test_historical_catalog_pin_must_match_every_import_receipt(self) -> None:
        current = {
            "index": {"path": "/index", "size": 1, "sha256": "1" * 64},
            "inventory": {
                "path": "/inventory", "size": 2, "sha256": "2" * 64,
            },
            "compatibility_reports": {
                "torso": {
                    "path": "/catalog", "size": 20, "sha256": "b" * 64,
                },
            },
        }
        historical = json.loads(json.dumps(current))
        historical["compatibility_reports"]["torso"].update({
            "size": 19, "sha256": "a" * 64,
        })
        receipts = {
            0: {
                "compatibility_report": {
                    "path": "$PINNED_REPORT/torso", "sha256": "a" * 64,
                },
            },
        }
        self.assertIs(
            project.validate_historical_canonical_inputs(
                historical, current, [{"kind": "torso"}], receipts
            ),
            historical,
        )

        forged = {0: json.loads(json.dumps(receipts[0]))}
        forged[0]["compatibility_report"]["sha256"] = "f" * 64
        with self.assertRaisesRegex(project.ProjectError, "catalog pin"):
            project.validate_historical_canonical_inputs(
                historical, current, [{"kind": "torso"}],
                forged,
            )

    def test_union_verifier_refuses_difference_outside_union(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_bytes = b"a" * 64
            output_bytes = bytearray(source_bytes)
            output_bytes[10:12] = b"bc"
            output_bytes[50] = ord("z")
            source = root / "source.bin"
            output = root / "output.bin"
            source.write_bytes(source_bytes)
            output.write_bytes(output_bytes)
            edit = self.prepared(root, 0, 10, source_bytes[10:12], bytes(output_bytes[10:12]))
            source_fd = os.open(source, os.O_RDONLY)
            output_fd = os.open(output, os.O_RDONLY)
            try:
                with self.assertRaisesRegex(project.ProjectError, "outside selected spans"):
                    project.verify_union(source_fd, output_fd, 64, [edit])
            finally:
                os.close(source_fd)
                os.close(output_fd)

    def test_union_verifier_refuses_overlapping_selected_spans(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_bytes = b"a" * 64
            output_bytes = bytearray(source_bytes)
            output_bytes[10:16] = b"ABCDEF"
            source = root / "source.bin"
            output = root / "output.bin"
            source.write_bytes(source_bytes)
            output.write_bytes(output_bytes)
            edits = [
                self.prepared(root, 0, 10, source_bytes[10:14],
                              bytes(output_bytes[10:14])),
                self.prepared(root, 1, 12, source_bytes[12:16],
                              bytes(output_bytes[12:16])),
            ]
            source_fd = os.open(source, os.O_RDONLY)
            output_fd = os.open(output, os.O_RDONLY)
            try:
                with self.assertRaisesRegex(project.ProjectError, "overlap"):
                    project.verify_union(source_fd, output_fd, 64, edits)
            finally:
                os.close(source_fd)
                os.close(output_fd)


if __name__ == "__main__":
    unittest.main()
