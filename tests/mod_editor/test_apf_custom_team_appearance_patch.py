"""Safety and real-source tests for APF custom-team appearance editing."""

from __future__ import annotations

from pathlib import Path
import struct
import hashlib
import tempfile
import unittest

from mod_editor.apf_studio.backend import ensure_tools_importable
from mod_editor.apf_studio import project
from mod_editor.apf_studio.models import Modification


ensure_tools_importable()
import apf_custom_team_appearance_patch as writer  # type: ignore  # noqa: E402
import apf_outer  # type: ignore  # noqa: E402
import apf_player_position_patch  # type: ignore  # noqa: E402
import apf_roster  # type: ignore  # noqa: E402
import apf_roster_composite_patch  # type: ignore  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "extracted/All-Pro Football 2K8 (USA)/0A"


def _bank(
    *,
    helmet: bytes = bytes.fromhex("1003020009000000"),
    logo: bytes = bytes.fromhex("5000000302010000"),
) -> writer.AppearanceBank:
    return writer.AppearanceBank(tuple(0xFF000000 + index for index in range(10)), helmet, logo)


class CustomTeamAppearanceContractTests(unittest.TestCase):
    def test_payload_target_metadata_and_project_validation_are_canonical(self) -> None:
        appearance = writer.CustomTeamAppearance(32, _bank(), _bank())
        payload = writer.encode_replacement_payload(appearance)
        self.assertEqual(writer.decode_replacement_payload(payload), appearance)
        self.assertEqual(
            project.decode_custom_team_appearance_payload(
                payload, "apf:custom-team-appearance:32"
            )["slot"],
            32,
        )
        metadata = {
            "slot": 32,
            "config_index": 32,
            "home_palette_index": 65,
            "away_palette_index": 64,
            "home_helmet_selector_index": 913,
            "home_logo_selector_index": 915,
            "away_helmet_selector_index": 899,
            "away_logo_selector_index": 901,
            "palette_color_count": 10,
            "selector_size": 8,
            "selector_tail_semantics": "opaque",
        }
        self.assertEqual(
            project._validated_metadata(
                "apf:custom-team-appearance:32",
                "custom_team_appearance",
                metadata,
            ),
            metadata,
        )
        with self.assertRaisesRegex(project.ProjectError, "target changed"):
            project._validated_metadata(
                "apf:custom-team-appearance:32",
                "custom_team_appearance",
                {**metadata, "home_palette_index": 66},
            )
        with self.assertRaisesRegex(writer.CustomTeamAppearanceError, "canonical"):
            writer.decode_replacement_payload(payload.replace(b"FF000000", b"ff000000"))

    def test_bounds_and_cardinality_fail_closed(self) -> None:
        for slot in (31, 40, True):
            with self.subTest(slot=slot):
                with self.assertRaises(writer.CustomTeamAppearanceError):
                    writer.asset_id(slot)  # type: ignore[arg-type]
        with self.assertRaisesRegex(writer.CustomTeamAppearanceError, "10 ARGB"):
            writer.validate_appearance(
                writer.CustomTeamAppearance(
                    32,
                    writer.AppearanceBank((0,), b"\0" * 8, b"\0" * 8),
                    _bank(),
                )
            )
        with self.assertRaisesRegex(writer.CustomTeamAppearanceError, "0..23"):
            writer.validate_appearance(
                writer.CustomTeamAppearance(
                    32, _bank(helmet=bytes((24,)) + b"\0" * 7), _bank()
                )
            )
        with self.assertRaisesRegex(writer.CustomTeamAppearanceError, "0..117"):
            writer.validate_appearance(
                writer.CustomTeamAppearance(
                    32, _bank(logo=bytes((118,)) + b"\0" * 7), _bank()
                )
            )
        with self.assertRaisesRegex(writer.CustomTeamAppearanceError, "0..9"):
            writer.validate_appearance(
                writer.CustomTeamAppearance(
                    32,
                    _bank(helmet=bytes((1, 10)) + b"\0" * 6),
                    _bank(),
                )
            )

    def test_eagles_preset_preserves_helmet_tail_and_applies_proved_logo_route(self) -> None:
        current = writer.CustomTeamAppearance(
            32,
            _bank(
                helmet=bytes.fromhex("0703020009000000"),
                logo=bytes.fromhex("5000000302010000"),
            ),
            _bank(
                helmet=bytes.fromhex("1304010506070809"),
                logo=bytes.fromhex("5C02030405060708"),
            ),
        )
        preset = writer.eagles_2017_preset(current)
        self.assertEqual(preset.home.palette, writer.EAGLES_2017_PALETTE)
        self.assertEqual(preset.away.palette, writer.EAGLES_2017_PALETTE)
        self.assertEqual(preset.home.helmet_selector, bytes.fromhex("0708020009000000"))
        self.assertEqual(preset.away.helmet_selector, bytes.fromhex("1308010506070809"))
        self.assertEqual(preset.home.logo_selector, bytes.fromhex("1E00010009000000"))
        self.assertEqual(preset.away.logo_selector, bytes.fromhex("1E00010009000000"))

    def test_project_round_trip_preserves_replacement_only_payload(self) -> None:
        appearance = writer.eagles_2017_preset(
            writer.CustomTeamAppearance(32, _bank(), _bank())
        )
        payload = writer.encode_replacement_payload(appearance)
        metadata = {
            "slot": 32,
            "config_index": 32,
            "home_palette_index": 65,
            "away_palette_index": 64,
            "home_helmet_selector_index": 913,
            "home_logo_selector_index": 915,
            "away_helmet_selector_index": 899,
            "away_logo_selector_index": 901,
            "palette_color_count": 10,
            "selector_size": 8,
            "selector_tail_semantics": "opaque",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            replacement = root / "appearance.json"
            replacement.write_bytes(payload)
            modification = Modification(
                "apf:custom-team-appearance:32",
                "custom_team_appearance",
                replacement,
                hashlib.sha256(payload).hexdigest(),
                metadata,
            )
            archive = project.save_project(
                root / "eagles.apf2k8mod",
                source_sha256="a" * 64,
                modifications=(modification,),
            )
            _document, loaded, _annotations = project.load_project(
                archive,
                expected_source_sha256="a" * 64,
                destination_dir=root / "loaded",
            )
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].metadata, metadata)
            self.assertEqual(loaded[0].replacement_path.read_bytes(), payload)


