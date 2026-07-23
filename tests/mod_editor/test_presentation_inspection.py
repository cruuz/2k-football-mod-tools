"""Public APF scorebug inspection tests."""

from __future__ import annotations

import json
from pathlib import Path
import re
import tempfile
import unittest

from mod_editor.core.errors import ValidationError
from mod_editor.core.presentation_inspection import (
    AUDIT,
    FONT_LAYOUT,
    FONT_ROUNDTRIP,
    inspect_apf_scorebug_presentation,
)


class PresentationInspectionTests(unittest.TestCase):
    def test_named_components_and_digital_font_boundary(self) -> None:
        value = inspect_apf_scorebug_presentation()
        self.assertEqual(value["field_scorebug"]["component_count"], 7)
        self.assertEqual(
            [row["name"] for row in value["field_scorebug"]["components"]],
            [
                "scorebug_bottombar", "scorebug_titlebar",
                "scorebug_team_logos", "scorebug_infobar",
                "scorebug_messages", "scorebug_blackbar", "scorebug_statbar",
            ],
        )
        font = value["digital_font"]
        self.assertEqual(font["dimensions"], [128, 128])
        self.assertEqual(font["format"], "DXT5A")
        self.assertTrue(font["copy_only_writer_proved"])
        self.assertTrue(font["all_unrelated_global_parts_preserved"])
        self.assertFalse(font["production_encoder_ready"])
        self.assertFalse(font["runtime_visibility_proved"])
        self.assertEqual(value["safe_writer_count"], 1)

    def test_public_projection_has_no_raw_offsets_or_runtime_overclaim(self) -> None:
        text = json.dumps(inspect_apf_scorebug_presentation())
        self.assertIsNone(re.search(r"0x[0-9a-f]+", text, re.IGNORECASE))
        self.assertNotIn("offset", text.lower())
        self.assertNotIn("outer_index", text)
        self.assertNotIn("inner_index", text)

    def test_symlink_and_tampered_reports_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for source, position in (
                (AUDIT, 0), (FONT_LAYOUT, 1), (FONT_ROUNDTRIP, 2)
            ):
                link = root / f"link-{position}.json"
                link.symlink_to(source)
                args = [AUDIT, FONT_LAYOUT, FONT_ROUNDTRIP]
                args[position] = link
                with self.assertRaisesRegex(ValidationError, "non-symlink"):
                    inspect_apf_scorebug_presentation(*args)

                changed = root / f"changed-{position}.json"
                payload = bytearray(source.read_bytes())
                payload[-2] = ord(" ")
                changed.write_bytes(payload)
                args[position] = changed
                with self.assertRaisesRegex(ValidationError, "hash"):
                    inspect_apf_scorebug_presentation(*args)


if __name__ == "__main__":
    unittest.main()
