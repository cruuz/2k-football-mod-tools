"""The release probes must import every beta-69 runtime addition explicitly."""
import ast
from pathlib import Path
import subprocess
import sys
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
    def test_stfs_rehasher_imports_in_isolated_installed_runtime(self):
        path = ROOT / "tools/apf_stfs_roster_rehash.py"
        probe = "\n".join((
            "import importlib.util, sys",
            f"spec = importlib.util.spec_from_file_location('rehash_probe', {str(path)!r})",
            "module = importlib.util.module_from_spec(spec)",
            "sys.modules[spec.name] = module",
            "spec.loader.exec_module(module)",
            "assert callable(module.rehash_roster)",
        ))
        result = subprocess.run([sys.executable, "-I", "-c", probe], cwd=ROOT,
                                text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_j8_packaged_guide_can_open_its_stfs_format_audit(self):
        guide = (ROOT / "docs/mod_editor/apf2k8_mod_studio_getting_started.md").read_text(encoding="utf-8")
        self.assertIn("../research/apf_stfs_rehash.md", guide)
        allowed = (ROOT / "packaging/apf2k8-release-allowlist.txt").read_text(encoding="utf-8").splitlines()
        self.assertIn("docs/research/apf_stfs_rehash.md", allowed)

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