@unittest.skipUnless(SOURCE.is_file(), "private APF source is unavailable")
class RetailCustomTeamAppearanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_body, _source = apf_roster.load_roster(SOURCE)
        cls.rows = writer.inspect_appearances(SOURCE)
        cls.stock = cls.rows[0][1]
        cls.preset = writer.eagles_2017_preset(cls.stock)
        cls.result = writer.build_patch(SOURCE, {32: cls.preset})

    def test_all_eight_user_slots_are_uniquely_pointer_proved(self) -> None:
        self.assertEqual([target.slot for target, _value in self.rows], list(range(32, 40)))
        all_indices: set[int] = set()
        for target, _appearance in self.rows:
            metadata = writer.target_metadata(target)
            self.assertEqual(metadata["config_index"], target.slot)
            owned = {
                target.home_palette_index,
                target.away_palette_index,
                target.home_helmet_selector_index,
                target.home_logo_selector_index,
                target.away_helmet_selector_index,
                target.away_logo_selector_index,
            }
            self.assertFalse(all_indices.intersection(owned))
            all_indices.update(owned)

    def test_real_writer_changes_only_selected_records_and_preserves_metadata(self) -> None:
        archive = apf_outer.parse_archive(SOURCE)
        entry = archive.entries[apf_roster.OUTER_TABLE_INDEX]
        rebuilt = writer._entry_body(self.result.entry_bytes, entry)
        targets = writer._resolve_targets(self.source_body)
        target = targets[32]
        allowed: set[int] = set()
        for start, length in (
            (target.home_palette_offset, 40),
            (target.away_palette_offset, 40),
            (target.home_helmet_offset, 8),
            (target.home_logo_offset, 8),
            (target.away_helmet_offset, 8),
            (target.away_logo_offset, 8),
        ):
            allowed.update(range(start, start + length))
        changed = {
            index
            for index, pair in enumerate(zip(self.source_body, rebuilt, strict=True))
            if pair[0] != pair[1]
        }
        self.assertTrue(changed)
        self.assertTrue(changed.issubset(allowed))
        for palette_offset in (target.home_palette_offset, target.away_palette_offset):
            self.assertEqual(
                rebuilt[palette_offset + 40 : palette_offset + 48],
                self.source_body[palette_offset + 40 : palette_offset + 48],
            )
        self.assertEqual(writer._appearance_from_body(rebuilt, target), self.preset)
        self.assertLessEqual(
            self.result.manifest["output"]["compressed_block_size"], entry.size
        )

    def test_pointer_alias_tamper_is_rejected(self) -> None:
        tables, _root = apf_roster.parse_root(self.source_body)
        config = tables[19].offset + 32 * tables[19].stride
        tampered = bytearray(self.source_body)
        away_target = apf_roster.resolve_relative(
            self.source_body, config + 0x74, "AWAY palette"
        )
        assert away_target is not None
        stored = (away_target - (config + 0x70) + 1) & 0xFFFFFFFF
        struct.pack_into(">I", tampered, config + 0x70, stored)
        with self.assertRaisesRegex(writer.CustomTeamAppearanceError, "uniquely owned"):
            writer._resolve_targets(bytes(tampered))

    def test_composes_with_other_roster_owned_edits(self) -> None:
        stock_code = self.source_body[apf_roster.ROOT_SIZE + 0x34]
        position = apf_player_position_patch.build_patch(SOURCE, {0: stock_code})
        combined = apf_roster_composite_patch.compose_components(
            SOURCE, positions=position, appearances=self.result
        )
        self.assertEqual(combined.entry_bytes, self.result.entry_bytes)
        self.assertEqual(
            combined.manifest["custom_team_appearance_edit_count"], 1
        )
        self.assertTrue(
            combined.manifest["validation"]["component_decoded_deltas_disjoint"]
        )


if __name__ == "__main__":
    unittest.main()
