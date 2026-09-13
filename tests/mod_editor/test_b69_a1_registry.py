"""The published JSON schema and all shared count contracts accept the registry."""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]


class RegistryContractsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads((ROOT / "mod_editor/capabilities/registry.v1.json").read_bytes())
        cls.schema = json.loads((ROOT / "mod_editor/capabilities/registry.schema.json").read_bytes())

    def test_schema_games_cardinality_accepts_all_supported_games(self):
        games = self.schema["properties"]["games"]
        self.assertLessEqual(games["minItems"], len(self.registry["games"]))
        self.assertGreaterEqual(games["maxItems"], len(self.registry["games"]))

    def test_schema_surfaces_cardinality_and_enums_accept_texture_lane(self):
        surfaces = self.schema["properties"]["surfaces"]
        with self.subTest(contract="cardinality"):
            self.assertEqual((surfaces["minItems"], surfaces["maxItems"]),
                             (len(self.registry["surfaces"]),) * 2)
        with self.subTest(contract="top-level enum"):
            self.assertEqual(set(surfaces["items"]["enum"]), set(self.registry["surfaces"]))
        with self.subTest(contract="capability enum"):
            allowed = self.schema["$defs"]["capability"]["properties"]["surface"]["enum"]
            self.assertEqual(set(allowed), set(self.registry["surfaces"]))
            self.assertTrue(all(row["surface"] in allowed for row in self.registry["capabilities"]))

    def test_all_five_shared_count_sites_match_actual_registry(self):
        expected = len(self.registry["capabilities"])
        paths = {
            "packaging/check_2k5_mod_studio_runtime.py": 2,
            "packaging/check_apf2k8_mod_studio_runtime.py": 1,
            "tests/mod_editor/test_phase1_packaging.py": 1,
            "tests/mod_editor/test_apf_studio_installer.py": 1,
        }
        for path, sites in paths.items():
            with self.subTest(path=path):
                text = (ROOT / path).read_text(encoding="utf-8")
                values = re.findall(r"len\(registry\.capabilities\) == (\d+)|registry=(\d+)", text)
                self.assertEqual([int(a or b) for a, b in values], [expected] * sites)

    def test_every_published_validation_command_has_a_runnable_local_entrypoint(self):
        from tools.validate_all_mod_editor_capabilities import parse_validation_command
        for row in self.registry["capabilities"]:
            if row["validation_command"]:
                with self.subTest(capability=row["id"]):
                    parse_validation_command(row["validation_command"])

    def test_validation_plan_counts_cover_the_current_registry(self):
        from tools import validate_all_mod_editor_capabilities as runner
        rows = self.registry["capabilities"]
        commands = {row["validation_command"] for row in rows} - {None}
        deferred = tuple(row["id"] for row in rows if row["validation_command"] is None)
        self.assertEqual((runner.EXPECTED_CAPABILITIES, runner.EXPECTED_COVERED_CAPABILITIES,
                          runner.EXPECTED_DEFERRED_CAPABILITIES, runner.EXPECTED_UNIQUE_VALIDATORS,
                          runner.EXPECTED_DEFERRED_IDS),
                         (len(rows), len(rows) - len(deferred), len(deferred), len(commands), deferred))

    def test_runtime_validator_exception_still_refuses_other_scripts_and_arguments(self):
        from tools.validate_all_mod_editor_capabilities import parse_validation_command, ValidationRunError
        for command in (
            "python3 packaging/check_apf2k8_mod_studio_runtime.py --output altered",
            "bash packaging/check_apf2k8_mod_studio_runtime.py",
            "python3 packaging/stage_release.py",
            "python3 packaging/../tools/apf_stfs_roster_rehash.py",
        ):
            with self.subTest(command=command), self.assertRaises(ValidationRunError):
                parse_validation_command(command)


if __name__ == "__main__":
    unittest.main()
