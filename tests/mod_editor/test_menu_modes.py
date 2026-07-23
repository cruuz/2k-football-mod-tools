"""Named, read-only Main Menu inspector tests."""

from __future__ import annotations

import json
from pathlib import Path
import re
import tempfile
import unittest

from mod_editor.core.errors import ValidationError
from mod_editor.core.menu_modes import DEFAULT_REPORT_DIR, inspect_main_menu


ADDRESS = re.compile(r"0x[0-9a-fA-F]+")


class NamedMainMenuInspectorTests(unittest.TestCase):
    def test_nfl_named_rows_initial_state_and_layouts(self) -> None:
        value = inspect_main_menu(" NFL2K5 ")
        self.assertEqual(value["game"], "NFL 2K5")
        self.assertEqual(value["state"]["initial_selection"], "Quick Game")
        self.assertEqual(
            [row["label"] for row in value["state"]["rows"]],
            [
                "Quick Game", "Game Modes", "The Crib|TM|", "Features",
                "Options", "Xbox Live", "Extras",
            ],
        )
        self.assertEqual(
            value["state"]["rows"][0]["activation"],
            {"kind": "push_target_state", "target": "Team Select", "status": "proved"},
        )
        self.assertEqual(
            [row["layout"] for row in value["layout_reachability"]],
            ["main_menu_sub", "main_navi"],
        )
        self.assertEqual(value["rendering"]["default_path"], "serialized_layout")
        self.assertFalse(value["mutation_supported"])

    def test_apf_separates_quicknav_from_unproved_layout_mainmenu(self) -> None:
        value = inspect_main_menu("apf2k8")
        self.assertEqual(value["game"], "APF 2K8")
        self.assertEqual(value["state"]["proved_executable_route_count"], 8)
        self.assertEqual(
            [row["label"] for row in value["state"]["rows"]],
            ["Quick Game", "Teams", "Season", "Practice", "Options", "Features", "Xbox Live"],
        )
        layouts = {row["layout"]: row for row in value["layout_reachability"]}
        self.assertEqual(layouts["quicknav"]["status"], "proved")
        self.assertEqual(layouts["template_quicknav"]["status"], "proved")
        self.assertEqual(layouts["layout_mainmenu"]["status"], "runtime_instantiation_unproved")
        self.assertFalse(layouts["layout_mainmenu"]["direct_main_owner"])
        self.assertEqual(value["labels"]["content_provider"], "proved")
        self.assertEqual(value["labels"]["visible_label_renderer"], "unproved")

    def test_public_results_expose_no_executable_address_or_mutation_contract(self) -> None:
        for game in ("nfl2k5", "apf2k8"):
            with self.subTest(game=game):
                value = inspect_main_menu(game)
                encoded = json.dumps(value, sort_keys=True)
                self.assertIsNone(ADDRESS.search(encoded))
                self.assertNotIn("offset", encoded.lower())
                self.assertNotIn("virtual_address", encoded.lower())
                self.assertTrue(value["read_only"])
                self.assertFalse(value["mutation_supported"])

    def test_unknown_game_is_refused(self) -> None:
        for game in ("", "nfl", "2k8", "offset:123", 5):
            with self.subTest(game=game), self.assertRaises(ValidationError):
                inspect_main_menu(game)  # type: ignore[arg-type]

    def test_missing_symlink_and_tampered_evidence_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for source in DEFAULT_REPORT_DIR.glob("*.json"):
                if source.name in {
                    "menu_state_trace.json",
                    "nfl_main_menu_live_state.json",
                }:
                    (root / source.name).write_bytes(source.read_bytes())

            (root / "menu_state_trace.json").unlink()
            (root / "menu_state_trace.json").symlink_to(
                DEFAULT_REPORT_DIR / "menu_state_trace.json"
            )
            with self.assertRaisesRegex(ValidationError, "non-symlink"):
                inspect_main_menu("nfl2k5", root)

            (root / "menu_state_trace.json").unlink()
            payload = bytearray((DEFAULT_REPORT_DIR / "menu_state_trace.json").read_bytes())
            payload[-2] = ord(" ")
            (root / "menu_state_trace.json").write_bytes(payload)
            with self.assertRaisesRegex(ValidationError, "hash"):
                inspect_main_menu("nfl2k5", root)


if __name__ == "__main__":
    unittest.main()
