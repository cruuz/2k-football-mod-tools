"""The release probes must import every beta-69 runtime addition explicitly."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


def import_list(path, variable):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    assignments = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == variable
                           for target in node.targets)]
    assert len(assignments) == 1, variable
    return ast.literal_eval(assignments[0].value)


class RuntimeImportsTests(unittest.TestCase):
    def test_apf_probe_imports_both_lazy_scheme_writers(self):
        modules = import_list("packaging/check_apf2k8_mod_studio_runtime.py", "PRODUCT_MODULES")
        self.assertTrue({"mod_editor.core.apf2k8_offensive_schemes",
                         "mod_editor.core.apf2k8_formation_calling"} <= set(modules))

    def test_2k5_probe_imports_both_model_project_modules(self):
        modules = import_list("packaging/check_2k5_mod_studio_runtime.py", "product_modules")
        self.assertTrue({"mod_editor.core.nfl2k5_model_project",
                         "mod_editor.core.nfl2k5_model_project_session"} <= set(modules))


if __name__ == "__main__":
    unittest.main()
