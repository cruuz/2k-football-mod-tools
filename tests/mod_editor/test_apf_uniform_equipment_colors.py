"""Exact-byte coverage for APF HOME/AWAY uniform equipment colors."""

from __future__ import annotations

from pathlib import Path
import hashlib
import struct
import tempfile
import unittest
from unittest import mock

from mod_editor.apf_studio.backend import ensure_tools_importable
from mod_editor.apf_studio import project
from mod_editor.apf_studio.models import Modification


ensure_tools_importable()
import apf_outer  # type: ignore  # noqa: E402
import apf_player_position_patch  # type: ignore  # noqa: E402
import apf_roster  # type: ignore  # noqa: E402
import apf_roster_composite_patch  # type: ignore  # noqa: E402
import apf_uniform_equipment_color_patch as writer  # type: ignore  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "extracted/All-Pro Football 2K8 (USA)/0A"


def _synthetic_roster() -> tuple[bytes, list[apf_roster.RootTable]]:
    body = bytearray(0x20000)
    tables = [
        apf_roster.RootTable(index, 0, 0, 0, 0, None, 0, 0)
        for index in range(40)
    ]
    tables[4] = apf_roster.RootTable(4, 40, 0, 0, 0x1000, 0x180, 40 * 0x180, 0)
    tables[16] = apf_roster.RootTable(16, 266, 0, 0, 0x8000, 0x30, 266 * 0x30, 0)
    tables[17] = apf_roster.RootTable(17, 3724, 0, 0, 0xC000, 0x08, 3724 * 8, 0)
    tables[19] = apf_roster.RootTable(19, 40, 0, 0, 0x5000, 0x98, 40 * 0x98, 0)

    def pointer(field: int, target: int) -> None:
        struct.pack_into(">i", body, field, target - field + 1)

    for team_index in range(40):
        team_offset = tables[4].offset + team_index * tables[4].stride
        config_offset = tables[19].offset + team_index * tables[19].stride
        pointer(team_offset + 0xBC, config_offset)
        palette_group = (team_index * 3) % 40
        pointer(config_offset + 0x70, tables[16].offset + (palette_group * 2 + 1) * 0x30)
        pointer(config_offset + 0x74, tables[16].offset + palette_group * 2 * 0x30)
        selector_group = (team_index * 7) % 40
        selector_base = selector_group * 28
        for selector_number in range(28):
            selector_index = selector_base + ((selector_number + 14) % 28)
            pointer(
                config_offset + selector_number * 4,
                tables[17].offset + selector_index * 8,
            )
        for bank_base in (0, 14):
            turtleneck = tables[17].offset + (selector_base + bank_base) * 8
            facemask = tables[17].offset + (selector_base + bank_base + 3) * 8
            body[turtleneck : turtleneck + 8] = bytes((0xA0, 0xA1, team_index % 10, 0xA3, 0xA4, 0xA5, 0xA6, 0xA7))
            body[facemask : facemask + 8] = bytes((0xB0, 0xB1, 0xB2, 0xB3, 0xB4, 0xB5, (team_index + 1) % 10, 0xB7))
    return bytes(body), tables


class UniformEquipmentColorContractTests(unittest.TestCase):
    def test_payload_and_project_metadata_are_canonical(self) -> None:
        value = writer.UniformEquipmentColors(
            0,
            writer.EquipmentColorBank(1, 2),
            writer.EquipmentColorBank(3, 4),
        )
        payload = writer.encode_replacement_payload(value)
        self.assertEqual(writer.decode_replacement_payload(payload), value)
        self.assertEqual(
            project.decode_uniform_equipment_color_payload(
                payload, "apf:uniform-equipment-colors:0"
            )["team_index"],
            0,
        )
        body, tables = _synthetic_roster()
        with mock.patch.object(writer.apf_roster, "parse_root", return_value=(tables, {})):
            target = writer._resolve_targets(body)[0].public
        metadata = writer.target_metadata(target)
        self.assertEqual(
            project._validated_metadata(
                target.asset_id, "uniform_equipment_colors", metadata
            ),
            metadata,
        )
        with self.assertRaisesRegex(project.ProjectError, "target changed"):
            project._validated_metadata(
                target.asset_id,
                "uniform_equipment_colors",
                {**metadata, "facemask_selector_byte": 5},
            )
        with self.assertRaisesRegex(writer.UniformEquipmentColorError, "canonical"):
            writer.decode_replacement_payload(payload.replace(b'"away"', b' "away"'))

    def test_synthetic_all_40_pointer_graph_is_unique_and_fail_closed(self) -> None:
        body, tables = _synthetic_roster()
        with mock.patch.object(writer.apf_roster, "parse_root", return_value=(tables, {})):
            targets = writer._resolve_targets(body)
        self.assertEqual(tuple(targets), tuple(range(40)))
        selected: set[int] = set()
        for team_index, target in targets.items():
            self.assertEqual(
                writer._value_from_body(body, target),
                writer.UniformEquipmentColors(
                    team_index,
                    writer.EquipmentColorBank((team_index + 1) % 10, team_index % 10),
                    writer.EquipmentColorBank((team_index + 1) % 10, team_index % 10),
                ),
            )
            offsets = {
                target.home_facemask_offset,
                target.away_facemask_offset,
                target.home_turtleneck_offset,
                target.away_turtleneck_offset,
            }
            self.assertFalse(selected.intersection(offsets))
            selected.update(offsets)
        aliased = bytearray(body)
        source_field = tables[4].offset + 39 * tables[4].stride + 0xBC
        target_config = tables[19].offset
        struct.pack_into(">i", aliased, source_field, target_config - source_field + 1)
        with mock.patch.object(writer.apf_roster, "parse_root", return_value=(tables, {})):
            with self.assertRaisesRegex(writer.UniformEquipmentColorError, "config"):
                writer._resolve_targets(bytes(aliased))

    def test_bounds_reject_bools_and_out_of_range_indices(self) -> None:
        for team_index in (-1, 40, True):
            with self.subTest(team_index=team_index):
                with self.assertRaises(writer.UniformEquipmentColorError):
                    writer.asset_id(team_index)  # type: ignore[arg-type]
        with self.assertRaisesRegex(writer.UniformEquipmentColorError, "0 to 9"):
            writer.validate_colors(
                writer.UniformEquipmentColors(
                    0,
                    writer.EquipmentColorBank(10, 0),
                    writer.EquipmentColorBank(0, 0),
                )
            )

    def test_project_round_trip_keeps_only_selector_indices(self) -> None:
        body, tables = _synthetic_roster()
        with mock.patch.object(writer.apf_roster, "parse_root", return_value=(tables, {})):
            target = writer._resolve_targets(body)[7].public
        value = writer.UniformEquipmentColors(
            7,
            writer.EquipmentColorBank(8, 9),
            writer.EquipmentColorBank(1, 2),
        )
        payload = writer.encode_replacement_payload(value)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            replacement = root / "equipment-colors.json"
            replacement.write_bytes(payload)
            modification = Modification(
                target.asset_id,
                "uniform_equipment_colors",
                replacement,
                hashlib.sha256(payload).hexdigest(),
                writer.target_metadata(target),
            )
            archive = project.save_project(
                root / "colors.apf2k8mod",
                source_sha256="a" * 64,
                modifications=(modification,),
            )
            _document, loaded, _annotations = project.load_project(
                archive,
                expected_source_sha256="a" * 64,
                destination_dir=root / "loaded",
            )
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].metadata, modification.metadata)
            self.assertEqual(loaded[0].replacement_path.read_bytes(), payload)
            self.assertNotIn(b"palette", payload.replace(b"palette_index", b""))


