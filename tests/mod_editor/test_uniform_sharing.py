"""Public editor uniform-sharing lookup tests."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from mod_editor.core.errors import ValidationError
from mod_editor.core.uniform_sharing import (
    DEFAULT_HELMET_REPORT,
    DEFAULT_REPORT,
    DEFAULT_PANTS_REPORT,
    DEFAULT_SHOULDER_REPORT,
    inspect_apf_helmet_sharing,
    inspect_apf_jersey_sharing,
    inspect_apf_pants_sharing,
    inspect_apf_shoulder_sharing,
    inspect_nfl_uniform_sharing,
)


class UniformSharingLookupTests(unittest.TestCase):
    def test_nfl_alias_lookup_lists_affected_selectors_and_independent_span(self) -> None:
        value = inspect_nfl_uniform_sharing("10h5")
        self.assertEqual(value["selector"]["selector"], "10H5")
        self.assertEqual(value["selector"]["team"], "Green Bay Packers")
        self.assertEqual(value["cross_asset_code_content_alias_count"], 4)
        self.assertEqual(
            {row["texture_name"] for row in value["cross_asset_code_content_aliases"]},
            {"jersey00", "jersey00_mud", "sleeve00", "sleeve00_mud"},
        )
        self.assertTrue(value["on_disc_span_is_independent"])
        for group in value["cross_asset_code_content_aliases"]:
            self.assertTrue(any(
                owner["selector"] == "10H5" for owner in group["affected_owners"]
            ))

    def test_nfl_nonaliased_selector_reports_no_cross_team_warning(self) -> None:
        value = inspect_nfl_uniform_sharing("09H0")
        self.assertEqual(value["cross_asset_code_content_alias_count"], 0)
        self.assertEqual(value["cross_asset_code_content_aliases"], [])
        self.assertIn("No cross-asset-code", value["warning"])

    def test_apf_asset_lookup_lists_only_neutral_bank_labels(self) -> None:
        value = inspect_apf_jersey_sharing(23)
        self.assertEqual(value["asset"]["selector_owner_count"], 26)
        self.assertEqual(value["asset"]["team_count"], 13)
        self.assertEqual({row["bank"] for row in value["asset"]["owners"]}, {0, 1})
        self.assertNotIn("home", str(value["asset"]).lower())
        self.assertNotIn("away", str(value["asset"]).lower())
        self.assertTrue(value["safe_dealias_writer_available"])
        self.assertTrue(value["safe_offline_cli_dealias_writer_available"])
        self.assertFalse(value["public_gui_dealias_writer_available"])

    def test_apf_pants_asset_lookup_sanitizes_shared_owners(self) -> None:
        value = inspect_apf_pants_sharing(13)
        self.assertEqual(value["team_bank_use_count"], 34)
        self.assertEqual({row["bank"] for row in value["team_bank_uses"]}, {0, 1})
        self.assertTrue(value["physical_asset_writer_proved"])
        self.assertFalse(value["selector_or_roster_writer_available"])
        self.assertFalse(value["runtime_visibility_proved"])
        self.assertNotIn("offset", str(value).lower())
        unused = inspect_apf_pants_sharing(23)
        self.assertEqual(unused["team_bank_uses"], [])

    def test_apf_helmet_asset_lookup_sanitizes_channels_and_shared_owners(self) -> None:
        value = inspect_apf_helmet_sharing(16)
        self.assertEqual(value["team_bank_use_count"], 34)
        self.assertEqual({row["bank"] for row in value["team_bank_uses"]}, {0, 1})
        self.assertTrue(value["physical_asset_writer_proved"])
        self.assertFalse(value["selector_or_roster_writer_available"])
        self.assertEqual(value["two_channel_data_contract"], {
            "stored_channels": ["R", "G"],
            "required_blue": 0,
            "required_alpha": 255,
            "shader_meanings_named": False,
        })
        self.assertFalse(value["runtime_visibility_proved"])
        self.assertNotIn("offset", str(value).lower())
        self.assertEqual(inspect_apf_helmet_sharing(23)["team_bank_uses"], [])

    def test_apf_shoulder_asset_lookup_sanitizes_shared_owners(self) -> None:
        value = inspect_apf_shoulder_sharing(8)
        self.assertEqual(value["team_bank_use_count"], 36)
        self.assertEqual({row["bank"] for row in value["team_bank_uses"]}, {0, 1})
        self.assertTrue(value["physical_color_asset_writer_proved"])
        self.assertFalse(value["paired_normal_writer_available"])
        self.assertFalse(value["selector_or_roster_writer_available"])
        self.assertFalse(value["runtime_visibility_proved"])
        self.assertNotIn("offset", str(value).lower())
        self.assertEqual(inspect_apf_shoulder_sharing(23)["team_bank_uses"], [])

    def test_invalid_selectors_are_refused(self) -> None:
        for selector in ("9H0", "09X0", "09H-1", "offset:123"):
            with self.subTest(selector=selector), self.assertRaises(ValidationError):
                inspect_nfl_uniform_sharing(selector)
        for asset in (-1, 24, True):
            with self.subTest(asset=asset), self.assertRaises(ValidationError):
                inspect_apf_jersey_sharing(asset)  # type: ignore[arg-type]
            with self.subTest(pants_asset=asset), self.assertRaises(ValidationError):
                inspect_apf_pants_sharing(asset)  # type: ignore[arg-type]
            with self.subTest(helmet_asset=asset), self.assertRaises(ValidationError):
                inspect_apf_helmet_sharing(asset)  # type: ignore[arg-type]
            with self.subTest(shoulder_asset=asset), self.assertRaises(ValidationError):
                inspect_apf_shoulder_sharing(asset)  # type: ignore[arg-type]

    def test_symlink_and_tampered_reports_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            linked = root / "linked.json"
            linked.symlink_to(DEFAULT_REPORT)
            with self.assertRaisesRegex(ValidationError, "non-symlink"):
                inspect_nfl_uniform_sharing("09H0", linked)

            changed = root / "changed.json"
            payload = bytearray(DEFAULT_REPORT.read_bytes())
            payload[-2] = ord(" ")
            changed.write_bytes(payload)
            with self.assertRaisesRegex(ValidationError, "hash"):
                inspect_apf_jersey_sharing(6, changed)

            pants_link = root / "pants-linked.json"
            pants_link.symlink_to(DEFAULT_PANTS_REPORT)
            with self.assertRaisesRegex(ValidationError, "non-symlink"):
                inspect_apf_pants_sharing(13, pants_link)

            pants_changed = root / "pants-changed.json"
            pants_payload = bytearray(DEFAULT_PANTS_REPORT.read_bytes())
            pants_payload[-2] = ord(" ")
            pants_changed.write_bytes(pants_payload)
            with self.assertRaisesRegex(ValidationError, "hash"):
                inspect_apf_pants_sharing(13, pants_changed)

            helmet_link = root / "helmet-linked.json"
            helmet_link.symlink_to(DEFAULT_HELMET_REPORT)
            with self.assertRaisesRegex(ValidationError, "non-symlink"):
                inspect_apf_helmet_sharing(16, helmet_link)

            helmet_changed = root / "helmet-changed.json"
            helmet_payload = bytearray(DEFAULT_HELMET_REPORT.read_bytes())
            helmet_payload[-2] = ord(" ")
            helmet_changed.write_bytes(helmet_payload)
            with self.assertRaisesRegex(ValidationError, "hash"):
                inspect_apf_helmet_sharing(16, helmet_changed)

            shoulder_link = root / "shoulder-linked.json"
            shoulder_link.symlink_to(DEFAULT_SHOULDER_REPORT)
            with self.assertRaisesRegex(ValidationError, "non-symlink"):
                inspect_apf_shoulder_sharing(8, shoulder_link)

            shoulder_changed = root / "shoulder-changed.json"
            shoulder_payload = bytearray(DEFAULT_SHOULDER_REPORT.read_bytes())
            shoulder_payload[-2] = ord(" ")
            shoulder_changed.write_bytes(shoulder_payload)
            with self.assertRaisesRegex(ValidationError, "hash"):
                inspect_apf_shoulder_sharing(8, shoulder_changed)


if __name__ == "__main__":
    unittest.main()
    inspect_apf_helmet_sharing,
