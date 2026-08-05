"""Registry command ownership for executable package-relative modules."""

from __future__ import annotations

import unittest

from mod_editor.capabilities import validate_registry


class CapabilityRegistryModuleCommandTest(unittest.TestCase):
    def test_python_dash_m_resolves_to_exact_repository_module(self) -> None:
        self.assertEqual(
            validate_registry._command_module(
                "PYTHONPATH=. python3 -m "
                "mod_editor.apf_studio.stadium_model_import import --help",
                "test.command",
            ),
            "mod_editor/apf_studio/stadium_model_import.py",
        )

    def test_direct_script_commands_keep_their_existing_identity(self) -> None:
        self.assertEqual(
            validate_registry._command_module(
                "python3 tools/apf_logo_patch.py --help", "test.command"
            ),
            "tools/apf_logo_patch.py",
        )

    def test_unknown_or_malformed_dash_m_target_is_not_accepted(self) -> None:
        self.assertIsNone(
            validate_registry._command_module(
                "python3 -m mod_editor.does_not_exist --help", "test.command"
            )
        )
        self.assertIsNone(
            validate_registry._command_module(
                "python3 -m ../outside --help", "test.command"
            )
        )


if __name__ == "__main__":
    unittest.main()
