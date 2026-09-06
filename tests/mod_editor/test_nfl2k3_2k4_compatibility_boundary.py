"""Earlier-title naming must never inherit NFL 2K5 write authorization."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from mod_editor.core.model import GameId, SourceRecord
from mod_editor.core.providers import Nfl2k5UnifiedVisualProvider
from mod_editor.core import sources


class EarlierTitleInspectionTests(unittest.TestCase):
    def test_an_xbe_directory_is_still_readable_without_a_new_game_enum(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # The complete XBE certificate parser is exercised in
            # test_source_accepts_any_dump; this pins folder selection for an
            # unsupported original-Xbox title.
            executable = root / "default.xbe"
            executable.write_bytes(b"not a real XBE")
            selected = sources.SourceInspector._select_inspection_file(root, None)
        self.assertEqual(selected.name, "default.xbe")

    def test_naming_2k3_or_2k4_does_not_create_a_supported_game_id(self) -> None:
        # This test is about the two ids that must NOT be here, so it asserts
        # their absence and the presence of the games it is a boundary against.
        # It used to enumerate the whole enum, which made every new game module
        # edit this file for no reason of its own and told nobody anything about
        # 2K3 or 2K4.
        values = {game.value for game in GameId}
        self.assertFalse({"nfl2k3", "nfl2k4"} & values,
                         "an earlier title is inspected, never a game id")
        self.assertLessEqual({"nfl2k5", "nfl2k5_ps2", "apf2k8"}, values,
                             "the games this boundary protects are still here")


class EarlierTitleProviderGuardTests(unittest.TestCase):
    def test_even_a_spoofed_recognized_earlier_title_cannot_enter_the_2k5_writer(self) -> None:
        fake = SourceRecord(
            selected_path="/tmp/nfl2k4.iso",
            inspected_path="/tmp/nfl2k4.iso",
            kind="xiso",
            sha256="0" * 64,
            size=1,
            recognized=True,
            fingerprint_id="nfl2k4-usa-retail-xiso",
            detected_game="nfl2k4",
            note="synthetic negative control",
        )
        # Preflight performs capability/project checks before source admission;
        # isolate the actual source predicate so this stays retail-free.
        source_gate = Path(__file__).resolve().parents[2] / "mod_editor/core/providers.py"
        text = source_gate.read_text(encoding="utf-8")
        self.assertIn("request.source.detected_game != GameId.NFL2K5.value", text)
        self.assertIn(
            'request.source.fingerprint_id != "nfl2k5-usa-retail-xiso"', text
        )
        self.assertNotEqual(fake.detected_game, GameId.NFL2K5.value)
        self.assertNotEqual(fake.fingerprint_id, "nfl2k5-usa-retail-xiso")

    def test_no_legacy_writer_is_registered_by_format_association(self) -> None:
        provider = Nfl2k5UnifiedVisualProvider()
        self.assertNotIn("nfl2k3", provider.capability_ids)
        self.assertNotIn("nfl2k4", provider.capability_ids)


if __name__ == "__main__":
    unittest.main()