@unittest.skipUnless(SOURCE.is_file(), "private APF source is unavailable")
class RetailUniformEquipmentColorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_body, _source = apf_roster.load_roster(SOURCE)
        cls.rows = writer.inspect_colors(SOURCE)
        cls.source = cls.rows[0].value
        cls.identity = writer.build_patch(SOURCE, {0: cls.source})
        cls.replacement = writer.UniformEquipmentColors(
            0,
            writer.EquipmentColorBank(
                (cls.source.home.facemask_palette_index + 1) % 10,
                (cls.source.home.team_turtleneck_palette_index + 1) % 10,
            ),
            writer.EquipmentColorBank(
                (cls.source.away.facemask_palette_index + 2) % 10,
                (cls.source.away.team_turtleneck_palette_index + 1) % 10,
            ),
        )
        cls.patched = writer.build_patch(SOURCE, {0: cls.replacement})

    def test_real_source_resolves_every_team_and_identity_is_verbatim(self) -> None:
        self.assertEqual([row.target.team_index for row in self.rows], list(range(40)))
        self.assertEqual(self.identity.manifest["mode"], "no_op")
        self.assertEqual(
            self.identity.manifest["output"]["decoded_changed_byte_count"], 0
        )
        self.assertEqual(
            self.identity.manifest["source"]["entry_sha256"],
            self.identity.manifest["output"]["entry_sha256"],
        )

    def test_real_writer_changes_only_four_selector_bytes(self) -> None:
        archive = apf_outer.parse_archive(SOURCE)
        entry = archive.entries[apf_roster.OUTER_TABLE_INDEX]
        rebuilt = writer._entry_body(self.patched.entry_bytes, entry)
        target = writer._resolve_targets(self.source_body)[0]
        expected = {
            target.home_facemask_offset,
            target.away_facemask_offset,
            target.home_turtleneck_offset,
            target.away_turtleneck_offset,
        }
        changed = {
            offset
            for offset, values in enumerate(zip(self.source_body, rebuilt, strict=True))
            if values[0] != values[1]
        }
        self.assertEqual(changed, expected)
        self.assertEqual(writer._value_from_body(rebuilt, target), self.replacement)
        for palette_offset in (target.home_palette_offset, target.away_palette_offset):
            self.assertEqual(
                rebuilt[palette_offset : palette_offset + 0x30],
                self.source_body[palette_offset : palette_offset + 0x30],
            )
        for offset in expected:
            record_start = offset - (
                writer.FACEMASK_SELECTOR_BYTE
                if offset in {target.home_facemask_offset, target.away_facemask_offset}
                else writer.TURTLENECK_SELECTOR_BYTE
            )
            for byte_index in range(writer.SELECTOR_STRIDE):
                if record_start + byte_index != offset:
                    self.assertEqual(
                        rebuilt[record_start + byte_index],
                        self.source_body[record_start + byte_index],
                    )

    def test_equipment_colors_compose_with_another_roster_edit_class(self) -> None:
        source_position = self.source_body[apf_roster.ROOT_SIZE + 0x34]
        position = apf_player_position_patch.build_patch(
            SOURCE, {0: source_position}
        )
        composed = apf_roster_composite_patch.compose_components(
            SOURCE,
            positions=position,
            equipment_colors=self.patched,
        )
        self.assertEqual(composed.manifest["uniform_equipment_color_edit_count"], 1)
        self.assertEqual(
            composed.manifest["output"]["uniform_equipment_color_changed_byte_count"],
            4,
        )
        self.assertEqual(
            composed.manifest["output"]["player_position_changed_byte_count"], 0
        )


if __name__ == "__main__":
    unittest.main()
